#!/usr/bin/env python3
"""
AFIS Bedrock Pack Installer

A local helper for Bedrock Dedicated Server worlds. It reads .mcpack/.mcaddon/.zip files
or unpacked pack folders, finds manifest.json files, copies behavior/resource packs into
the right BDS folders, and updates world_behavior_packs.json / world_resource_packs.json.

No external Python packages required.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

APP_NAME = "AFIS Bedrock Pack Installer"
SUPPORTED_ARCHIVES = {".mcpack", ".mcaddon", ".zip"}


@dataclass
class PackInfo:
    name: str
    uuid: str
    version: List[int]
    kind: str  # "behavior" or "resource"
    manifest: Dict[str, Any]
    source_mode: str  # "folder" or "archive"
    source_path: Path
    root_in_archive: str = ""
    root_folder: Optional[Path] = None

    @property
    def suffix(self) -> str:
        return "bp" if self.kind == "behavior" else "rp"


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def safe_name(value: str, fallback: str = "pack") -> str:
    value = re.sub(r"[^a-zA-Z0-9._ -]+", "", value).strip().replace(" ", "_")
    value = re.sub(r"_+", "_", value)
    return value[:80] or fallback


def normalize_version(value: Any) -> List[int]:
    if isinstance(value, list):
        result: List[int] = []
        for item in value[:3]:
            try:
                result.append(int(item))
            except Exception:
                result.append(0)
        while len(result) < 3:
            result.append(0)
        return result
    if isinstance(value, str):
        parts = [p for p in re.split(r"[^0-9]+", value) if p]
        result = [int(p) for p in parts[:3]]
        while len(result) < 3:
            result.append(0)
        return result
    return [1, 0, 0]


def detect_kind(manifest: Dict[str, Any]) -> Optional[str]:
    module_types = []
    for module in manifest.get("modules", []) or []:
        if isinstance(module, dict):
            module_types.append(str(module.get("type", "")).lower())

    # Behavior packs usually contain data and/or script modules.
    if any(t in {"data", "script", "server_data"} for t in module_types):
        return "behavior"

    # Resource packs usually contain resources/client_data modules.
    if any(t in {"resources", "client_data"} for t in module_types):
        return "resource"

    # Some older packs are not cleanly labeled. Fall back carefully.
    caps = manifest.get("capabilities", []) or []
    caps_text = " ".join(str(c).lower() for c in caps)
    if "script" in caps_text:
        return "behavior"

    return None


def parse_manifest(manifest: Dict[str, Any], source_mode: str, source_path: Path, root_in_archive: str = "", root_folder: Optional[Path] = None) -> Optional[PackInfo]:
    header = manifest.get("header", {})
    pack_uuid = header.get("uuid")
    if not pack_uuid:
        return None

    pack_kind = detect_kind(manifest)
    if not pack_kind:
        return None

    return PackInfo(
        name=str(header.get("name") or root_folder.name if root_folder else header.get("name") or source_path.stem),
        uuid=str(pack_uuid),
        version=normalize_version(header.get("version", [1, 0, 0])),
        kind=pack_kind,
        manifest=manifest,
        source_mode=source_mode,
        source_path=source_path,
        root_in_archive=root_in_archive.strip("/"),
        root_folder=root_folder,
    )


def read_json_bytes(data: bytes, label: str) -> Dict[str, Any]:
    try:
        return json.loads(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Could not read JSON from {label}: {exc}") from exc


def find_packs_in_archive(path: Path) -> List[PackInfo]:
    packs: List[PackInfo] = []
    with zipfile.ZipFile(path, "r") as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        manifest_names = [n for n in names if Path(n).name.lower() == "manifest.json" and "__MACOSX" not in n]
        for manifest_name in manifest_names:
            try:
                manifest = read_json_bytes(zf.read(manifest_name), manifest_name)
                root = str(Path(manifest_name).parent).replace("\\", "/")
                if root == ".":
                    root = ""
                pack = parse_manifest(manifest, "archive", path, root_in_archive=root)
                if pack:
                    packs.append(pack)
            except Exception as exc:
                print(f"[WARN] Skipped manifest in archive: {manifest_name} ({exc})")
    return packs


def find_packs_in_folder(path: Path) -> List[PackInfo]:
    packs: List[PackInfo] = []
    manifest_paths = [p for p in path.rglob("manifest.json") if "__MACOSX" not in str(p)]
    for manifest_path in manifest_paths:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            root_folder = manifest_path.parent
            pack = parse_manifest(manifest, "folder", path, root_folder=root_folder)
            if pack:
                packs.append(pack)
        except Exception as exc:
            print(f"[WARN] Skipped manifest: {manifest_path} ({exc})")
    return packs


def find_packs(input_path: Path) -> List[PackInfo]:
    input_path = input_path.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Pack path does not exist: {input_path}")

    if input_path.is_file():
        if input_path.suffix.lower() not in SUPPORTED_ARCHIVES:
            raise ValueError(f"Unsupported file type: {input_path.suffix}. Use .mcpack, .mcaddon, .zip, or a folder.")
        return find_packs_in_archive(input_path)

    if input_path.is_dir():
        return find_packs_in_folder(input_path)

    raise ValueError(f"Unsupported pack path: {input_path}")


def resolve_world_path(server_root: Path, world_arg: str) -> Path:
    world_path = Path(world_arg).expanduser()
    if world_path.exists():
        return world_path.resolve()

    candidate = server_root / "worlds" / world_arg
    if candidate.exists():
        return candidate.resolve()

    # Create it only if parent worlds exists and user supplied a name.
    raise FileNotFoundError(
        f"World not found. Tried '{world_arg}' and '{candidate}'. Choose the actual world folder inside server_root/worlds/."
    )


def backup_file(path: Path, backup_dir: Path) -> Optional[Path]:
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / path.name
    shutil.copy2(path, dest)
    return dest


def move_to_backup(path: Path, backup_dir: Path) -> Optional[Path]:
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / path.name
    counter = 1
    while dest.exists():
        dest = backup_dir / f"{path.name}.{counter}"
        counter += 1
    shutil.move(str(path), str(dest))
    return dest


def read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []
    except Exception:
        return []


def write_json_list(path: Path, data: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def update_world_pack_file(path: Path, pack: PackInfo, backup_dir: Path, dry_run: bool = False) -> str:
    backup_file(path, backup_dir)
    entries = read_json_list(path)
    changed = False
    found = False
    for entry in entries:
        if str(entry.get("pack_id", "")).lower() == pack.uuid.lower():
            found = True
            if entry.get("version") != pack.version:
                entry["version"] = pack.version
                changed = True
            break

    if not found:
        entries.append({"pack_id": pack.uuid, "version": pack.version})
        changed = True

    if not dry_run:
        write_json_list(path, entries)

    if found and changed:
        return f"Updated version in {path.name}"
    if found:
        return f"Already listed in {path.name}"
    return f"Added to {path.name}"


def manifest_uuid_from_folder(folder: Path) -> Optional[str]:
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        uuid = manifest.get("header", {}).get("uuid")
        return str(uuid) if uuid else None
    except Exception:
        return None


def backup_existing_same_uuid(pack_dir: Path, pack_uuid: str, backup_dir: Path, dry_run: bool = False) -> List[str]:
    moved: List[str] = []
    if not pack_dir.exists():
        return moved
    for child in pack_dir.iterdir():
        if not child.is_dir():
            continue
        existing_uuid = manifest_uuid_from_folder(child)
        if existing_uuid and existing_uuid.lower() == pack_uuid.lower():
            moved.append(child.name)
            if not dry_run:
                move_to_backup(child, backup_dir / "old_pack_folders")
    return moved


def copy_pack_from_folder(pack: PackInfo, dest: Path, dry_run: bool = False) -> None:
    assert pack.root_folder is not None
    if dry_run:
        return
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(pack.root_folder, dest)


def copy_pack_from_archive(pack: PackInfo, dest: Path, dry_run: bool = False) -> None:
    if dry_run:
        return
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    root = pack.root_in_archive.strip("/")
    prefix = f"{root}/" if root else ""
    with zipfile.ZipFile(pack.source_path, "r") as zf:
        for member in zf.infolist():
            name = member.filename.replace("\\", "/")
            if member.is_dir() or "__MACOSX" in name:
                continue
            if prefix:
                if not name.startswith(prefix):
                    continue
                relative = name[len(prefix):]
            else:
                relative = name

            if not relative or relative.startswith("../") or "/../" in relative:
                continue
            out_path = dest / relative
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, open(out_path, "wb") as dst:
                shutil.copyfileobj(src, dst)


def copy_pack(pack: PackInfo, server_root: Path, backup_dir: Path, dry_run: bool = False) -> Tuple[Path, List[str]]:
    target_base = server_root / ("behavior_packs" if pack.kind == "behavior" else "resource_packs")
    target_base.mkdir(parents=True, exist_ok=True)

    moved_old = backup_existing_same_uuid(target_base, pack.uuid, backup_dir, dry_run=dry_run)

    dest_name = f"{safe_name(pack.name)}_{pack.uuid[:8]}_{pack.suffix}"
    dest = target_base / dest_name

    if pack.source_mode == "folder":
        copy_pack_from_folder(pack, dest, dry_run=dry_run)
    else:
        copy_pack_from_archive(pack, dest, dry_run=dry_run)

    return dest, moved_old


def set_server_property(server_root: Path, key: str, value: str, backup_dir: Path, dry_run: bool = False) -> str:
    props_path = server_root / "server.properties"
    backup_file(props_path, backup_dir)
    lines: List[str] = []
    found = False
    if props_path.exists():
        lines = props_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    new_lines: List[str] = []
    for line in lines:
        if line.strip().startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        existing_key = line.split("=", 1)[0].strip()
        if existing_key == key:
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")

    if not dry_run:
        props_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return f"Set {key}={value} in server.properties"


def install_pack(server_root: Path, world: str, pack_input: Path, texturepack_required: bool = False, dry_run: bool = False) -> str:
    server_root = server_root.expanduser().resolve()
    if not server_root.exists():
        raise FileNotFoundError(f"Server root does not exist: {server_root}")

    world_path = resolve_world_path(server_root, world)
    backup_dir = world_path / "afis_pack_installer_backups" / now_stamp()

    packs = find_packs(pack_input)
    if not packs:
        raise ValueError("No valid Bedrock behavior/resource pack manifest.json files were found.")

    report: List[str] = []
    report.append(f"{APP_NAME} report")
    report.append(f"Time: {_dt.datetime.now().isoformat(timespec='seconds')}")
    report.append(f"Server root: {server_root}")
    report.append(f"World: {world_path}")
    report.append(f"Pack input: {pack_input}")
    report.append(f"Dry run: {dry_run}")
    report.append("")

    for pack in packs:
        report.append(f"Detected {pack.kind.upper()} pack: {pack.name}")
        report.append(f"  UUID: {pack.uuid}")
        report.append(f"  Version: {'.'.join(map(str, pack.version))}")
        dest, moved_old = copy_pack(pack, server_root, backup_dir, dry_run=dry_run)
        if moved_old:
            report.append(f"  Backed up old folder(s): {', '.join(moved_old)}")
        report.append(f"  Installed folder: {dest}")

        if pack.kind == "behavior":
            target_json = world_path / "world_behavior_packs.json"
        else:
            target_json = world_path / "world_resource_packs.json"
        report.append(f"  {update_world_pack_file(target_json, pack, backup_dir, dry_run=dry_run)}")
        report.append("")

    if texturepack_required:
        report.append(set_server_property(server_root, "texturepack-required", "true", backup_dir, dry_run=dry_run))
        report.append("")

    report.append(f"Backup folder: {backup_dir}")
    report.append("Restart the Bedrock server after installing/updating packs.")

    report_text = "\n".join(report)
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "install_report.txt").write_text(report_text + "\n", encoding="utf-8")
    return report_text


def interactive_menu() -> int:
    print(f"\n{APP_NAME}\n" + "=" * len(APP_NAME))
    server_root = Path(input("BDS server root folder: ").strip().strip('"'))
    world = input("World folder path OR world name inside server_root/worlds: ").strip().strip('"')
    pack_input = Path(input("Pack file/folder path (.mcpack/.mcaddon/.zip/folder): ").strip().strip('"'))
    texture_required = input("Force texture pack required? (y/N): ").strip().lower().startswith("y")
    dry_run = input("Dry run only? (y/N): ").strip().lower().startswith("y")

    try:
        report = install_pack(server_root, world, pack_input, texture_required, dry_run=dry_run)
        print("\n" + report)
        return 0
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print(traceback.format_exc())
        return 1


def gui_menu() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as exc:
        print(f"Tkinter GUI unavailable: {exc}")
        return interactive_menu()

    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(APP_NAME, "Choose your Bedrock Dedicated Server folder, world folder, and pack file/folder.")

    server_root = filedialog.askdirectory(title="Choose BDS server root folder")
    if not server_root:
        return 1

    initial_worlds = str(Path(server_root) / "worlds") if (Path(server_root) / "worlds").exists() else server_root
    world_path = filedialog.askdirectory(title="Choose world folder", initialdir=initial_worlds)
    if not world_path:
        return 1

    pack_file = filedialog.askopenfilename(
        title="Choose pack file (.mcpack/.mcaddon/.zip) or Cancel to choose a folder",
        filetypes=[("Bedrock packs", "*.mcpack *.mcaddon *.zip"), ("All files", "*.*")],
    )
    if pack_file:
        pack_input = pack_file
    else:
        pack_folder = filedialog.askdirectory(title="Choose unpacked pack folder")
        if not pack_folder:
            return 1
        pack_input = pack_folder

    texture_required = messagebox.askyesno(APP_NAME, "Set texturepack-required=true in server.properties?")

    try:
        report = install_pack(Path(server_root), world_path, Path(pack_input), texture_required, dry_run=False)
        messagebox.showinfo(APP_NAME, report[:3500] + ("\n\n...Report was longer. Check install_report.txt in the backup folder." if len(report) > 3500 else ""))
        print(report)
        return 0
    except Exception as exc:
        error = f"ERROR: {exc}\n\n{traceback.format_exc()}"
        messagebox.showerror(APP_NAME, error[:3500])
        print(error)
        return 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--gui", action="store_true", help="Open simple file picker GUI.")
    parser.add_argument("--server-root", help="Bedrock Dedicated Server root folder.")
    parser.add_argument("--world", help="World folder path, or world name inside server_root/worlds.")
    parser.add_argument("--pack", help="Pack file/folder path: .mcpack, .mcaddon, .zip, or folder.")
    parser.add_argument("--texturepack-required", action="store_true", help="Set texturepack-required=true in server.properties.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without changing files.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        return interactive_menu()

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.gui:
        return gui_menu()

    missing = [name for name in ["server_root", "world", "pack"] if not getattr(args, name)]
    if missing:
        parser.error("Missing required arguments unless using --gui: " + ", ".join("--" + m.replace("_", "-") for m in missing))

    try:
        report = install_pack(
            Path(args.server_root),
            args.world,
            Path(args.pack),
            texturepack_required=args.texturepack_required,
            dry_run=args.dry_run,
        )
        print(report)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
