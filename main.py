from __future__ import annotations

# ROCKSOUL · g4f Launcher
# GUI + FastAPI/OpenAI-compatible API supervisor.
# Includes Windows-safe BLAS limits and automatic FFmpeg bootstrap.

import argparse
import ctypes
import hashlib
import importlib.metadata
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
from pathlib import Path

# Prevent BLAS/OpenMP memory explosions when API reload spawns a child.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"
os.environ.setdefault("G4F_TIMEOUT", "30")
os.environ.setdefault("G4F_STREAM_TIMEOUT", "30")

RESET, BOLD = "\033[0m", "\033[1m"
CYAN, MAGENTA, GREEN = "\033[96m", "\033[95m", "\033[92m"
YELLOW, RED, BLUE, WHITE, GRAY = "\033[93m", "\033[91m", "\033[94m", "\033[97m", "\033[90m"

GUI_HOST = "0.0.0.0"
GUI_PORT = 8080
API_HOST = "0.0.0.0"
API_PORT = 8081
TIMEOUT = 30
STREAM_TIMEOUT = 30

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
    auto_install: bool
    no_color: bool
    quiet: bool


@dataclass(slots=True)
class Managed:
    name: str
    process: subprocess.Popen[bytes]


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


def run_command(c: C, command: list[str], title: str) -> bool:
    print(f"  {c.yellow('▶')} {c.white(title)}")
    print(f"    {c.gray(' '.join(command))}")
    try:
        result = subprocess.run(command, check=False)
        return result.returncode == 0
    except OSError as exc:
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


def ensure_ffmpeg(c: C, auto_install: bool) -> str | None:
    existing = find_ffmpeg()
    if existing:
        add_ffmpeg_to_path(existing)
        return existing
    if not auto_install:
        return None

    winget = shutil.which("winget")
    if winget:
        run_command(c, [winget, "install", "--id", "Gyan.FFmpeg", "--exact", "--scope", "user", "--silent", "--accept-package-agreements", "--accept-source-agreements"], "Trying WinGet FFmpeg")
        found = find_ffmpeg()
        if found:
            add_ffmpeg_to_path(found)
            return found
        print(f"  {warn(c)} {c.yellow('WinGet did not expose a usable ffmpeg.exe; using portable fallback')}")

    choco = shutil.which("choco")
    if choco:
        run_command(c, [choco, "install", "ffmpeg-full", "-y", "--no-progress"], "Trying Chocolatey FFmpeg")
        found = find_ffmpeg()
        if found:
            add_ffmpeg_to_path(found)
            return found

    scoop = shutil.which("scoop")
    if scoop:
        run_command(c, [scoop, "install", "ffmpeg"], "Trying Scoop FFmpeg")
        found = find_ffmpeg()
        if found:
            add_ffmpeg_to_path(found)
            return found

    return install_portable_ffmpeg(c)


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
        description="ROCKSOUL launcher for g4f GUI and Interference API",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("mode", nargs="?", choices=["gui", "api", "both"], default="both")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-reload", action="store_true")
    parser.add_argument("--no-auto-install", action="store_true")
    parser.add_argument("--gui-host", default=GUI_HOST)
    parser.add_argument("--gui-port", type=int, default=GUI_PORT)
    parser.add_argument("--api-host", default=API_HOST)
    parser.add_argument("--api-port", type=int, default=API_PORT)
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    parser.add_argument("--stream-timeout", type=int, default=STREAM_TIMEOUT)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--version", action="store_true")
    return parser.parse_args()


def make_config(args: argparse.Namespace) -> Config:
    if not 1 <= args.gui_port <= 65535 or not 1 <= args.api_port <= 65535:
        raise ValueError("Ports must be between 1 and 65535")
    if args.mode == "both" and args.gui_port == args.api_port:
        raise ValueError("GUI and API ports must be different in both mode")
    if args.timeout <= 0 or args.stream_timeout <= 0:
        raise ValueError("Timeout values must be greater than zero")
    debug = bool(args.debug)
    return Config(
        mode=args.mode,
        debug=debug,
        reload=debug and not args.no_reload,
        gui_host=args.gui_host,
        gui_port=args.gui_port,
        api_host=args.api_host,
        api_port=args.api_port,
        timeout=args.timeout,
        stream_timeout=args.stream_timeout,
        auto_install=not args.no_auto_install,
        no_color=args.no_color,
        quiet=args.quiet,
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


def start_process(name: str, command: list[str], c: C) -> Managed:
    print(f"  {c.green('▶')} {c.white(f'Starting {name}')}")
    print(f"    {c.gray(' '.join(command))}")
    process = subprocess.Popen(command, cwd=str(Path.cwd()), env=os.environ.copy())
    print(f"    {label(c, 'PID')}{c.white(str(process.pid))}")
    return Managed(name, process)


def stop_all(processes: list[Managed], c: C) -> None:
    for managed in reversed(processes):
        if managed.process.poll() is not None:
            continue
        print(f"  {c.yellow('■')} {c.white(f'Stopping {managed.name}')} {c.gray(f'(PID {managed.process.pid})')}")
        try:
            managed.process.terminate()
            managed.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            managed.process.kill()
        except OSError:
            pass


def banner(config: Config, c: C, ffmpeg: str | None) -> None:
    if config.quiet:
        return
    print()
    print(c.cyan("  ╭────────────────────────────────────────────────────────╮"))
    print(c.cyan("  │") + "                " + c.magenta("ROCKSOUL") + c.gray(" · ") + c.cyan("g4f Launcher") + "                 " + c.cyan("│"))
    print(c.cyan("  ╰────────────────────────────────────────────────────────╯"))
    print()
    print(c.bold(c.magenta("  MODE")))
    print(f"  {label(c, 'MODE')}{c.cyan(config.mode.upper())}")
    print(f"  {label(c, 'DEBUG')}{c.green('● ON') if config.debug else c.gray('● OFF')}")
    print(f"  {label(c, 'API RELOAD')}{c.green('● ON') if config.reload else c.gray('● OFF')}")
    if config.mode in ("gui", "both"):
        print(f"  {label(c, 'GUI RELOAD')}{c.gray('● OFF (official runner)')}")
    print()
    if config.mode in ("gui", "both"):
        print(c.bold(c.magenta("  GUI SERVER")))
        print(f"  {label(c, 'HOST')}{c.white(config.gui_host)}")
        print(f"  {label(c, 'PORT')}{c.white(str(config.gui_port))}")
        print(f"  {label(c, 'CHAT')}{c.cyan(f'http://127.0.0.1:{config.gui_port}/chat/')}")
        print()
    if config.mode in ("api", "both"):
        print(c.bold(c.magenta("  INTERFERENCE API")))
        print(f"  {label(c, 'HOST')}{c.white(config.api_host)}")
        print(f"  {label(c, 'PORT')}{c.white(str(config.api_port))}")
        print(f"  {label(c, 'BASE URL')}{c.cyan(f'http://127.0.0.1:{config.api_port}/v1')}")
        print(f"  {label(c, 'SWAGGER')}{c.cyan(f'http://127.0.0.1:{config.api_port}/docs')}")
        print(f"  {label(c, 'REDOC')}{c.cyan(f'http://127.0.0.1:{config.api_port}/redoc')}")
        print()
    print(c.bold(c.magenta("  RUNTIME")))
    print(f"  {label(c, 'PYTHON')}{c.white(platform.python_version())}")
    print(f"  {label(c, 'G4F')}{c.white(g4f_version())}")
    print(f"  {label(c, 'TIMEOUT')}{c.yellow(f'{config.timeout}s')}")
    print(f"  {label(c, 'STREAM TIMEOUT')}{c.yellow(f'{config.stream_timeout}s')}")
    print(f"  {label(c, 'MEMORY')}{c.white(memory_info())}")
    print()
    print(c.bold(c.magenta("  PERFORMANCE")))
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        print(f"  {label(c, name.removesuffix('_NUM_THREADS'))}{c.green(os.environ[name])}{c.gray(' threads')}")
    print()
    print(c.bold(c.magenta("  DEPENDENCIES")))
    if ffmpeg:
        print(f"  {label(c, 'FFMPEG')}{c.green(ffmpeg)} {ok(c)}")
    else:
        print(f"  {label(c, 'FFMPEG')}{c.yellow('NOT FOUND')} {warn(c)}")
    print()
    print(c.cyan("  " + "─" * 58))
    print()
    print(f"  {label(c, 'STATUS')}{c.bold(c.green('● READY'))}")
    if config.debug and config.reload:
        print(f"  {c.green('✓')} {c.white('Development mode')} {c.gray('·')} {c.green('API debug + auto reload enabled')}")
    if config.mode in ("gui", "both"):
        print(f"  {c.gray('•')} {c.gray('GUI uses g4f official runner · no reload flag')}")
    if not ffmpeg:
        print(f"  {c.yellow('⚠')} {c.yellow('FFmpeg unavailable · audio features may be limited')}")
    print()


def main() -> int:
    args = parse_args()
    colors = C(supports_color() and not args.no_color)
    processes: list[Managed] = []

    try:
        config = make_config(args)
        configure_environment(config)

        if args.version:
            print(f"ROCKSOUL · g4f {g4f_version()} · Python {platform.python_version()}")
            return 0

        ffmpeg = ensure_ffmpeg(colors, config.auto_install)
        if ffmpeg:
            add_ffmpeg_to_path(ffmpeg)

        if args.check:
            print()
            print(f"{label(colors, 'G4F')}{g4f_version()} {ok(colors) if g4f_version() != 'unknown' else fail(colors)}")
            print(f"{label(colors, 'PYTHON')}{platform.python_version()} {ok(colors)}")
            print(f"{label(colors, 'MEMORY')}{memory_info()}")
            print(f"{label(colors, 'FFMPEG')}{ffmpeg or 'not found'}")
            return 0

        if config.mode in ("gui", "both") and not port_available(config.gui_host, config.gui_port):
            print(f"\n  {fail(colors)} {colors.red(f'GUI port {config.gui_port} is busy')}")
            return 1

        if config.mode in ("api", "both") and not port_available(config.api_host, config.api_port):
            print(f"\n  {fail(colors)} {colors.red(f'API port {config.api_port} is busy')}")
            return 1

        banner(config, colors, ffmpeg)

        if config.mode in ("gui", "both"):
            processes.append(start_process("GUI", build_gui(config), colors))
        if config.mode in ("api", "both"):
            processes.append(start_process("API", build_api(config), colors))

        print()
        print(f"  {label(colors, 'STATUS')}{colors.bold(colors.green('● RUNNING'))}")
        if config.mode in ("gui", "both"):
            print(f"  {colors.magenta('➜')} {colors.cyan(f'GUI    http://127.0.0.1:{config.gui_port}/chat/')}")
        if config.mode in ("api", "both"):
            print(f"  {colors.magenta('➜')} {colors.cyan(f'API    http://127.0.0.1:{config.api_port}/v1')}")
            print(f"  {colors.magenta('➜')} {colors.cyan(f'DOCS   http://127.0.0.1:{config.api_port}/docs')}")
            print(f"  {colors.magenta('➜')} {colors.cyan(f'REDOC  http://127.0.0.1:{config.api_port}/redoc')}")
        print()

        while True:
            for managed in processes:
                code = managed.process.poll()
                if code is not None:
                    print(f"\n  {fail(colors)} {colors.red(managed.name)} {colors.white('stopped with exit code')} {colors.red(str(code))}")
                    return int(code)
            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\n  {colors.yellow('● Shutdown requested')}")
        return 130
    except ValueError as exc:
        print(f"\n  {fail(colors)} {colors.red(str(exc))}")
        return 2
    except Exception as exc:
        print(f"\n  {fail(colors)} {colors.red(f'Launcher error: {exc}')}")
        return 1
    finally:
        if processes:
            stop_all(processes, colors)


if __name__ == "__main__":
    raise SystemExit(main())
