# Local Shop Setup Guide (Offline / No Cloud Costs)

This guide explains how the system runs completely offline on the shop PC with automated startup and a desktop app experience, as well as how to set it up on another computer.

---

## 1. What Has Been Configured On This PC

1. **Silent Background Server Launcher (`start_app_silent.vbs` + `run_server.bat`):**
   - Starts Uvicorn on `http://127.0.0.1:8000` silently with **no black command prompt window**.
2. **Auto-Start on Boot:**
   - Configured in Windows Startup (`shell:startup`). Whenever this computer turns on or logs in, the backend server starts silently in the background.
3. **One-Click Desktop POS App (`Amee Mobiles POS` on your Desktop):**
   - An icon with your emblem logo on the Desktop.
   - Double-clicking it checks if the server is running (starts it if needed), and opens Google Chrome or Microsoft Edge in **frameless standalone app mode** (`--app=http://localhost:8000`).
   - Feels like a native Windows desktop software without address bar or browser clutter.

---

## 2. Steps to Set Up on a Different / New PC

When moving or installing this project onto another Windows PC:

### Step 1: Install Python & uv
1. Install **Python 3.12+** from [python.org](https://www.python.org/downloads/) (make sure to check **"Add python.exe to PATH"** during installation).
2. Open PowerShell or Command Prompt and install `uv` (fast package manager):
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

### Step 2: Copy the Project Folder
- Copy the entire `service` folder (via USB drive or `git clone https://github.com/syedraihanm/tracksale.git`) onto the new PC (e.g. `C:\AmeeMobiles\service` or Desktop).

### Step 3: Install Dependencies & Run Database Migration
Open Command Prompt in that folder and run:
```cmd
uv sync
uv run alembic upgrade head
```

### Step 4: Configure Auto-Start & Desktop Icon (One-Click)
1. Double-click **`install_autostart.bat`**:
   - This places a silent startup link in Windows Startup so the server starts when the PC powers on.
2. Run this command in the project folder to create the Desktop icon:
   ```cmd
   uv run python -c "import os, subprocess; subprocess.run(['cmd', '/c', 'launch_pos_app.bat'])"
   ```
   Or simply right-click **`launch_pos_app.bat`** -> **Send to** -> **Desktop (create shortcut)**, rename it to `Amee Mobiles POS`, and assign the icon from `app\static\app.ico`.

---

## 3. Local Data Backup & Safety

Since all shop data lives in `data/shop.db`:
- **Automated Hourly Backups:** The app automatically creates database snapshots in `backups/`.
- **Pen Drive Copy:** Plug in a USB pen drive once a week and copy the `data/shop.db` or `backups/` folder.
- **Free Cloud Mirror (No Server Cost):** You can install Google Drive or OneDrive on the PC and set it to sync the `backups/` folder to the owner's personal free 15 GB account.
