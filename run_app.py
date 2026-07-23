"""One-command local app: check/install deps, serve API+UI, open browser."""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
VENV_WIN = BACKEND / ".venv" / "Scripts" / "python.exe"
VENV_UNIX = BACKEND / ".venv" / "bin" / "python"
PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "0.0.0.0")
LOCAL_URL = f"http://127.0.0.1:{PORT}"
MIN_PY = (3, 12)
LOG_PATH = ROOT / "herbie.log"
_HERO_SHOWN = False


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            try:
                stream.write(data)
                stream.flush()
            except Exception:
                pass
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:
                pass


def _setup_logging() -> None:
    try:
        log = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        sys.stdout = _Tee(sys.__stdout__, log)  # type: ignore[assignment]
        sys.stderr = _Tee(sys.__stderr__, log)  # type: ignore[assignment]
    except OSError:
        pass


def _log(msg: str) -> None:
    print(msg, flush=True)


def _install_hero_path() -> Path:
    return ROOT / "scripts" / "install_hero.txt"


def _show_install_hero() -> None:
    global _HERO_SHOWN
    if _HERO_SHOWN:
        return
    _HERO_SHOWN = True
    path = _install_hero_path()
    if not path.is_file():
        _log("")
        _log("  H E R B I E   C R E A T I V E")
        _log("  first launch - installing packages")
        _log("")
        return
    try:
        art = path.read_text(encoding="utf-8")
    except OSError:
        return
    _log(art.rstrip("\n"))
    _log("")


def _spinner(stop: threading.Event, label: str) -> None:
    frames = "|/-\\"
    i = 0
    started = time.monotonic()
    while not stop.wait(0.2):
        frame = frames[i % len(frames)]
        elapsed = int(time.monotonic() - started)
        line = f"\r  {frame} {label}  ({elapsed}s)   "
        try:
            sys.__stdout__.write(line)
            sys.__stdout__.flush()
        except Exception:
            pass
        i += 1
    try:
        sys.__stdout__.write("\r" + " " * (len(label) + 24) + "\r")
        sys.__stdout__.flush()
    except Exception:
        pass


def _write_status(step: str, detail: str = "") -> None:
    """Small status file so Open App / users can see what is happening."""
    try:
        path = ROOT / "herbie.status"
        line = step if not detail else f"{step}: {detail}"
        path.write_text(line + "\n", encoding="utf-8")
    except OSError:
        pass


def _run_with_spinner(label: str, argv: list[str], cwd: Path) -> None:
    _write_status("installing", label)
    _log(f"→ {label}")
    stop = threading.Event()
    thread = threading.Thread(target=_spinner, args=(stop, label), daemon=True)
    thread.start()
    log_file = None
    try:
        try:
            log_file = open(LOG_PATH, "a", encoding="utf-8")
            log_file.write(f"\n--- {label} ---\n")
            log_file.flush()
        except OSError:
            log_file = None
        subprocess.check_call(
            argv,
            cwd=cwd,
            stdout=log_file or subprocess.DEVNULL,
            stderr=log_file or subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        stop.set()
        thread.join(timeout=1.0)
        _write_status("error", label)
        _log(f"  FAILED  {label} (exit {exc.returncode})")
        _log(f"  See herbie.log for details.")
        raise
    finally:
        stop.set()
        thread.join(timeout=1.0)
        if log_file is not None:
            try:
                log_file.close()
            except OSError:
                pass
    _log(f"  OK  {label}")
    _write_status("ok", label)


def _health_ok(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"{LOCAL_URL}/health", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _lan_ip() -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return None


def _venv_python() -> Path | None:
    if VENV_WIN.exists():
        return VENV_WIN
    if VENV_UNIX.exists():
        return VENV_UNIX
    return None


def _python_version(exe: str | Path) -> tuple[int, int] | None:
    try:
        out = subprocess.check_output(
            [str(exe), "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        major, minor = out.split(".", 1)
        return int(major), int(minor)
    except Exception:
        return None


def _iter_windows_python_candidates() -> list[Path]:
    """Locate python.exe even when it is installed but not on PATH."""
    found: list[Path] = []
    seen: set[str] = set()

    def add(path: Path | None) -> None:
        if not path:
            return
        try:
            resolved = path.resolve()
        except OSError:
            return
        key = str(resolved).lower()
        if key in seen:
            return
        if "windowsapps" in key:
            return
        if resolved.is_file():
            seen.add(key)
            found.append(resolved)

    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
    search_roots = [
        local,
        Path(os.environ.get("ProgramFiles", "")) / "Python",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Python",
        home / "scoop" / "apps" / "python",
        home / "scoop" / "apps" / "python312",
        home / "scoop" / "apps" / "python313",
        home / "anaconda3",
        home / "miniconda3",
        home / "AppData" / "Local" / "miniconda3",
        home / "AppData" / "Local" / "anaconda3",
        home / ".pyenv" / "pyenv-win" / "versions",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        Path("C:/tools/python"),
    ]
    for root in search_roots:
        if root.is_dir():
            for exe in root.rglob("python.exe"):
                if "windowsapps" in str(exe).lower() or "\\lib\\venv\\" in str(exe).lower():
                    continue
                add(exe)

    for ver in ("Python314", "Python313", "Python312", "Python311", "Python310"):
        add(Path(os.environ.get("ProgramFiles", "")) / ver / "python.exe")
        add(Path(os.environ.get("ProgramFiles(x86)", "")) / ver / "python.exe")
        add(local / ver / "python.exe")

    system_drive = Path(os.environ.get("SystemDrive", "C:") + "/")
    if system_drive.is_dir():
        for folder in system_drive.glob("Python3*"):
            add(folder / "python.exe")

    if os.name == "nt":
        try:
            import winreg
        except ImportError:
            winreg = None  # type: ignore
        if winreg is not None:
            for hive, sub in (
                (winreg.HKEY_CURRENT_USER, r"Software\Python\PythonCore"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Python\PythonCore"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Python\PythonCore"),
            ):
                try:
                    with winreg.OpenKey(hive, sub) as core:
                        i = 0
                        while True:
                            try:
                                ver_name = winreg.EnumKey(core, i)
                            except OSError:
                                break
                            i += 1
                            try:
                                with winreg.OpenKey(core, rf"{ver_name}\InstallPath") as ip:
                                    install, _ = winreg.QueryValueEx(ip, None)
                                    add(Path(install) / "python.exe")
                                    try:
                                        exe_path, _ = winreg.QueryValueEx(ip, "ExecutablePath")
                                        add(Path(exe_path))
                                    except OSError:
                                        pass
                            except OSError:
                                continue
                except OSError:
                    continue

    py_launcher = shutil.which("py")
    if not py_launcher:
        for launch in (
            local / "Launcher" / "py.exe",
            Path(os.environ.get("SystemRoot", r"C:\Windows")) / "py.exe",
        ):
            if launch.is_file():
                py_launcher = str(launch)
                break
    if py_launcher:
        for args in (["-3"], ["-3-64"], ["-3.14"], ["-3.13"], ["-3.12"]):
            try:
                out = subprocess.check_output(
                    [py_launcher, *args, "-c", "import sys; print(sys.executable)"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                add(Path(out) if out else None)
            except Exception:
                pass

    for name in ("python3", "python"):
        which = shutil.which(name)
        if which:
            add(Path(which))

    return found


def _find_system_python() -> Path | None:
    if os.name == "nt":
        for candidate in _iter_windows_python_candidates():
            ver = _python_version(candidate)
            if ver and ver >= MIN_PY:
                return candidate
        return None

    for name in ("python3", "python"):
        path = shutil.which(name)
        if not path:
            continue
        ver = _python_version(path)
        if ver and ver >= MIN_PY:
            return Path(path)
    return None


def _try_winget_python() -> bool:
    winget = shutil.which("winget")
    if not winget:
        return False
    # --source winget only: public PCs often fail on the Microsoft Store (msstore) source.
    _log("Installing Python 3.12 via winget --source winget (skips Microsoft Store)...")
    cmd = [
        winget,
        "install",
        "-e",
        "--id",
        "Python.Python.3.12",
        "--source",
        "winget",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    # x64 Python on Windows ARM: more wheels exist than for native ARM builds.

    machine = (platform.machine() or "").lower()
    if "arm" in machine or "aarch64" in machine:
        cmd.extend(["--architecture", "x64"])
        _log("Windows ARM detected: requesting x64 Python for better package wheels.")
    try:
        subprocess.call(cmd)
        return True
    except OSError:
        return False


def _try_python_org_installer() -> bool:
    """Silent per-user install from python.org when winget is blocked (public PCs)."""
    ver = "3.12.10"
    url = f"https://www.python.org/ftp/python/{ver}/python-{ver}-amd64.exe"
    installer = Path(os.environ.get("TEMP", ".")) / "herbie-python-3.12-amd64.exe"
    _log("Downloading Python 3.12 for this user from python.org (no admin)...")
    try:
        import urllib.request

        urllib.request.urlretrieve(url, installer)
    except Exception as exc:
        _log(f"python.org download failed: {exc}")
        return False
    if not installer.is_file():
        return False
    _log("Running silent per-user Python install...")
    try:
        code = subprocess.call(
            [
                str(installer),
                "/quiet",
                "InstallAllUsers=0",
                "PrependPath=1",
                "Include_launcher=1",
                "InstallLauncherAllUsers=0",
                "Include_test=0",
                "SimpleInstall=1",
            ]
        )
        if code not in (0, None):
            _log(f"python.org installer exit code: {code}")
        return True
    except OSError as exc:
        _log(f"python.org installer failed: {exc}")
        return False
    finally:
        try:
            installer.unlink(missing_ok=True)
        except OSError:
            pass


def ensure_python() -> Path:
    existing = _venv_python()
    if existing:
        ver = _python_version(existing)
        if ver and ver >= MIN_PY:
            _log(f"Python OK (venv {ver[0]}.{ver[1]})")
            return existing
        _log(f"Project venv is Python {ver[0]}.{ver[1] if ver else '?'}; need {MIN_PY[0]}.{MIN_PY[1]}+")

    system = _find_system_python()
    if system:
        ver = _python_version(system)
        _log(f"Python OK ({system}" + (f", {ver[0]}.{ver[1]}" if ver else "") + ")")
        return system

    _log(f"Python {MIN_PY[0]}.{MIN_PY[1]}+ was not found.")
    if os.name == "nt":
        _log("On public PCs, winget often fails on Microsoft Store. Trying community winget, then python.org...")
        _try_winget_python()
        system = _find_system_python()
        if system:
            _log(f"Python OK ({system})")
            return system
        _try_python_org_installer()
        system = _find_system_python()
        if system:
            _log(f"Python OK ({system})")
            return system
        webbrowser.open("https://www.python.org/downloads/")
        raise SystemExit(
            f"Install Python {MIN_PY[0]}.{MIN_PY[1]}+ for the current user from python.org "
            '(check "Add python.exe to PATH"), open a new terminal, then run Open App.bat again.'
        )

    if _try_unix_python_install():
        system = _find_system_python()
        if system:
            _log(f"Python OK ({system})")
            return system

    webbrowser.open("https://www.python.org/downloads/")
    raise SystemExit(
        f"Install Python {MIN_PY[0]}.{MIN_PY[1]}+, then run ./Open\\ App.sh again."
    )


def _try_unix_python_install() -> bool:
    """Best-effort Python install on macOS (Homebrew) or Debian/Ubuntu (apt)."""
    system = platform.system()
    if system == "Darwin" and shutil.which("brew"):
        _log("Installing Python 3.12 with Homebrew...")
        try:
            subprocess.check_call(["brew", "install", "python@3.12"])
            return True
        except subprocess.CalledProcessError:
            return False
    if shutil.which("apt-get"):
        _log("Installing Python with apt (may ask for sudo)...")
        try:
            subprocess.check_call(["sudo", "apt-get", "update"])
            try:
                subprocess.check_call(
                    [
                        "sudo",
                        "apt-get",
                        "install",
                        "-y",
                        "python3.12",
                        "python3.12-venv",
                        "python3-pip",
                    ]
                )
            except subprocess.CalledProcessError:
                subprocess.check_call(
                    [
                        "sudo",
                        "apt-get",
                        "install",
                        "-y",
                        "python3",
                        "python3-venv",
                        "python3-pip",
                    ]
                )
            return True
        except subprocess.CalledProcessError:
            return False
    return False


def ensure_venv(system_python: Path) -> Path:
    venv_py = _venv_python()
    if venv_py:
        return venv_py
    _show_install_hero()
    _log("Creating backend virtual environment...")
    _run_with_spinner(
        "creating virtual environment",
        [str(system_python), "-m", "venv", str(BACKEND / ".venv")],
        ROOT,
    )
    venv_py = _venv_python()
    if not venv_py:
        raise SystemExit("Failed to create backend/.venv")
    _log("Virtual environment OK")
    return venv_py


def _marker_path() -> Path:
    return BACKEND / ".venv" / ".deps-installed"


def _deps_need_install() -> bool:
    marker = _marker_path()
    if not marker.exists():
        return True
    pyproject = BACKEND / "pyproject.toml"
    lock = BACKEND / "uv.lock"
    try:
        marker_mtime = marker.stat().st_mtime
        if pyproject.exists() and pyproject.stat().st_mtime > marker_mtime:
            return True
        if lock.exists() and lock.stat().st_mtime > marker_mtime:
            return True
    except OSError:
        return True
    return False


def ensure_backend_deps(venv_py: Path) -> None:
    if not _deps_need_install():
        _log("Dependencies OK")
        return
    _show_install_hero()
    _log("Installing packages (first launch can take a few minutes)...")
    _log("Grok motion uses the xAI HTTP API (works on PC, Mac, and Windows ARM).")
    uv = shutil.which("uv")
    if uv:
        _run_with_spinner("syncing packages with uv", [uv, "sync"], BACKEND)
    else:
        _run_with_spinner(
            "upgrading pip",
            [str(venv_py), "-m", "pip", "install", "--upgrade", "pip"],
            BACKEND,
        )
        # Prefer wheels so machines without MSVC do not try to compile.
        _run_with_spinner(
            "installing Campaign Pipeline packages",
            [
                str(venv_py),
                "-m",
                "pip",
                "install",
                "--prefer-binary",
                "-e",
                ".",
            ],
            BACKEND,
        )
        # Optional native SDK (grpcio). Nice-to-have on Intel/AMD; skip on Windows ARM.
        try:
            _run_with_spinner(
                "optional native xAI SDK (skipped automatically if unsupported)",
                [
                    str(venv_py),
                    "-m",
                    "pip",
                    "install",
                    "--prefer-binary",
                    "-e",
                    ".[motion]",
                ],
                BACKEND,
            )
        except subprocess.CalledProcessError:
            _log("  Native xAI SDK not installed on this machine.")
            _log("  Grok still works via HTTP when you add an XAI_API_KEY in Settings.")
    _marker_path().parent.mkdir(parents=True, exist_ok=True)
    _marker_path().write_text("ok\n", encoding="utf-8")
    _log("Dependencies OK")


def ensure_frontend_built() -> None:
    if (DIST / "index.html").exists():
        _log("UI ready")
        return
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    if not shutil.which("npm") and not shutil.which("npm.cmd"):
        raise SystemExit(
            "frontend/dist is missing and Node/npm was not found. "
            "Install Node.js 20+ from https://nodejs.org/ or restore frontend/dist."
        )
    _log("Building UI (first run)...")
    if not (FRONTEND / "node_modules").exists():
        subprocess.check_call([npm_cmd, "install"], cwd=FRONTEND)
    subprocess.check_call([npm_cmd, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Frontend build failed: dist/index.html missing")
    _log("UI ready")


def open_browser_when_ready() -> None:
    for _ in range(90):
        if _health_ok():
            webbrowser.open(LOCAL_URL)
            return
        time.sleep(0.25)
    webbrowser.open(LOCAL_URL)


def main() -> int:
    _setup_logging()
    _log("Herbie Creative Campaign Pipeline")
    if _health_ok():
        _log("App already running. Opening browser…")
        webbrowser.open(LOCAL_URL)
        return 0

    system_python = ensure_python()
    venv_py = _venv_python()
    if venv_py is None:
        venv_py = ensure_venv(system_python)

    ensure_backend_deps(venv_py)
    ensure_frontend_built()

    _log(f"Opening app at {LOCAL_URL}")
    lan = _lan_ip()
    if lan:
        _log(f"On your phone (same Wi-Fi): http://{lan}:{PORT}")
    _log("Server running in this window. Use Close App.bat / Close App.sh to stop.")
    _write_status("ready", LOCAL_URL)

    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    return subprocess.call(
        [
            str(venv_py),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=BACKEND,
    )


if __name__ == "__main__":
    raise SystemExit(main())
