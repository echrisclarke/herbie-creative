"""Open an OS terminal and run the bare CLI sample."""
from __future__ import annotations

import os
import platform
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from app.config import PROJECT_ROOT

BACKEND = PROJECT_ROOT / "backend"
SMOKE_BRIEF = "sample-briefs/jordan-hero-zoom.json"
CLI_MODULE = "app.cli"


def resolve_backend_python() -> Path:
    win = BACKEND / ".venv" / "Scripts" / "python.exe"
    unix = BACKEND / ".venv" / "bin" / "python"
    if win.exists():
        return win
    if unix.exists():
        return unix
    return Path(sys.executable)


def smoke_command_parts() -> list[str]:
    return [
        str(resolve_backend_python()),
        "-m",
        CLI_MODULE,
        "smoke",
    ]


def smoke_command_display() -> str:
    parts = smoke_command_parts()
    if platform.system() == "Windows":
        return subprocess.list2cmdline(parts)
    return " ".join(shlex.quote(p) for p in parts)


# Christian: deprecated aliases from when this was named "assignment" not "smoke".
# Nothing imports these anymore; left so old notes do not break. Harmless.
assignment_command_parts = smoke_command_parts
assignment_command_display = smoke_command_display


def _win_quote(path: Path | str) -> str:
    """Quote a path for a .cmd file (spaces, commas, ampersands)."""
    text = str(path)
    return '"' + text.replace('"', '""') + '"'


def _write_windows_runner(cmd: list[str]) -> Path:
    """Write a .cmd runner so nested CreateProcess quoting cannot break paths."""
    py, *args = cmd
    lines = [
        "@echo off",
        "setlocal",
        "title Herbie Creative Campaign Pipeline - local CLI",
        f"cd /d {_win_quote(BACKEND)}",
        "if errorlevel 1 (",
        "  echo Could not open project folder:",
        f"  echo {_win_quote(BACKEND)}",
        "  pause",
        "  exit /b 1",
        ")",
        f"{_win_quote(py)} {' '.join(args)}",
        "set EXITCODE=%ERRORLEVEL%",
        "echo.",
        "if not %EXITCODE%==0 echo Local CLI exited with code %EXITCODE%.",
        "pause",
        "endlocal",
        "exit /b %EXITCODE%",
    ]
    fd, name = tempfile.mkstemp(prefix="herbie-cli-sample-", suffix=".cmd")
    os.close(fd)
    path = Path(name)
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return path


def _write_unix_runner(cmd: list[str]) -> Path:
    script = (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f"cd {shlex.quote(str(BACKEND))}\n"
        f"{' '.join(shlex.quote(p) for p in cmd)}\n"
        "status=$?\n"
        "echo\n"
        "if [ \"$status\" -ne 0 ]; then echo \"Local CLI exited with code $status.\"; fi\n"
        "read -n 1 -s -r -p 'Press any key to close...'\n"
        "exit \"$status\"\n"
    )
    fd, name = tempfile.mkstemp(prefix="herbie-cli-sample-", suffix=".sh")
    os.close(fd)
    path = Path(name)
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o755)
    return path


def _launch_windows(cmd: list[str]) -> None:
    runner = _write_windows_runner(cmd)
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
    subprocess.Popen(
        ["cmd.exe", "/k", str(runner)],
        cwd=str(BACKEND),
        creationflags=flags,
        env={**os.environ},
    )


def _launch_macos(cmd: list[str]) -> None:
    runner = _write_unix_runner(cmd)
    applescript = f'tell application "Terminal" to do script {shlex.quote(str(runner))}'
    subprocess.Popen(["osascript", "-e", applescript], env={**os.environ})


def _launch_linux(cmd: list[str]) -> None:
    runner = _write_unix_runner(cmd)
    shell_line = shlex.quote(str(runner))
    candidates: list[list[str]] = [
        ["gnome-terminal", "--", str(runner)],
        ["konsole", "-e", str(runner)],
        ["xfce4-terminal", "-e", str(runner)],
        ["x-terminal-emulator", "-e", str(runner)],
        ["xterm", "-hold", "-e", str(runner)],
        ["bash", "-lc", shell_line],
    ]
    last_err: Exception | None = None
    for argv in candidates:
        try:
            subprocess.Popen(argv, cwd=str(BACKEND), env={**os.environ})
            return
        except FileNotFoundError as exc:
            last_err = exc
            continue
    raise RuntimeError(
        "No graphical terminal found. Run this yourself:\n"
        f"  cd {BACKEND}\n"
        f"  {smoke_command_display()}"
    ) from last_err


def launch_assignment_terminal() -> dict:
    """Open a terminal and run the local CLI (Jordan hero zoom)."""
    if not (PROJECT_ROOT / SMOKE_BRIEF).exists():
        raise FileNotFoundError(f"Local CLI brief missing: {SMOKE_BRIEF}")

    cmd = smoke_command_parts()
    if not Path(cmd[0]).exists():
        return {
            "ok": False,
            "error": f"Python not found: {cmd[0]}",
            "command": smoke_command_display(),
            "cwd": str(BACKEND),
            "brief": SMOKE_BRIEF,
        }

    system = platform.system()
    try:
        if system == "Windows":
            _launch_windows(cmd)
        elif system == "Darwin":
            _launch_macos(cmd)
        else:
            _launch_linux(cmd)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "command": smoke_command_display(),
            "cwd": str(BACKEND),
            "brief": SMOKE_BRIEF,
        }

    return {
        "ok": True,
        "command": smoke_command_display(),
        "cwd": str(BACKEND),
        "brief": SMOKE_BRIEF,
        "message": "Opened a terminal for the local CLI run.",
    }
