#!/usr/bin/env python3
"""Run the CV service directly on this computer, starting by itself at login.

The API then uses it first and falls back to the CV service in Docker whenever it is not available.
Inference can be several times faster outside Docker's virtual machine (5x on an M1 Mac).

Once per computer, with Docker running and Python 3.12:

    python3.12 scripts/native_cv.py install      (Windows: py -3.12 scripts\\native_cv.py install)

Run install again after changing the CV service or its settings in .env, to pick up the changes.

    python3.12 scripts/native_cv.py uninstall    back to Docker only
    python3.12 scripts/native_cv.py run          run it in this terminal instead

Works on macOS (launchd), Linux (systemd user service) and Windows (Task Scheduler).
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = Path(__file__).resolve()
CV_SERVICE = ROOT / "cv-service"
MODELS = CV_SERVICE / "models"
VENV = CV_SERVICE / ".venv"
LOG = VENV / "native-service.log"
PORT = 8001  # the cv-service container publishes 8000
IMAGE = "golfcoach-cv-service"
CLUB_MODEL = "club_swingtrace_yolo11m_quant.onnx"
NAME = "golfcoach-cv-service"
MAC_LABEL = "com.golfcoach.cv-service"
MAC_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
LINUX_UNIT = Path.home() / ".config" / "systemd" / "user" / f"{NAME}.service"

WINDOWS = os.name == "nt"
MAC = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")
VENV_BIN = VENV / ("Scripts" if WINDOWS else "bin")
VENV_PYTHON = VENV_BIN / ("python.exe" if WINDOWS else "python")


def setting(name: str, default: str) -> str:
    """The same order as Docker Compose: this shell, then .env, then the default."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = ROOT / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.is_file() else []
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key.strip() == name and not key.lstrip().startswith("#"):
            value = value.strip().strip("\"'")
            if value:
                return value
    return default


def pose_model() -> str:
    return f"pose_landmarker_{setting('POSE_MODEL_VARIANT', 'heavy')}.task"


def call(*args: str, check: bool = True, cwd: Path | None = None) -> str:
    done = subprocess.run(args, check=check, cwd=cwd, stdout=subprocess.PIPE, text=True)
    return done.stdout.strip()


def prepare() -> None:
    if sys.version_info[:2] != (3, 12):
        sys.exit("Please run this with Python 3.12 (the version the CV service is built for).")
    if not shutil.which("docker"):
        sys.exit("Docker is needed once, to get the models out of the image.")
    if not VENV_PYTHON.exists():
        print("Creating the Python environment")
        call(sys.executable, "-m", "venv", str(VENV))
    print("Installing packages")
    call(str(VENV_PYTHON), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt", cwd=CV_SERVICE)

    print("Copying the models out of the Docker image")
    call("docker", "compose", "build", "cv-service", cwd=ROOT)
    container = call("docker", "create", IMAGE)
    try:
        for model in (pose_model(), CLUB_MODEL):
            call("docker", "cp", f"{container}:/app/models/{model}", str(MODELS / model))
    finally:
        call("docker", "rm", container)


def listen_address() -> str:
    """Only reachable from this computer. On Linux, containers reach the host via Docker's bridge."""
    if LINUX:
        return call("docker", "network", "inspect", "bridge", "--format", "{{(index .IPAM.Config 0).Gateway}}")
    return "127.0.0.1"


def club_threads() -> str:
    """Macs: the performance cores only, the slower ones would hold them back. Else: the default."""
    return call("sysctl", "-n", "hw.perflevel0.physicalcpu", check=False) or "0" if MAC else "0"


def run() -> None:
    os.environ.update(
        DATA_DIR=str(ROOT / "data"),
        POSE_MODEL_PATH=str(MODELS / pose_model()),
        CLUB_MODEL_PATH=str(MODELS / CLUB_MODEL),
        CLUB_THREADS=club_threads(),
        MAX_PROCESS_DIM=setting("MAX_PROCESS_DIM", "1280"),
        NUM_POSES=setting("NUM_POSES", "2"),
    )
    os.chdir(CV_SERVICE)
    command = [
        str(VENV_PYTHON), "-m", "uvicorn", "app.main:app",
        "--host", listen_address(), "--port", str(PORT), "--no-access-log",
    ]
    if WINDOWS:  # started without a console by Task Scheduler
        with open(LOG, "a", encoding="utf-8") as log:
            sys.exit(subprocess.call(command, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW))
    os.execv(command[0], command)


def install_mac() -> None:
    uninstall_mac()
    MAC_PLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(MAC_PLIST, "wb") as fh:
        plistlib.dump(
            {
                "Label": MAC_LABEL,
                "ProgramArguments": [str(VENV_PYTHON), str(SCRIPT), "run"],
                "RunAtLoad": True,
                "KeepAlive": True,
                "ProcessType": "Interactive",  # no background throttling
                "StandardOutPath": str(LOG),
                "StandardErrorPath": str(LOG),
            },
            fh,
        )
    call("launchctl", "bootstrap", f"gui/{os.getuid()}", str(MAC_PLIST))


def uninstall_mac() -> None:
    call("launchctl", "bootout", f"gui/{os.getuid()}/{MAC_LABEL}", check=False)
    MAC_PLIST.unlink(missing_ok=True)


def install_linux() -> None:
    LINUX_UNIT.parent.mkdir(parents=True, exist_ok=True)
    LINUX_UNIT.write_text(
        "[Unit]\nDescription=Golf Coach CV service\n\n"
        f'[Service]\nExecStart="{VENV_PYTHON}" "{SCRIPT}" run\nRestart=always\nRestartSec=10\n\n'
        "[Install]\nWantedBy=default.target\n",
        encoding="utf-8",
    )
    call("systemctl", "--user", "daemon-reload")
    call("systemctl", "--user", "enable", NAME)
    call("systemctl", "--user", "restart", NAME)


def uninstall_linux() -> None:
    call("systemctl", "--user", "disable", "--now", NAME, check=False)
    LINUX_UNIT.unlink(missing_ok=True)
    call("systemctl", "--user", "daemon-reload", check=False)


def install_windows() -> None:
    pythonw = VENV_BIN / "pythonw.exe"
    call("schtasks", "/Create", "/F", "/SC", "ONLOGON", "/TN", NAME, "/TR", f'"{pythonw}" "{SCRIPT}" run')
    call("schtasks", "/End", "/TN", NAME, check=False)
    call("schtasks", "/Run", "/TN", NAME)


def uninstall_windows() -> None:
    call("schtasks", "/End", "/TN", NAME, check=False)
    call("schtasks", "/Delete", "/F", "/TN", NAME, check=False)


def platform_steps():
    if MAC:
        return install_mac, uninstall_mac
    if LINUX:
        return install_linux, uninstall_linux
    if WINDOWS:
        return install_windows, uninstall_windows
    sys.exit(f"{sys.platform} is not supported; the CV service in Docker still works.")


def main() -> None:
    action = sys.argv[1] if len(sys.argv) == 2 else ""
    if action == "run":
        run()
    elif action == "install":
        install, _ = platform_steps()
        prepare()
        install()
        print(f"Done. The CV service now runs on this computer (port {PORT}) and starts at login.")
    elif action == "uninstall":
        platform_steps()[1]()
        print("Done. Analyses now run in Docker.")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
