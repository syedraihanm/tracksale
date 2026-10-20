# Local Shop Setup Guide (Offline / No Cloud Costs)

This guide explains how the system runs completely offline on the shop PC with automated startup and a desktop app experience, as well as how to set it up on another computer.

---

## 1. What Has Been Configured On This PC

1. **Silent Background Server Launcher (`start_app_silent.vbs` + `run_server.bat`):**
   - Starts Uvicorn on `http://127.0.0.1:8000` silently with **no black command prompt window**.
2. **Auto-Start on Login:**
   - Configured in Windows Startup (`shell:startup`). The backend server starts silently when the shop user signs in to Windows.
3. **One-Click Desktop POS App (`Amee Mobiles POS` on your Desktop):**
   - An icon with your emblem logo on the Desktop.
   - Double-clicking it checks the server's health, starts it if needed, waits until it is ready, and opens Google Chrome or Microsoft Edge in **frameless standalone app mode** (`--app=http://127.0.0.1:8000`).
   - Feels like a native Windows desktop software without address bar or browser clutter.

---

## 2. Set Up on a Different / New PC

Copy the `service` project folder to the new PC. Do not copy `.venv` or `.git`; the installer rebuilds the Python environment. For a fresh shop, also leave out `.env`, `data\shop.db`, and `backups\` so setup creates fresh secrets and an empty database.

The new PC needs an internet connection for the first setup. Double-click **`setup_shop_pc.bat`**. It installs `uv`, uses an existing Python 3.12 or installs a managed one, installs the locked app dependencies, creates a local `.env` with unique secrets if one is missing, applies database migrations, and creates the Desktop app shortcut plus the Windows sign-in startup link.

The installer does not seed sample tickets, import data, or erase an existing database. A fresh database opens the first-run setup screen with **AMEE MOBILES** prefilled so the owner can set one 4–6 digit Shop PIN for sign-in and owner authorization (for example, `1234`).

After setup, double-click **`Amee Mobiles POS`** on the Desktop. It starts the local server if needed, waits for its health check, then opens the shop app in Chrome or Edge app mode. Diagnostics are saved under `%LOCALAPPDATA%\AmeeMobiles\logs`.

The shortcut stores the project folder path. If you move the folder later, run `setup_shop_pc.bat` again to rebuild the shortcuts.

---

## 3. Local Data Backup & Safety

Since all shop data lives in `data/shop.db`:
- **Automated Hourly Backups:** The app automatically creates database snapshots in `backups/`.
- **Pen Drive Copy:** Plug in a USB pen drive once a week and copy the `data/shop.db` or `backups/` folder.
- **Free Cloud Mirror (No Server Cost):** You can install Google Drive or OneDrive on the PC and set it to sync the `backups/` folder to the owner's personal free 15 GB account.
