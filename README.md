# AFIS Pack Installer

![Version](https://img.shields.io/badge/version-v1.0.0-brightgreen)
![Status](https://img.shields.io/badge/status-active-success)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

A local helper for installing **Minecraft Bedrock Dedicated Server add-on packs**.

AFIS Pack Installer reads `.mcpack`, `.mcaddon`, `.zip`, or unpacked pack folders, finds `manifest.json`, grabs the pack UUID/version, copies the pack into the correct Bedrock Dedicated Server folder, and updates the world JSON files for you.

> ⚠️ **This tool runs locally on your machine.**  
> It does not upload your server files, SFTP credentials, worlds, or packs anywhere.

---

## ⬇️ Download

Download the latest version from the **Releases** page:

https://github.com/sayrejeri/AFIS-Pack-Installer/releases/latest

---

## ✨ Features

- Reads `.mcpack`, `.mcaddon`, `.zip`, and unpacked pack folders
- Finds `manifest.json` automatically
- Reads `header.uuid` and `header.version`
- Detects behavior packs vs resource packs from module types
- Copies packs into `behavior_packs/` or `resource_packs/`
- Updates:
  - `world_behavior_packs.json`
  - `world_resource_packs.json`
- Avoids duplicate UUID entries
- Updates existing pack versions when the UUID already exists
- Backs up old world JSON files before editing
- Can set `texturepack-required=true` in `server.properties`
- Works well with SFTP workflows for hosts like Four Seasons Hosting

---

## 🖥️ How It Works

1. Choose your Bedrock Dedicated Server folder.
2. Choose the world folder you want to install the pack into.
3. Choose a `.mcpack`, `.mcaddon`, `.zip`, or unpacked pack folder.
4. The installer scans every `manifest.json` it finds.
5. It installs behavior/resource packs into the correct server folders.
6. It updates the correct world JSON files.
7. Restart your Bedrock server.

---

## 📦 Installation Options

### Option A: Windows EXE

Download the latest `.exe` from the **Releases** page when available.

No Python install needed.

### Option B: Run from Source

1. Install **Python 3.10+**.
2. Download or clone this repo.
3. Run the GUI:

```bash
python afis_pack_installer.py --gui
```

Or run the CLI:

```bash
python afis_pack_installer.py --server-root "C:\BDS" --world "Bedrock level" --pack "C:\Packs\AFIS-SkyGen.mcaddon" --texturepack-required
```

### Dry Run

Use dry run to preview changes without editing anything:

```bash
python afis_pack_installer.py --server-root "C:\BDS" --world "Bedrock level" --pack "C:\Packs\AFIS-SkyGen.mcaddon" --dry-run
```

---

## 📁 Bedrock Dedicated Server Paths

The tool updates these locations:

```txt
server-root/
├─ behavior_packs/
├─ resource_packs/
├─ server.properties
└─ worlds/
   └─ YourWorld/
      ├─ world_behavior_packs.json
      ├─ world_resource_packs.json
      └─ afis_pack_installer_backups/
```

---

## 🌐 Four Seasons Hosting / SFTP Workflow

If your host gives you SFTP access:

1. Download your world/server files with FileZilla or another SFTP client.
2. Run AFIS Pack Installer locally.
3. Upload the changed files back to the server:
   - `behavior_packs/`
   - `resource_packs/`
   - `worlds/<world>/world_behavior_packs.json`
   - `worlds/<world>/world_resource_packs.json`
   - `server.properties` if texture pack required was enabled
4. Restart the server from the hosting panel.

---

## ✅ Supported Pack Types

Works with normal Bedrock add-on packs:

- Behavior packs
- Resource packs
- Script behavior packs
- `.mcaddon` files containing both BP and RP packs

Does not support:

- Java plugins
- Spigot/Paper/Bukkit mods
- Locked Marketplace content that cannot export normally

---

## 🔒 Privacy & Safety

- Runs fully local
- No external Python packages required
- No telemetry
- No online login
- No SFTP credentials stored
- Creates backups before editing world pack JSON files

---

## 📄 Output / Backups

Backups are saved inside the selected world folder:

```txt
worlds/YourWorld/afis_pack_installer_backups/YYYYMMDD-HHMMSS/
```

Each successful install also writes:

```txt
install_report.txt
```

---

## 🗺️ Roadmap

- [ ] Cleaner Windows EXE release
- [ ] Better pack validation screen
- [ ] Remove/uninstall pack option
- [ ] Installed packs list/export
- [ ] SFTP upload mode
- [ ] Web dashboard integration
- [ ] Discord bot integration

---

## ❗ Disclaimer

This project is not affiliated with Mojang, Microsoft, Minecraft, Bedrock Dedicated Server, or Four Seasons Hosting.

Use at your own risk. Always back up your world before installing or updating packs.

---

## 📜 License

License is currently **TBD**.

MIT is a good fit if you want this open-source like RBXTools. If you want AFIS tools more controlled, use All Rights Reserved or a custom license.

---

## 🤝 Contributing

Pull requests and improvements are welcome once the repo is public.

Good contribution areas:

- Better Windows UI
- More manifest validation
- SFTP support
- BDS compatibility testing
- Pack uninstall/update workflows
