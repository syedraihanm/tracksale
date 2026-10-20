"""Per-user Windows entry point for the packaged Amee Mobiles POS app."""

from __future__ import annotations

import ctypes
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.fernet import Fernet

APP_TITLE = "AMEE MOBILES POS"
HOST = "127.0.0.1"
PORT = int(os.environ.get("AMEE_MOBILES_PORT", "8000"))
APP_URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{APP_URL}/healthz"
BACKGROUND_MODE = "--background" in sys.argv[1:]


def resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def user_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "AmeeMobiles"
    return Path.home() / "AppData" / "Local" / "AmeeMobiles"


def ensure_user_environment(data_root: Path) -> None:
    env_file = data_root / ".env"
    if not env_file.exists():
        values = [
            "APP_ENV=production",
            f"SECRET_KEY={secrets.token_urlsafe(48)}",
            f"PASSCODE_ENCRYPTION_KEY={Fernet.generate_key().decode('ascii')}",
            "DATABASE_URL=sqlite:///data/shop.db",
            "BACKUP_DIR=backups",
            "COOKIE_SECURE=false",
        ]
        temp_file = env_file.with_suffix(".env.tmp")
        temp_file.write_text("\n".join(values) + "\n", encoding="ascii")
        os.replace(temp_file, env_file)

    # Keep writable data and generated secrets outside the versioned install folder.
    os.environ["APP_ENV"] = "production"
    os.environ["DATABASE_URL"] = "sqlite:///data/shop.db"
    os.environ["BACKUP_DIR"] = "backups"
    os.environ["COOKIE_SECURE"] = "false"


def app_is_healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1) as response:
            return response.status == 200 and b'"status":"ok"' in response.read()
    except (OSError, urllib.error.URLError):
        return False


def port_is_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.5)
        return connection.connect_ex((HOST, PORT)) == 0


def open_app_window() -> None:
    candidates = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.extend(
                (
                    Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                    Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                )
            )

    for browser in candidates:
        if browser.is_file():
            subprocess.Popen(
                [str(browser), f"--app={APP_URL}"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            )
            return

    os.startfile(APP_URL)  # type: ignore[attr-defined]


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10)


def migrate_database(bundle_root: Path) -> None:
    from alembic import command
    from alembic.config import Config

    config_file = bundle_root / "alembic.ini"
    migrations = bundle_root / "alembic"
    if not config_file.is_file() or not migrations.is_dir():
        raise FileNotFoundError("The packaged database migration files are missing.")

    config = Config(str(config_file))
    config.set_main_option("script_location", str(migrations))
    command.upgrade(config, "head")


def open_browser_when_ready(log_file: Path) -> None:
    for _ in range(60):
        if app_is_healthy():
            open_app_window()
            return
        time.sleep(0.5)

    show_error(f"The repair app did not start. Check the log file:\n{log_file}")


def main() -> int:
    data_root = user_data_root()
    logs_dir = data_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"
    log_stream = log_file.open("a", encoding="utf-8", buffering=1)
    sys.stdout = log_stream
    sys.stderr = log_stream

    try:
        if app_is_healthy():
            if not BACKGROUND_MODE:
                open_app_window()
            return 0
        if port_is_open():
            raise RuntimeError(f"Port {PORT} is already in use by another application.")

        data_root.mkdir(parents=True, exist_ok=True)
        (data_root / "data").mkdir(exist_ok=True)
        (data_root / "backups").mkdir(exist_ok=True)
        ensure_user_environment(data_root)
        os.chdir(data_root)

        bundle_root = resource_root()
        migrate_database(bundle_root)

        if not BACKGROUND_MODE:
            threading.Thread(target=open_browser_when_ready, args=(log_file,), daemon=True).start()

        import uvicorn

        uvicorn.run(
            "app.main:app",
            host=HOST,
            port=PORT,
            log_config=None,
            access_log=False,
            log_level="info",
            loop="asyncio",
            http="h11",
            lifespan="on",
        )
        return 0
    except Exception as exc:
        print(traceback.format_exc())
        show_error(f"Amee Mobiles POS could not start.\n\n{exc}\n\nLog: {log_file}")
        return 1
    finally:
        log_stream.flush()
        log_stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
