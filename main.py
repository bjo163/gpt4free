from __future__ import annotations

# ============================================================
# ROCKSOUL · g4f LAUNCHER
# Process safety + dependency bootstrap + GUI/API supervisor.
# ============================================================

import argparse
import ctypes
import importlib.metadata
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ.setdefault("G4F_TIMEOUT", "30")
os.environ.setdefault("G4F_STREAM_TIMEOUT", "30")

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
WHITE = "\033[97m"
GRAY = "\033[90m"

APP_TITLE = "ROCKSOUL · g4f Launcher"
DEFAULT_GUI_HOST = "0.0.0.0"
DEFAULT_GUI_PORT = 8080
DEFAULT_API_HOST = "0.0.0.0"
DEFAULT_API_PORT = 8081
DEFAULT_TIMEOUT = 30
DEFAULT_STREAM_TIMEOUT = 30
WIDTH = 58
LABEL = 18

@dataclass(slots=True)
class Config:
    mode: str
    debug: bool
    reload: bool
    gui_host: str
    gui_port: int
    api_host: str
    api_port: int
    timeout: int
    stream_timeout: int
    color: bool
    quiet: bool
    auto_install: bool

@dataclass(slots=True)
class ManagedProcess:
    name: str
    process: subprocess.Popen[str]

class Colors:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
    def __call__(self, text: str, color: str) -> str:
        return f"{color}{text}{RESET}" if self.enabled else text
    def bold(self, text: str) -> str: return self(text, BOLD)
    def cyan(self, text: str) -> str: return self(text, CYAN)
    def magenta(self, text: str) -> str: return self(text, MAGENTA)
    def green(self, text: str) -> str: return self(text, GREEN)
    def yellow(self, text: str) -> str: return self(text, YELLOW)
    def red(self, text: str) -> str: return self(text, RED)
    def blue(self, text: str) -> str: return self(text, BLUE)
    def white(self, text: str) -> str: return self(text, WHITE)
    def gray(self, text: str) -> str: return self(text, GRAY)

def supports_color() -> bool:
    return os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb" and sys.stdout.isatty()

def slabel(c: Colors, text: str) -> str:
    return c.bold(c.blue(text.ljust(LABEL)))

def ok(c: Colors) -> str: return c.bold(c.green("✓ OK"))
def warn(c: Colors) -> str: return c.bold(c.yellow("⚠ WARN"))
def fail(c: Colors) -> str: return c.bold(c.red("✖ FAIL"))
def rule(c: Colors) -> None: print(c.cyan("  " + ("─" * WIDTH)))

def get_g4f_version() -> str:
    try:
        return importlib.metadata.version("g4f")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"

def get_memory() -> str:
    try:
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        value = MemoryStatusEx()
        value.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            total = value.ullTotalPhys / 1024**3
            free = value.ullAvailPhys / 1024**3
            return f"{free:.1f} GB free / {total:.1f} GB ({value.dwMemoryLoad}% used)"
    except Exception:
        pass
    return "unavailable"

def find_ffmpeg() -> str | None:
    direct = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if direct:
        return direct
    local_links = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
    for name in ("ffmpeg.exe", "ffmpeg"):
        candidate = local_links / name
        if candidate.is_file():
            return str(candidate)
    scoop = Path(os.environ.get("USERPROFILE", "")) / "scoop" / "shims" / "ffmpeg.exe"
    return str(scoop) if scoop.is_file() else None

def run_installer(c: Colors, command: list[str], label: str) -> bool:
    print(f"  {c.yellow('▶')} {c.white(f'Installing {label}')}")
    print(f"    {c.gray(' '.join(command))}")
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        print(f"    {c.red(str(exc))}")
        return False
    return result.returncode == 0

def auto_install_ffmpeg(c: Colors) -> str | None:
    existing = find_ffmpeg()
    if existing:
        return existing
    print(f"  {c.yellow('⚠')} {c.yellow('FFmpeg not found; attempting automatic install')}")
    winget = shutil.which("winget")
    if winget:
        command = [winget, "install", "--id", "Gyan.FFmpeg", "--exact", "--silent", "--accept-package-agreements", "--accept-source-agreements"]
        if run_installer(c, command, "FFmpeg via WinGet"):
            found = find_ffmpeg()
            if found:
                print(f"  {slabel(c, 'FFMPEG')}{c.green(found)} {ok(c)}")
                return found
    choco = shutil.which("choco")
    if choco:
        command = [choco, "install", "ffmpeg-full", "-y", "--no-progress"]
        if run_installer(c, command, "FFmpeg via Chocolatey"):
            found = find_ffmpeg()
            if found:
                print(f"  {slabel(c, 'FFMPEG')}{c.green(found)} {ok(c)}")
                return found
    scoop = shutil.which("scoop")
    if scoop:
        command = [scoop, "install", "ffmpeg"]
        if run_installer(c, command, "FFmpeg via Scoop"):
            found = find_ffmpeg()
            if found:
                print(f"  {slabel(c, 'FFMPEG')}{c.green(found)} {ok(c)}")
                return found
    print(f"  {slabel(c, 'FFMPEG')}{c.yellow('still not found')} {warn(c)}")
    return None

def configure_environment(config: Config) -> None:
    os.environ["G4F_TIMEOUT"] = str(config.timeout)
    os.environ["G4F_STREAM_TIMEOUT"] = str(config.stream_timeout)
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"
    if config.debug:
        os.environ["G4F_DEBUG"] = "1"
        os.environ["FLASK_DEBUG"] = "1"
        os.environ["FLASK_ENV"] = "development"

def is_port_available(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host == "localhost" else host
    if bind_host == "::": bind_host = "0.0.0.0"
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_host, port))
        return True
    except OSError:
        return False
    finally:
        if sock is not None: sock.close()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="rockg4f", description="ROCKSOUL launcher for g4f GUI and Interference API", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("mode", nargs="?", choices=["gui", "api", "both"], default="both")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode and API auto reload")
    parser.add_argument("--no-reload", action="store_true", help="Disable API auto reload")
    parser.add_argument("--no-auto-install", action="store_true", help="Do not auto-install missing FFmpeg")
    parser.add_argument("--gui-host", default=DEFAULT_GUI_HOST)
    parser.add_argument("--gui-port", type=int, default=DEFAULT_GUI_PORT)
    parser.add_argument("--api-host", default=DEFAULT_API_HOST)
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--stream-timeout", type=int, default=DEFAULT_STREAM_TIMEOUT)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--version", action="store_true")
    return parser.parse_args()

def make_config(args: argparse.Namespace) -> Config:
    if not 1 <= args.gui_port <= 65535 or not 1 <= args.api_port <= 65535: raise ValueError("Ports must be between 1 and 65535")
    if args.mode == "both" and args.gui_port == args.api_port: raise ValueError("GUI and API ports must be different in both mode")
    if args.timeout <= 0 or args.stream_timeout <= 0: raise ValueError("Timeout values must be greater than zero")
    debug = bool(args.debug)
    return Config(args.mode, debug, debug and not args.no_reload, args.gui_host, args.gui_port, args.api_host, args.api_port, args.timeout, args.stream_timeout, supports_color() and not args.no_color, args.quiet, not args.no_auto_install)

def build_gui_command(config: Config) -> list[str]:
    command = [sys.executable, "-m", "g4f.cli", "gui", "--host", config.gui_host, "--port", str(config.gui_port)]
    if config.debug: command.append("--debug")
    return command

def build_api_command(config: Config) -> list[str]:
    command = [sys.executable, "-m", "g4f", "api", "--bind", f"{config.api_host}:{config.api_port}", "--no-gui", "--timeout", str(config.timeout), "--stream-timeout", str(config.stream_timeout)]
    if config.debug: command.append("--debug")
    if config.reload: command.append("--reload")
    return command

def start(name: str, command: list[str], config: Config, c: Colors) -> ManagedProcess:
    print(f"  {c.green('▶')} {c.white(f'Starting {name}')}")
    if config.debug: print(f"    {c.gray(' '.join(command))}")
    process = subprocess.Popen(command, cwd=str(Path.cwd()), env=os.environ.copy())
    print(f"    {slabel(c, 'PID')}{c.white(str(process.pid))}")
    return ManagedProcess(name, process)

def stop_all(processes: list[ManagedProcess], c: Colors) -> None:
    for item in reversed(processes):
        if item.process.poll() is None:
            print(f"  {c.yellow('■')} {c.white(f'Stopping {item.name}')} {c.gray(f'(PID {item.process.pid})')}")
            try:
                item.process.terminate(); item.process.wait(timeout=5)
            except subprocess.TimeoutExpired: item.process.kill()
            except OSError: pass

def banner(config: Config, c: Colors, ffmpeg: str | None) -> None:
    if config.quiet: return
    inner = WIDTH - 2; title = "ROCKSOUL · g4f Launcher"; padding = max(2, inner - len(title)); left = padding // 2; right = padding - left
    print(); print(c.cyan("  ╭" + "─" * inner + "╮")); print(c.cyan("  │") + " " * left + c.magenta("ROCKSOUL") + c.gray(" · ") + c.cyan("g4f Launcher") + " " * right + c.cyan("│")); print(c.cyan("  ╰" + "─" * inner + "╯")); print()
    print(c.bold(c.magenta("  MODE"))); print(f"  {slabel(c,'MODE')}{c.cyan(config.mode.upper())}"); print(f"  {slabel(c,'DEBUG')}{c.green('● ON') if config.debug else c.gray('● OFF')}"); print(f"  {slabel(c,'API RELOAD')}{c.green('● ON') if config.reload else c.gray('● OFF')}")
    if config.mode in ("gui", "both"): print(f"  {slabel(c,'GUI RELOAD')}{c.gray('● OFF (official runner)')}")
    print()
    if config.mode in ("gui", "both"): print(c.bold(c.magenta("  GUI SERVER"))); print(f"  {slabel(c,'HOST')}{c.white(config.gui_host)}"); print(f"  {slabel(c,'PORT')}{c.white(str(config.gui_port))}"); print(f"  {slabel(c,'CHAT')}{c.cyan(f'http://127.0.0.1:{config.gui_port}/chat/')}"); print()
    if config.mode in ("api", "both"): print(c.bold(c.magenta("  INTERFERENCE API"))); print(f"  {slabel(c,'HOST')}{c.white(config.api_host)}"); print(f"  {slabel(c,'PORT')}{c.white(str(config.api_port))}"); print(f"  {slabel(c,'BASE URL')}{c.cyan(f'http://127.0.0.1:{config.api_port}/v1')}"); print(f"  {slabel(c,'SWAGGER')}{c.cyan(f'http://127.0.0.1:{config.api_port}/docs')}"); print(f"  {slabel(c,'REDOC')}{c.cyan(f'http://127.0.0.1:{config.api_port}/redoc')}"); print()
    print(c.bold(c.magenta("  RUNTIME"))); print(f"  {slabel(c,'PYTHON')}{c.white(platform.python_version())}"); print(f"  {slabel(c,'G4F')}{c.white(get_g4f_version())}"); print(f"  {slabel(c,'TIMEOUT')}{c.yellow(f'{config.timeout}s')}"); print(f"  {slabel(c,'STREAM TIMEOUT')}{c.yellow(f'{config.stream_timeout}s')}"); print(f"  {slabel(c,'MEMORY')}{c.white(get_memory())}"); print()
    print(c.bold(c.magenta("  PERFORMANCE")))
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"): print(f"  {slabel(c,name.removesuffix('_NUM_THREADS'))}{c.green(os.environ[name])}{c.gray(' threads')}")
    print(); print(c.bold(c.magenta("  DEPENDENCIES"))); print(f"  {slabel(c,'FFMPEG')}{c.green(ffmpeg) + ' ' + ok(c) if ffmpeg else c.yellow('NOT FOUND') + ' ' + warn(c)}"); print(); rule(c); print()

def diagnostics(config: Config, c: Colors, ffmpeg: str | None) -> bool:
    print(); print(c.bold(c.magenta("ROCKSOUL · Diagnostics"))); print(); print(f"  {slabel(c,'G4F')}{c.green(get_g4f_version())} {ok(c)}"); print(f"  {slabel(c,'PYTHON')}{c.white(platform.python_version())} {ok(c)}"); print(f"  {slabel(c,'MEMORY')}{c.white(get_memory())}"); print(f"  {slabel(c,'OPENBLAS')}{c.green(os.environ['OPENBLAS_NUM_THREADS'])}"); print(f"  {slabel(c,'OMP')}{c.green(os.environ['OMP_NUM_THREADS'])}"); print(f"  {slabel(c,'FFMPEG')}{c.green(ffmpeg) + ' ' + ok(c) if ffmpeg else c.yellow('not found') + ' ' + warn(c)}")
    all_ok = ffmpeg is not None
    targets = []
    if config.mode in ("gui", "both"): targets.append(("GUI", config.gui_host, config.gui_port))
    if config.mode in ("api", "both"): targets.append(("API", config.api_host, config.api_port))
    for name, host, port in targets:
        available = is_port_available(host, port); print(f"  {slabel(c,name + ' PORT')}{c.green(str(port)) if available else c.red(str(port))} {ok(c) if available else fail(c)}"); all_ok = all_ok and available
    print(); print(f"  {c.green('✓ Diagnostics passed.') if all_ok else c.yellow('⚠ Diagnostics completed with warnings/errors.')}"); print(); return all_ok

def wait_processes(processes: list[ManagedProcess], c: Colors) -> int:
    while True:
        for item in processes:
            code = item.process.poll()
            if code is not None:
                print(f"\n  {c.red('✖')} {c.red(item.name)} {c.white('stopped with exit code')} {c.red(str(code))}")
                return int(code)
        time.sleep(0.5)

def main() -> int:
    args = parse_args(); c = Colors(supports_color() and not args.no_color); processes: list[ManagedProcess] = []
    try:
        config = make_config(args); configure_environment(config)
        if args.version:
            print(f"{APP_TITLE} · g4f {get_g4f_version()} · Python {platform.python_version()}"); return 0
        ffmpeg = find_ffmpeg()
        if ffmpeg is None and config.auto_install: ffmpeg = auto_install_ffmpeg(c)
        if args.check: return 0 if diagnostics(config, c, ffmpeg) else 1
        targets = []
        if config.mode in ("gui", "both"): targets.append(("GUI", config.gui_host, config.gui_port))
        if config.mode in ("api", "both"): targets.append(("API", config.api_host, config.api_port))
        for name, host, port in targets:
            if not is_port_available(host, port): print(f"  {fail(c)} {c.red(f'{name} port {port} is busy')}"); return 1
        banner(config, c, ffmpeg)
        if config.mode in ("gui", "both"): processes.append(start("GUI", build_gui_command(config), config, c))
        if config.mode in ("api", "both"): processes.append(start("API", build_api_command(config), config, c))
        print(); rule(c); print(); print(f"  {slabel(c,'STATUS')}{c.bold(c.green('● RUNNING'))}")
        if config.mode in ("gui", "both"): print(f"  {c.magenta('➜')} {c.cyan(f'GUI    http://127.0.0.1:{config.gui_port}/chat/')}")
        if config.mode in ("api", "both"):
            print(f"  {c.magenta('➜')} {c.cyan(f'API    http://127.0.0.1:{config.api_port}/v1')}"); print(f"  {c.magenta('➜')} {c.cyan(f'DOCS   http://127.0.0.1:{config.api_port}/docs')}"); print(f"  {c.magenta('➜')} {c.cyan(f'REDOC  http://127.0.0.1:{config.api_port}/redoc')}")
        print(); return wait_processes(processes, c)
    except KeyboardInterrupt:
        print(f"\n  {c.yellow('● Shutdown requested.')}"); return 130
    except (ValueError, OSError) as exc:
        print(f"\n  {fail(c)} {c.red(str(exc))}"); return 1
    finally: stop_all(processes, c)

if __name__ == "__main__": raise SystemExit(main())
