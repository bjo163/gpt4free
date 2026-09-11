from __future__ import annotations

# ROCKSOUL · g4f Launcher
# Local-safe GUI + FastAPI/OpenAI-compatible API supervisor.
# Includes Windows-safe BLAS limits, FFmpeg bootstrap, health checks,
# bounded auto-restart, graceful shutdown, and structured supervisor logs.

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Prevent BLAS/OpenMP memory explosions when API reload spawns a child.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"
os.environ.setdefault("G4F_TIMEOUT", "30")
os.environ.setdefault("G4F_STREAM_TIMEOUT", "30")

RESET, BOLD = "\033[0m", "\033[1m"
CYAN, MAGENTA, GREEN = "\033[96m", "\033[95m", "\033[92m"
YELLOW, RED, BLUE, WHITE, GRAY = "\033[93m", "\033[91m", "\033[94m", "\033[97m", "\033[90m"

DEFAULT_HOST = "127.0.0.1"
LAN_HOST = "0.0.0.0"
GUI_PORT = 8080
API_PORT = 8081
TIMEOUT = 30
STREAM_TIMEOUT = 30
HEALTH_TIMEOUT = 30
HEALTH_INTERVAL = 1.0
RESTART_DELAY = 2.0
MAX_RESTARTS = 3

ROCKSOUL_HOME = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ROCKSOUL" / "g4f"
LOG_DIR = ROCKSOUL_HOME / "logs"
FFMPEG_HOME = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ROCKSOUL" / "ffmpeg"
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-lgpl.zip"
FFMPEG_CHECKSUM_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/checksums.sha256"


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
    health_timeout: int
    health_interval: float
    restart_delay: float
    max_restarts: int
    auto_install: bool
    no_color: bool
    quiet: bool
    log_dir: Path


@dataclass(slots=True)
class Managed:
    name: str
    process: subprocess.Popen[bytes]
    health_url: str
    restarts: int = 0


class C:
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


def label(c: C, text: str) -> str:
    return c.bold(c.blue(text.ljust(18)))


def ok(c: C) -> str:
    return c.bold(c.green("✓ OK"))


def warn(c: C) -> str:
    return c.bold(c.yellow("⚠ WARN"))


def fail(c: C) -> str:
    return c.bold(c.red("✖ FAIL"))


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb"


def g4f_version() -> str:
    try:
        return importlib.metadata.version("g4f")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def memory_info() -> str:
    try:
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        value = MemoryStatusEx()
        value.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            total = value.ullTotalPhys / 1024**3
            free = value.ullAvailPhys / 1024**3
            return f"{free:.1f} GB free / {total:.1f} GB ({value.dwMemoryLoad}% used)"
    except Exception:
        pass
    return "unavailable"


def log_event(log_dir: Path, event: str, **fields: object) -> None:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "pid": os.getpid(),
            **fields,
        }
        with (log_dir / "supervisor.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def find_ffmpeg() -> str | None:
    direct = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if direct:
        return str(Path(direct).resolve())

    candidates = [
        FFMPEG_HOME / "bin" / "ffmpeg.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
        Path(os.environ.get("USERPROFILE", "")) / "scoop" / "shims" / "ffmpeg.exe",
    ]

    packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if packages.is_dir():
        try:
            candidates.extend(packages.glob("**/ffmpeg.exe"))
        except OSError:
            pass

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def add_ffmpeg_to_path(ffmpeg: str | None) -> None:
    if not ffmpeg:
        return
    bin_dir = str(Path(ffmpeg).resolve().parent)
    path = os.environ.get("PATH", "")
    parts = path.split(os.pathsep)
    if bin_dir not in parts:
        os.environ["PATH"] = bin_dir + os.pathsep + path


def run_command(c: C, command: list[str], title: str, log_dir: Path | None = None) -> bool:
    print(f"  {c.yellow('▶')} {c.white(title)}")
    print(f"    {c.gray(' '.join(command))}")
    try:
        result = subprocess.run(command, check=False)
        if log_dir:
            log_event(log_dir, "command", title=title, returncode=result.returncode, command=command)
        return result.returncode == 0
    except OSError as exc:
        if log_dir:
            log_event(log_dir, "command_error", title=title, error=str(exc), command=command)
        print(f"    {c.red(str(exc))}")
        return False


def download(url: str, target: Path, c: C) -> None:
    print(f"  {c.yellow('▶')} {c.white('Downloading FFmpeg portable build')}")
    print(f"    {c.gray(url)}")
    request = urllib.request.Request(url, headers={"User-Agent": "ROCKSOUL-g4f-launcher"})
    with urllib.request.urlopen(request, timeout=120) as response:
        total = int(response.headers.get("Content-Length", "0"))
        done = 0
        with target.open("wb") as stream:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
                done += len(chunk)
                if total:
                    percent = done * 100 // total
                    print(f"\r    {percent:3d}% ({done / 1024**2:.1f}/{total / 1024**2:.1f} MB)", end="", flush=True)
    print()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(archive: Path, c: C) -> bool:
    try:
        with tempfile.TemporaryDirectory(prefix="rocksoul-check-") as temp:
            checksum_file = Path(temp) / "checksums.sha256"
            download(FFMPEG_CHECKSUM_URL, checksum_file, c)
            expected: str | None = None
            for raw in checksum_file.read_text(encoding="utf-8", errors="replace").splitlines():
                fields = raw.strip().split()
                if len(fields) >= 2 and fields[-1].lstrip("*").endswith(archive.name):
                    expected = fields[0].lower()
                    break
            if not expected:
                print(f"  {warn(c)} {c.yellow('FFmpeg checksum entry unavailable; skipping verification')}")
                return True
            actual = sha256(archive).lower()
            if actual != expected:
                print(f"  {fail(c)} {c.red('FFmpeg checksum mismatch')}")
                print(f"    expected: {expected}")
                print(f"    actual:   {actual}")
                return False
            print(f"  {label(c, 'FFMPEG CHECK')}{ok(c)}")
            return True
    except (OSError, urllib.error.URLError, ValueError) as exc:
        print(f"  {warn(c)} {c.yellow(f'Checksum verification unavailable: {exc}')}")
        return True


def install_portable_ffmpeg(c: C) -> str | None:
    existing = find_ffmpeg()
    if existing:
        add_ffmpeg_to_path(existing)
        return existing

    print(f"  {c.cyan('◆')} {c.cyan('FFmpeg missing → portable ROCKSOUL runtime')}")
    FFMPEG_HOME.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="rocksoul-ffmpeg-", dir=str(FFMPEG_HOME.parent)) as temp_dir:
        root = Path(temp_dir)
        archive = root / "ffmpeg-win64-lgpl.zip"
        extracted = root / "extracted"
        try:
            download(FFMPEG_URL, archive, c)
            if not verify_checksum(archive, c):
                return None
            print(f"  {c.yellow('▶')} {c.white('Extracting FFmpeg')}")
            extracted.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as source:
                source.extractall(extracted)
            binaries = list(extracted.glob("**/bin/ffmpeg.exe")) or list(extracted.glob("**/ffmpeg.exe"))
            if not binaries:
                print(f"  {fail(c)} {c.red('ffmpeg.exe not found inside downloaded archive')}")
                return None
            source_root = binaries[0].parent.parent
            if FFMPEG_HOME.exists():
                shutil.rmtree(FFMPEG_HOME, ignore_errors=True)
            shutil.copytree(source_root, FFMPEG_HOME, dirs_exist_ok=True)
        except (OSError, urllib.error.URLError, zipfile.BadZipFile) as exc:
            print(f"  {fail(c)} {c.red(f'Portable FFmpeg install failed: {exc}')}")
            return None

    found = find_ffmpeg()
    if found:
        add_ffmpeg_to_path(found)
        print(f"  {label(c, 'FFMPEG')}{c.green(found)} {ok(c)}")
        return found
    print(f"  {fail(c)} {c.red('FFmpeg installation completed but binary was not found')}")
    return None


def ensure_ffmpeg(c: C, auto_install: bool, log_dir: Path) -> str | None:
    existing = find_ffmpeg()
    if existing:
        add_ffmpeg_to_path(existing)
        return existing
    if not auto_install:
        return None

    winget = shutil.which("winget")
    if winget:
        run_command(c, [winget, "install", "--id", "Gyan.FFmpeg", "--exact", "--scope", "user", "--silent", "--accept-package-agreements", "--accept-source-agreements"], "Trying WinGet FFmpeg", log_dir)
        found = find_ffmpeg()
        if found:
            add_ffmpeg_to_path(found)
            return found
        print(f"  {warn(c)} {c.yellow('WinGet did not expose a usable ffmpeg.exe; using portable fallback')}")

    choco = shutil.which("choco")
    if choco:
        run_command(c, [choco, "install", "ffmpeg-full", "-y", "--no-progress"], "Trying Chocolatey FFmpeg", log_dir)
        found = find_ffmpeg()
        if found:
            add_ffmpeg_to_path(found)
            return found

    scoop = shutil.which("scoop")
    if scoop:
        run_command(c, [scoop, "install", "ffmpeg"], "Trying Scoop FFmpeg", log_dir)
        found = find_ffmpeg()
        if found:
            add_ffmpeg_to_path(found)
            return found

    found = install_portable_ffmpeg(c)
    if found:
        log_event(log_dir, "ffmpeg_ready", path=found)
    return found


def configure_environment(config: Config) -> None:
    os.environ["G4F_TIMEOUT"] = str(config.timeout)
    os.environ["G4F_STREAM_TIMEOUT"] = str(config.stream_timeout)
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    if config.debug:
        os.environ["G4F_DEBUG"] = "1"
        os.environ["FLASK_DEBUG"] = "1"
        os.environ["FLASK_ENV"] = "development"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rockg4f",
        description="ROCKSOUL supervisor for g4f GUI and Interference API",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("mode", nargs="?", choices=["gui", "api", "both", "doctor"], default="both")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-reload", action="store_true")
    parser.add_argument("--no-auto-install", action="store_true")
    parser.add_argument("--lan", action="store_true", help="Bind GUI and API to 0.0.0.0")
    parser.add_argument("--gui-host", default=None)
    parser.add_argument("--gui-port", type=int, default=GUI_PORT)
    parser.add_argument("--api-host", default=None)
    parser.add_argument("--api-port", type=int, default=API_PORT)
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    parser.add_argument("--stream-timeout", type=int, default=STREAM_TIMEOUT)
    parser.add_argument("--health-timeout", type=int, default=HEALTH_TIMEOUT)
    parser.add_argument("--health-interval", type=float, default=HEALTH_INTERVAL)
    parser.add_argument("--restart-delay", type=float, default=RESTART_DELAY)
    parser.add_argument("--max-restarts", type=int, default=MAX_RESTARTS)
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--log-dir", default=str(LOG_DIR))
    return parser.parse_args()


def make_config(args: argparse.Namespace) -> Config:
    gui_host = args.gui_host or (LAN_HOST if args.lan else DEFAULT_HOST)
    api_host = args.api_host or (LAN_HOST if args.lan else DEFAULT_HOST)
    if not 1 <= args.gui_port <= 65535 or not 1 <= args.api_port <= 65535:
        raise ValueError("Ports must be between 1 and 65535")
    if args.mode == "both" and args.gui_port == args.api_port:
        raise ValueError("GUI and API ports must be different in both mode")
    if args.timeout <= 0 or args.stream_timeout <= 0:
        raise ValueError("Timeout values must be greater than zero")
    if args.health_timeout <= 0 or args.health_interval <= 0:
        raise ValueError("Health values must be greater than zero")
    if args.restart_delay < 0 or args.max_restarts < 0:
        raise ValueError("Restart values cannot be negative")
    return Config(
        mode=args.mode,
        debug=bool(args.debug),
        reload=bool(args.debug and not args.no_reload),
        gui_host=gui_host,
        gui_port=args.gui_port,
        api_host=api_host,
        api_port=args.api_port,
        timeout=args.timeout,
        stream_timeout=args.stream_timeout,
        health_timeout=args.health_timeout,
        health_interval=args.health_interval,
        restart_delay=args.restart_delay,
        max_restarts=0 if args.no_restart else args.max_restarts,
        auto_install=not args.no_auto_install,
        no_color=args.no_color,
        quiet=args.quiet,
        log_dir=Path(args.log_dir).expanduser(),
    )


def port_available(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host == "localhost" else ("0.0.0.0" if host == "::" else host)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
            return True
    except OSError:
        return False


def health_check(url: str, timeout: float) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "ROCKSOUL-health/1"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (OSError, urllib.error.URLError):
        return False


def wait_for_health(managed: Managed, config: Config, c: C, log_dir: Path) -> bool:
    started = time.monotonic()
    while time.monotonic() - started < config.health_timeout:
        code = managed.process.poll()
        if code is not None:
            log_event(log_dir, "process_exit_during_health", service=managed.name, pid=managed.process.pid, returncode=code)
            return False
        if health_check(managed.health_url, min(config.health_interval, 3.0)):
            elapsed = time.monotonic() - started
            print(f"  {label(c, managed.name + ' HEALTH')}{ok(c)} {c.gray(f'{elapsed:.1f}s')}")
            log_event(log_dir, "health_ready", service=managed.name, pid=managed.process.pid, url=managed.health_url, seconds=round(elapsed, 2))
            return True
        time.sleep(config.health_interval)
    print(f"  {warn(c)} {c.yellow(f'{managed.name} health timeout: {managed.health_url}')}")
    log_event(log_dir, "health_timeout", service=managed.name, pid=managed.process.pid, url=managed.health_url)
    return False


def build_gui(config: Config) -> list[str]:
    command = [sys.executable, "-m", "g4f.cli", "gui", "--host", config.gui_host, "--port", str(config.gui_port)]
    if config.debug:
        command.append("--debug")
    return command


def build_api(config: Config) -> list[str]:
    command = [sys.executable, "-m", "g4f", "api", "--bind", f"{config.api_host}:{config.api_port}", "--no-gui", "--timeout", str(config.timeout), "--stream-timeout", str(config.stream_timeout)]
    if config.debug:
        command.append("--debug")
    if config.reload:
        command.append("--reload")
    return command


def start_process(name: str, command: list[str], health_url: str, c: C, log_dir: Path, restarts: int = 0) -> Managed:
    print(f"  {c.green('▶')} {c.white(f'Starting {name}')}")
    print(f"    {c.gray(' '.join(command))}")
    process = subprocess.Popen(command, cwd=str(Path.cwd()), env=os.environ.copy())
    print(f"    {label(c, 'PID')}{c.white(str(process.pid))}")
    log_event(log_dir, "process_start", service=name, pid=process.pid, command=command, restart_count=restarts)
    return Managed(name=name, process=process, health_url=health_url, restarts=restarts)


def stop_process(managed: Managed, c: C, reason: str = "shutdown") -> None:
    if managed.process.poll() is not None:
        return
    print(f"  {c.yellow('■')} {c.white(f'Stopping {managed.name}')}{c.gray(f' ({reason})')}")
    try:
        managed.process.terminate()
        managed.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        managed.process.kill()
    except OSError:
        pass


def stop_all(processes: list[Managed], c: C) -> None:
    for managed in reversed(processes):
        stop_process(managed, c)


def service_spec(name: str, config: Config) -> tuple[list[str], str]:
    if name == "GUI":
        return build_gui(config), f"http://127.0.0.1:{config.gui_port}/chat/"
    return build_api(config), f"http://127.0.0.1:{config.api_port}/docs"


def restart_service(index: int, processes: list[Managed], config: Config, c: C) -> bool:
    old = processes[index]
    if old.restarts >= config.max_restarts:
        print(f"  {fail(c)} {c.red(f'{old.name} restart budget exhausted ({old.restarts}/{config.max_restarts})')}")
        log_event(config.log_dir, "restart_exhausted", service=old.name, restart_count=old.restarts)
        return False
    stop_process(old, c, reason="restart")
    if config.restart_delay:
        time.sleep(config.restart_delay)
    command, health_url = service_spec(old.name, config)
    new = start_process(old.name, command, health_url, c, config.log_dir, old.restarts + 1)
    if not wait_for_health(new, config, c, config.log_dir):
        stop_process(new, c, reason="failed health")
        log_event(config.log_dir, "restart_failed", service=new.name, restart_count=new.restarts)
        processes[index] = new
        return False
    processes[index] = new
    print(f"  {c.green('↻')} {c.white(old.name)} {c.green('recovered')} {c.gray(f'(restart {new.restarts})')}")
    log_event(config.log_dir, "restart_success", service=new.name, restart_count=new.restarts)
    return True


def doctor(config: Config, c: C) -> int:
    ffmpeg = find_ffmpeg()
    checks = [
        ("PYTHON", sys.version.split()[0], True),
        ("G4F", g4f_version(), g4f_version() != "unknown"),
        ("FFMPEG", ffmpeg or "not found", ffmpeg is not None),
        (f"GUI PORT {config.gui_port}", "available" if port_available(config.gui_host, config.gui_port) else "busy", port_available(config.gui_host, config.gui_port)),
        (f"API PORT {config.api_port}", "available" if port_available(config.api_host, config.api_port) else "busy", port_available(config.api_host, config.api_port)),
    ]
    print()
    print(c.bold(c.magenta("  ROCKSOUL DOCTOR")))
    print()
    failed = False
    for name, value, passed in checks:
        print(f"  {label(c, name)}{c.green(str(value)) if passed else c.red(str(value))} {ok(c) if passed else fail(c)}")
        failed = failed or not passed
    print(f"  {label(c, 'MEMORY')}{memory_info()}")
    print(f"  {label(c, 'LOG DIR')}{config.log_dir}")
    log_event(config.log_dir, "doctor", passed=not failed, ffmpeg=ffmpeg, g4f=g4f_version())
    return 1 if failed else 0


def banner(config: Config, c: C, ffmpeg: str | None) -> None:
    if config.quiet:
        return
    print()
    print(c.cyan("  ╭────────────────────────────────────────────────────────╮"))
    print(c.cyan("  │") + "                " + c.magenta("ROCKSOUL") + c.gray(" · ") + c.cyan("g4f Supervisor") + "                 " + c.cyan("│"))
    print(c.cyan("  ╰────────────────────────────────────────────────────────╯"))
    print()
    print(c.bold(c.magenta("  RUNTIME")))
    print(f"  {label(c, 'MODE')}{c.cyan(config.mode.upper())}")
    print(f"  {label(c, 'DEBUG')}{c.green('● ON') if config.debug else c.gray('● OFF')}")
    print(f"  {label(c, 'API RELOAD')}{c.green('● ON') if config.reload else c.gray('● OFF')}")
    print(f"  {label(c, 'AUTO RESTART')}{c.green(f'● {config.max_restarts}') if config.max_restarts else c.gray('● OFF')}")
    print(f"  {label(c, 'PYTHON')}{platform.python_version()}")
    print(f"  {label(c, 'G4F')}{g4f_version()}")
    print(f"  {label(c, 'MEMORY')}{memory_info()}")
    print(f"  {label(c, 'FFMPEG')}{c.green(ffmpeg) if ffmpeg else c.yellow('NOT FOUND')}")
    print(f"  {label(c, 'LOGS')}{c.cyan(str(config.log_dir / 'supervisor.jsonl'))}")
    print()
    if config.mode in ("gui", "both"):
        print(c.bold(c.magenta("  GUI SERVER")))
        print(f"  {label(c, 'HOST')}{config.gui_host}")
        print(f"  {label(c, 'PORT')}{config.gui_port}")
        print(f"  {label(c, 'CHAT')}{c.cyan(f'http://127.0.0.1:{config.gui_port}/chat/')}")
        print()
    if config.mode in ("api", "both"):
        print(c.bold(c.magenta("  INTERFERENCE API")))
        print(f"  {label(c, 'HOST')}{config.api_host}")
        print(f"  {label(c, 'PORT')}{config.api_port}")
        print(f"  {label(c, 'BASE URL')}{c.cyan(f'http://127.0.0.1:{config.api_port}/v1')}")
        print(f"  {label(c, 'SWAGGER')}{c.cyan(f'http://127.0.0.1:{config.api_port}/docs')}")
        print(f"  {label(c, 'REDOC')}{c.cyan(f'http://127.0.0.1:{config.api_port}/redoc')}")
        print()
    print(c.bold(c.magenta("  PERFORMANCE")))
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        print(f"  {label(c, name.removesuffix('_NUM_THREADS'))}{c.green(os.environ[name])} threads")
    print()


def main() -> int:
    args = parse_args()
    colors = C(supports_color() and not args.no_color)
    processes: list[Managed] = []

    try:
        config = make_config(args)
        config.log_dir.mkdir(parents=True, exist_ok=True)
        configure_environment(config)
        log_event(config.log_dir, "launcher_start", mode=config.mode, debug=config.debug, reload=config.reload)

        if args.version:
            print(f"ROCKSOUL · g4f {g4f_version()} · Python {platform.python_version()}")
            return 0

        # Read-only checks never install or mutate FFmpeg/system state.
        if args.check or config.mode == "doctor":
            return doctor(config, colors)

        ffmpeg = ensure_ffmpeg(colors, config.auto_install, config.log_dir)
        if ffmpeg:
            add_ffmpeg_to_path(ffmpeg)

        if config.mode in ("gui", "both") and not port_available(config.gui_host, config.gui_port):
            print(f"\n  {fail(colors)} {colors.red(f'GUI port {config.gui_port} is busy')}")
            return 1
        if config.mode in ("api", "both") and not port_available(config.api_host, config.api_port):
            print(f"\n  {fail(colors)} {colors.red(f'API port {config.api_port} is busy')}")
            return 1

        banner(config, colors, ffmpeg)

        if config.mode in ("gui", "both"):
            managed = start_process("GUI", build_gui(config), f"http://127.0.0.1:{config.gui_port}/chat/", colors, config.log_dir)
            processes.append(managed)
        if config.mode in ("api", "both"):
            managed = start_process("API", build_api(config), f"http://127.0.0.1:{config.api_port}/docs", colors, config.log_dir)
            processes.append(managed)

        print()
        all_ready = True
        for managed in processes:
            if not wait_for_health(managed, config, colors, config.log_dir):
                all_ready = False
                break
        if not all_ready:
            stop_all(processes, colors)
            return 1

        print()
        print(f"  {label(colors, 'STATUS')}{colors.bold(colors.green('● READY'))}")
        for managed in processes:
            print(f"  {colors.magenta('➜')} {colors.cyan(managed.health_url)}")
        print()
        log_event(config.log_dir, "launcher_ready", services=[managed.name for managed in processes])

        while True:
            for index, managed in enumerate(processes):
                code = managed.process.poll()
                if code is None and health_check(managed.health_url, min(config.health_interval, 3.0)):
                    continue
                if code is not None:
                    print(f"\n  {warn(colors)} {colors.yellow(managed.name)} stopped with exit code {code}")
                    log_event(config.log_dir, "process_exit", service=managed.name, pid=managed.process.pid, returncode=code)
                else:
                    print(f"\n  {warn(colors)} {colors.yellow(managed.name)} became unhealthy")
                    log_event(config.log_dir, "health_lost", service=managed.name, pid=managed.process.pid, url=managed.health_url)
                if not restart_service(index, processes, config, colors):
                    stop_all(processes, colors)
                    return 1
            time.sleep(max(config.health_interval, 0.5))

    except KeyboardInterrupt:
        print(f"\n  {colors.yellow('● Shutdown requested')}")
        log_event(config.log_dir, "shutdown", reason="keyboard_interrupt")
        return 130
    except ValueError as exc:
        print(f"\n  {fail(colors)} {colors.red(str(exc))}")
        return 2
    except Exception as exc:
        print(f"\n  {fail(colors)} {colors.red(f'Launcher error: {exc}')}")
        try:
            log_event(config.log_dir, "launcher_error", error=str(exc))
        except UnboundLocalError:
            pass
        return 1
    finally:
        if processes:
            stop_all(processes, colors)
            try:
                log_event(config.log_dir, "launcher_stop")
            except UnboundLocalError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
