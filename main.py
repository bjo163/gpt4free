from __future__ import annotations

# ============================================================
# ROCKSOUL · BLAS / MEMORY SAFETY
# IMPORTANT:
# Set BEFORE starting g4f / numpy / scipy child processes.
# ============================================================

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

os.environ.setdefault("G4F_TIMEOUT", "30")
os.environ.setdefault("G4F_STREAM_TIMEOUT", "30")


# ============================================================
# STANDARD LIBRARY
# ============================================================

import argparse
import importlib.metadata
import logging
import platform
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


# ============================================================
# ROCKSOUL · ANSI COLORS
# ============================================================

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


# ============================================================
# CONSTANTS
# ============================================================

APP_NAME = "ROCKSOUL"
APP_TITLE = "ROCKSOUL · g4f Launcher"

DEFAULT_GUI_HOST = "0.0.0.0"
DEFAULT_GUI_PORT = 8080

DEFAULT_API_HOST = "0.0.0.0"
DEFAULT_API_PORT = 8081

DEFAULT_TIMEOUT = 30
DEFAULT_STREAM_TIMEOUT = 30
DEFAULT_LOG_LEVEL = "WARNING"

HEADER_WIDTH = 58
LABEL_WIDTH = 18


# ============================================================
# DATA TYPES
# ============================================================

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
    log_level: str
    color: bool
    quiet: bool
    no_color: bool


@dataclass(slots=True)
class RuntimeInfo:
    python_version: str
    platform: str
    g4f_version: str
    cwd: str
    pid: int
    ffmpeg: str | None
    lan_ip: str | None
    memory: str


@dataclass(slots=True)
class ManagedProcess:
    name: str
    process: subprocess.Popen[str]


# ============================================================
# COLOR MANAGER
# ============================================================

class Colors:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def apply(self, text: str, color: str) -> str:
        if not self.enabled:
            return text

        return f"{color}{text}{RESET}"

    def bold(self, text: str) -> str:
        return self.apply(text, BOLD)

    def cyan(self, text: str) -> str:
        return self.apply(text, CYAN)

    def magenta(self, text: str) -> str:
        return self.apply(text, MAGENTA)

    def green(self, text: str) -> str:
        return self.apply(text, GREEN)

    def yellow(self, text: str) -> str:
        return self.apply(text, YELLOW)

    def red(self, text: str) -> str:
        return self.apply(text, RED)

    def blue(self, text: str) -> str:
        return self.apply(text, BLUE)

    def white(self, text: str) -> str:
        return self.apply(text, WHITE)

    def gray(self, text: str) -> str:
        return self.apply(text, GRAY)


# ============================================================
# TERMINAL HELPERS
# ============================================================

def supports_color() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False

    if os.environ.get("TERM") == "dumb":
        return False

    return sys.stdout.isatty()


def styled_label(
    colors: Colors,
    text: str,
) -> str:
    padded = text.ljust(LABEL_WIDTH)

    return colors.bold(
        colors.blue(padded)
    )


def on_status(colors: Colors) -> str:
    return colors.bold(
        colors.green("● ON")
    )


def off_status(colors: Colors) -> str:
    return colors.bold(
        colors.gray("● OFF")
    )


def ok_status(colors: Colors) -> str:
    return colors.bold(
        colors.green("✓ OK")
    )


def warn_status(colors: Colors) -> str:
    return colors.bold(
        colors.yellow("⚠ WARN")
    )


def fail_status(colors: Colors) -> str:
    return colors.bold(
        colors.red("✖ FAIL")
    )


def print_separator(colors: Colors) -> None:
    print(
        colors.cyan(
            "  " + ("─" * HEADER_WIDTH)
        )
    )


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rockg4f",
        description=(
            "ROCKSOUL launcher for g4f GUI and "
            "OpenAI-compatible Interference API"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "mode",
        nargs="?",
        choices=[
            "gui",
            "api",
            "both",
        ],
        default="both",
        help="Server mode to launch",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode and auto reload",
    )

    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable auto reload while keeping debug mode",
    )

    parser.add_argument(
        "--gui-host",
        default=DEFAULT_GUI_HOST,
        help="GUI bind address",
    )

    parser.add_argument(
        "--gui-port",
        type=int,
        default=DEFAULT_GUI_PORT,
        help="GUI port",
    )

    parser.add_argument(
        "--api-host",
        default=DEFAULT_API_HOST,
        help="API bind address",
    )

    parser.add_argument(
        "--api-port",
        type=int,
        default=DEFAULT_API_PORT,
        help="API port",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Default g4f request timeout",
    )

    parser.add_argument(
        "--stream-timeout",
        type=int,
        default=DEFAULT_STREAM_TIMEOUT,
        help="Default g4f streaming timeout",
    )

    parser.add_argument(
        "--log-level",
        choices=[
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ],
        default=None,
        help="Log level",
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored terminal output",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Hide ROCKSOUL startup banner",
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Run diagnostics without starting servers",
    )

    parser.add_argument(
        "--version",
        action="store_true",
        help="Show runtime information",
    )

    return parser.parse_args()


# ============================================================
# RUNTIME
# ============================================================

def get_g4f_version() -> str:
    try:
        return importlib.metadata.version("g4f")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def get_ffmpeg_path() -> str | None:
    return (
        shutil.which("ffmpeg")
        or shutil.which("ffmpeg.exe")
    )


def get_lan_ip() -> str | None:
    sock: socket.socket | None = None

    try:
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        sock.connect(
            ("8.8.8.8", 80)
        )

        return str(
            sock.getsockname()[0]
        )

    except OSError:
        return None

    finally:
        if sock is not None:
            sock.close()


def get_memory_info() -> str:
    try:
        import ctypes

        class MemoryStatusEx(
            ctypes.Structure
        ):
            _fields_ = [
                (
                    "dwLength",
                    ctypes.c_ulong,
                ),
                (
                    "dwMemoryLoad",
                    ctypes.c_ulong,
                ),
                (
                    "ullTotalPhys",
                    ctypes.c_ulonglong,
                ),
                (
                    "ullAvailPhys",
                    ctypes.c_ulonglong,
                ),
                (
                    "ullTotalPageFile",
                    ctypes.c_ulonglong,
                ),
                (
                    "ullAvailPageFile",
                    ctypes.c_ulonglong,
                ),
                (
                    "ullTotalVirtual",
                    ctypes.c_ulonglong,
                ),
                (
                    "ullAvailVirtual",
                    ctypes.c_ulonglong,
                ),
                (
                    "ullAvailExtendedVirtual",
                    ctypes.c_ulonglong,
                ),
            ]

        status = MemoryStatusEx()

        status.dwLength = ctypes.sizeof(
            MemoryStatusEx
        )

        success = (
            ctypes.windll.kernel32
            .GlobalMemoryStatusEx(
                ctypes.byref(status)
            )
        )

        if success:
            total_gb = (
                status.ullTotalPhys
                / (1024 ** 3)
            )

            available_gb = (
                status.ullAvailPhys
                / (1024 ** 3)
            )

            used = int(
                status.dwMemoryLoad
            )

            return (
                f"{available_gb:.1f} GB free / "
                f"{total_gb:.1f} GB "
                f"({used}% used)"
            )

    except Exception:
        pass

    return "unavailable"


def collect_runtime_info() -> RuntimeInfo:
    return RuntimeInfo(
        python_version=platform.python_version(),
        platform=platform.platform(),
        g4f_version=get_g4f_version(),
        cwd=str(Path.cwd()),
        pid=os.getpid(),
        ffmpeg=get_ffmpeg_path(),
        lan_ip=get_lan_ip(),
        memory=get_memory_info(),
    )


# ============================================================
# CONFIG
# ============================================================

def validate_port(
    value: int,
    name: str,
) -> None:
    if not 1 <= value <= 65535:
        raise ValueError(
            f"Invalid {name}: {value}"
        )


def build_config(
    args: argparse.Namespace,
) -> Config:
    validate_port(
        args.gui_port,
        "GUI port",
    )

    validate_port(
        args.api_port,
        "API port",
    )

    if args.timeout <= 0:
        raise ValueError(
            "Timeout must be greater than zero."
        )

    if args.stream_timeout <= 0:
        raise ValueError(
            "Stream timeout must be greater than zero."
        )

    debug = bool(
        args.debug
    )

    reload = (
        debug
        and not args.no_reload
    )

    log_level = (
        args.log_level
        if args.log_level is not None
        else (
            "DEBUG"
            if debug
            else DEFAULT_LOG_LEVEL
        )
    )

    color = (
        supports_color()
        and not args.no_color
    )

    return Config(
        mode=args.mode,
        debug=debug,
        reload=reload,
        gui_host=args.gui_host,
        gui_port=args.gui_port,
        api_host=args.api_host,
        api_port=args.api_port,
        timeout=args.timeout,
        stream_timeout=args.stream_timeout,
        log_level=log_level,
        color=color,
        quiet=args.quiet,
        no_color=args.no_color,
    )


# ============================================================
# ENVIRONMENT
# ============================================================

def configure_environment(
    config: Config,
) -> None:
    os.environ[
        "OPENBLAS_NUM_THREADS"
    ] = os.environ.get(
        "OPENBLAS_NUM_THREADS",
        "1",
    )

    os.environ[
        "OMP_NUM_THREADS"
    ] = os.environ.get(
        "OMP_NUM_THREADS",
        "1",
    )

    os.environ[
        "MKL_NUM_THREADS"
    ] = os.environ.get(
        "MKL_NUM_THREADS",
        "1",
    )

    os.environ[
        "NUMEXPR_NUM_THREADS"
    ] = os.environ.get(
        "NUMEXPR_NUM_THREADS",
        "1",
    )

    os.environ[
        "G4F_TIMEOUT"
    ] = str(
        config.timeout
    )

    os.environ[
        "G4F_STREAM_TIMEOUT"
    ] = str(
        config.stream_timeout
    )

    if config.debug:
        os.environ[
            "G4F_DEBUG"
        ] = "1"

        os.environ[
            "FLASK_DEBUG"
        ] = "1"

        os.environ[
            "FLASK_ENV"
        ] = "development"


# ============================================================
# LOGGING
# ============================================================

def configure_logging(
    config: Config,
) -> None:
    level = getattr(
        logging,
        config.log_level,
        logging.WARNING,
    )

    if config.color:
        log_format = (
            f"{CYAN}%(asctime)s{RESET} "
            f"{MAGENTA}[%(levelname)s]{RESET} "
            "%(name)s: %(message)s"
        )
    else:
        log_format = (
            "%(asctime)s "
            "[%(levelname)s] "
            "%(name)s: %(message)s"
        )

    logging.basicConfig(
        level=level,
        format=log_format,
    )


# ============================================================
# PROCESS ENVIRONMENT
# ============================================================

def get_child_environment(
    config: Config,
) -> dict[str, str]:
    env = os.environ.copy()

    env[
        "OPENBLAS_NUM_THREADS"
    ] = "1"

    env[
        "OMP_NUM_THREADS"
    ] = "1"

    env[
        "MKL_NUM_THREADS"
    ] = "1"

    env[
        "NUMEXPR_NUM_THREADS"
    ] = "1"

    env[
        "G4F_TIMEOUT"
    ] = str(
        config.timeout
    )

    env[
        "G4F_STREAM_TIMEOUT"
    ] = str(
        config.stream_timeout
    )

    if config.debug:
        env[
            "G4F_DEBUG"
        ] = "1"

        env[
            "FLASK_DEBUG"
        ] = "1"

        env[
            "FLASK_ENV"
        ] = "development"

    return env


# ============================================================
# PORT CHECK
# ============================================================

def is_port_available(
    host: str,
    port: int,
) -> bool:
    check_host = host

    if host == "localhost":
        check_host = "127.0.0.1"

    if host in (
        "0.0.0.0",
        "::",
    ):
        check_host = "0.0.0.0"

    sock: socket.socket | None = None

    try:
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        sock.bind(
            (
                check_host,
                port,
            )
        )

        return True

    except OSError:
        return False

    finally:
        if sock is not None:
            sock.close()


# ============================================================
# MODE DISPLAY
# ============================================================

def mode_enabled(
    config: Config,
    mode: str,
) -> bool:
    if config.mode == "both":
        return True

    return config.mode == mode


def mode_name(
    config: Config,
) -> str:
    return {
        "gui": "GUI",
        "api": "API",
        "both": "GUI + API",
    }[config.mode]


# ============================================================
# BANNER
# ============================================================

def print_banner(
    config: Config,
    runtime: RuntimeInfo,
    colors: Colors,
) -> None:
    if config.quiet:
        return

    inner_width = HEADER_WIDTH - 2

    print()

    print(
        colors.cyan(
            "  ╭"
            + ("─" * inner_width)
            + "╮"
        )
    )

    title = "ROCKSOUL"
    subtitle = "g4f Launcher"

    plain_title = (
        f"{title} · {subtitle}"
    )

    padding = (
        inner_width
        - len(plain_title)
    )

    left = max(
        1,
        padding // 2,
    )

    right = max(
        1,
        padding - left,
    )

    title_line = (
        "│"
        + (" " * left)
        + colors.magenta(title)
        + colors.gray(" · ")
        + colors.cyan(subtitle)
        + (" " * right)
        + "│"
    )

    print(
        colors.cyan(
            "  " + title_line
        )
    )

    print(
        colors.cyan(
            "  ╰"
            + ("─" * inner_width)
            + "╯"
        )
    )

    print()

    # --------------------------------------------------------
    # MODE
    # --------------------------------------------------------

    print(
        colors.bold(
            colors.magenta(
                "  MODE"
            )
        )
    )

    print(
        f"  {styled_label(colors, 'MODE')}"
        f"{colors.cyan(mode_name(config))}"
    )

    print(
        f"  {styled_label(colors, 'DEBUG')}"
        f"{on_status(colors) if config.debug else off_status(colors)}"
    )

    print(
        f"  {styled_label(colors, 'AUTO RELOAD')}"
        f"{on_status(colors) if config.reload else off_status(colors)}"
    )

    print(
        f"  {styled_label(colors, 'LOG LEVEL')}"
        f"{colors.yellow(config.log_level)}"
    )

    print()

    # --------------------------------------------------------
    # GUI
    # --------------------------------------------------------

    if mode_enabled(
        config,
        "gui",
    ):
        print(
            colors.bold(
                colors.magenta(
                    "  GUI SERVER"
                )
            )
        )

        print(
            f"  {styled_label(colors, 'HOST')}"
            f"{colors.white(config.gui_host)}"
        )

        print(
            f"  {styled_label(colors, 'PORT')}"
            f"{colors.white(str(config.gui_port))}"
        )

        print(
            f"  {styled_label(colors, 'CHAT')}"
            f"{colors.cyan(f'http://127.0.0.1:{config.gui_port}/chat/')}"
        )

        print()

    # --------------------------------------------------------
    # API
    # --------------------------------------------------------

    if mode_enabled(
        config,
        "api",
    ):
        print(
            colors.bold(
                colors.magenta(
                    "  INTERFERENCE API"
                )
            )
        )

        print(
            f"  {styled_label(colors, 'HOST')}"
            f"{colors.white(config.api_host)}"
        )

        print(
            f"  {styled_label(colors, 'PORT')}"
            f"{colors.white(str(config.api_port))}"
        )

        print(
            f"  {styled_label(colors, 'BASE URL')}"
            f"{colors.cyan(f'http://127.0.0.1:{config.api_port}/v1')}"
        )

        print(
            f"  {styled_label(colors, 'SWAGGER')}"
            f"{colors.cyan(f'http://127.0.0.1:{config.api_port}/docs')}"
        )

        print()

    # --------------------------------------------------------
    # RUNTIME
    # --------------------------------------------------------

    print(
        colors.bold(
            colors.magenta(
                "  RUNTIME"
            )
        )
    )

    print(
        f"  {styled_label(colors, 'PYTHON')}"
        f"{colors.white(runtime.python_version)}"
    )

    print(
        f"  {styled_label(colors, 'G4F')}"
        f"{colors.white(runtime.g4f_version)}"
    )

    print(
        f"  {styled_label(colors, 'TIMEOUT')}"
        f"{colors.yellow(f'{config.timeout}s')}"
    )

    print(
        f"  {styled_label(colors, 'STREAM TIMEOUT')}"
        f"{colors.yellow(f'{config.stream_timeout}s')}"
    )

    print(
        f"  {styled_label(colors, 'MEMORY')}"
        f"{colors.white(runtime.memory)}"
    )

    print(
        f"  {styled_label(colors, 'PID')}"
        f"{colors.white(str(runtime.pid))}"
    )

    print(
        f"  {styled_label(colors, 'PLATFORM')}"
        f"{colors.gray(runtime.platform)}"
    )

    print()

    # --------------------------------------------------------
    # PERFORMANCE
    # --------------------------------------------------------

    print(
        colors.bold(
            colors.magenta(
                "  PERFORMANCE"
            )
        )
    )

    print(
        f"  {styled_label(colors, 'OPENBLAS')}"
        f"{colors.green(os.environ.get('OPENBLAS_NUM_THREADS', '1'))}"
        f"{colors.gray(' threads')}"
    )

    print(
        f"  {styled_label(colors, 'OMP')}"
        f"{colors.green(os.environ.get('OMP_NUM_THREADS', '1'))}"
        f"{colors.gray(' threads')}"
    )

    print(
        f"  {styled_label(colors, 'MKL')}"
        f"{colors.green(os.environ.get('MKL_NUM_THREADS', '1'))}"
        f"{colors.gray(' threads')}"
    )

    print()

    # --------------------------------------------------------
    # DEPENDENCIES
    # --------------------------------------------------------

    print(
        colors.bold(
            colors.magenta(
                "  DEPENDENCIES"
            )
        )
    )

    if runtime.ffmpeg:
        print(
            f"  {styled_label(colors, 'FFMPEG')}"
            f"{colors.green('AVAILABLE')} "
            f"{ok_status(colors)}"
        )
    else:
        print(
            f"  {styled_label(colors, 'FFMPEG')}"
            f"{colors.yellow('NOT FOUND')} "
            f"{warn_status(colors)}"
        )

    print()

    print_separator(colors)

    print()

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    print(
        f"  {styled_label(colors, 'STATUS')}"
        f"{colors.bold(colors.green('● READY'))}"
    )

    if (
        config.debug
        and config.reload
    ):
        print(
            f"  {colors.green('✓')} "
            f"{colors.white('Development mode')}"
            f" {colors.gray('·')} "
            f"{colors.green('debug + auto reload enabled')}"
        )

    elif config.debug:
        print(
            f"  {colors.yellow('!')} "
            f"{colors.white('Debug mode')}"
            f" {colors.gray('·')} "
            f"{colors.yellow('auto reload disabled')}"
        )

    else:
        print(
            f"  {colors.gray('•')} "
            f"{colors.gray('Normal mode · debug disabled')}"
        )

    print()


# ============================================================
# DIAGNOSTICS
# ============================================================

def run_diagnostics(
    config: Config,
    runtime: RuntimeInfo,
    colors: Colors,
) -> bool:
    all_ok = True

    print()

    print(
        colors.bold(
            colors.magenta(
                "ROCKSOUL · Diagnostics"
            )
        )
    )

    print()

    # --------------------------------------------------------
    # G4F
    # --------------------------------------------------------

    if runtime.g4f_version != "unknown":
        print(
            f"  {styled_label(colors, 'G4F')}"
            f"{colors.green(runtime.g4f_version)} "
            f"{ok_status(colors)}"
        )
    else:
        print(
            f"  {styled_label(colors, 'G4F')}"
            f"{colors.red('unknown')} "
            f"{fail_status(colors)}"
        )

        all_ok = False

    # --------------------------------------------------------
    # Python
    # --------------------------------------------------------

    print(
        f"  {styled_label(colors, 'PYTHON')}"
        f"{colors.white(runtime.python_version)} "
        f"{ok_status(colors)}"
    )

    # --------------------------------------------------------
    # MEMORY
    # --------------------------------------------------------

    print(
        f"  {styled_label(colors, 'MEMORY')}"
        f"{colors.white(runtime.memory)}"
    )

    # --------------------------------------------------------
    # FFmpeg
    # --------------------------------------------------------

    if runtime.ffmpeg:
        print(
            f"  {styled_label(colors, 'FFMPEG')}"
            f"{colors.green(runtime.ffmpeg)} "
            f"{ok_status(colors)}"
        )
    else:
        print(
            f"  {styled_label(colors, 'FFMPEG')}"
            f"{colors.yellow('not found')} "
            f"{warn_status(colors)}"
        )

    # --------------------------------------------------------
    # GUI PORT
    # --------------------------------------------------------

    if mode_enabled(config, "gui"):
        if is_port_available(
            config.gui_host,
            config.gui_port,
        ):
            print(
                f"  {styled_label(colors, 'GUI PORT')}"
                f"{colors.green(str(config.gui_port))} "
                f"{ok_status(colors)}"
            )
        else:
            print(
                f"  {styled_label(colors, 'GUI PORT')}"
                f"{colors.red(str(config.gui_port))} "
                f"{fail_status(colors)}"
            )

            all_ok = False

    # --------------------------------------------------------
    # API PORT
    # --------------------------------------------------------

    if mode_enabled(config, "api"):
        if is_port_available(
            config.api_host,
            config.api_port,
        ):
            print(
                f"  {styled_label(colors, 'API PORT')}"
                f"{colors.green(str(config.api_port))} "
                f"{ok_status(colors)}"
            )
        else:
            print(
                f"  {styled_label(colors, 'API PORT')}"
                f"{colors.red(str(config.api_port))} "
                f"{fail_status(colors)}"
            )

            all_ok = False

    # --------------------------------------------------------
    # BLAS
    # --------------------------------------------------------

    print(
        f"  {styled_label(colors, 'OPENBLAS')}"
        f"{colors.green(os.environ.get('OPENBLAS_NUM_THREADS', '1'))}"
        f"{colors.gray(' threads')}"
    )

    print(
        f"  {styled_label(colors, 'OMP')}"
        f"{colors.green(os.environ.get('OMP_NUM_THREADS', '1'))}"
        f"{colors.gray(' threads')}"
    )

    print(
        f"  {styled_label(colors, 'MKL')}"
        f"{colors.green(os.environ.get('MKL_NUM_THREADS', '1'))}"
        f"{colors.gray(' threads')}"
    )

    print()

    # --------------------------------------------------------
    # URLs
    # --------------------------------------------------------

    if mode_enabled(config, "gui"):
        print(
            f"  {colors.magenta('➜')} "
            f"{colors.cyan(f'http://127.0.0.1:{config.gui_port}/chat/')}"
        )

    if mode_enabled(config, "api"):
        print(
            f"  {colors.magenta('➜')} "
            f"{colors.cyan(f'http://127.0.0.1:{config.api_port}/v1')}"
        )

        print(
            f"  {colors.magenta('➜')} "
            f"{colors.cyan(f'http://127.0.0.1:{config.api_port}/docs')}"
        )

    print()

    if all_ok:
        print(
            f"  {colors.green('✓')} "
            f"{colors.green('Diagnostics passed.')}"
        )
    else:
        print(
            f"  {colors.yellow('⚠')} "
            f"{colors.yellow('Diagnostics completed with errors.')}"
        )

    print()

    return all_ok


# ============================================================
# SUBPROCESS COMMANDS
# ============================================================

def build_gui_command(
    config: Config,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "g4f.cli",
        "gui",
        "--host",
        config.gui_host,
        "--port",
        str(config.gui_port),
    ]

    if config.debug:
        command.append(
            "--debug"
        )

    return command


def build_api_command(
    config: Config,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "g4f",
        "--bind",
        config.api_host,
        "--port",
        str(config.api_port),
        "--no-gui",
        "--timeout",
        str(config.timeout),
        "--stream-timeout",
        str(config.stream_timeout),
    ]

    if config.debug:
        command.append(
            "--debug"
        )

    if config.reload:
        command.append(
            "--reload"
        )

    return command


def command_to_string(
    command: list[str],
) -> str:
    return " ".join(
        (
            f'"{item}"'
            if " " in item
            else item
        )
        for item in command
    )


# ============================================================
# PROCESS START
# ============================================================

def start_process(
    name: str,
    command: list[str],
    config: Config,
    colors: Colors,
) -> ManagedProcess:
    print(
        f"  {colors.green('▶')} "
        f"{colors.white(f'Starting {name}')} "
    )

    if config.debug:
        print(
            f"    {colors.gray(command_to_string(command))}"
        )

    process = subprocess.Popen(
        command,
        cwd=str(Path.cwd()),
        env=get_child_environment(config),
        text=True,
    )

    print(
        f"    {colors.green('PID')} "
        f"{colors.white(str(process.pid))}"
    )

    return ManagedProcess(
        name=name,
        process=process,
    )


# ============================================================
# PROCESS MANAGEMENT
# ============================================================

def terminate_process(
    managed: ManagedProcess,
    colors: Colors,
) -> None:
    process = managed.process

    if process.poll() is not None:
        return

    print(
        f"  {colors.yellow('■')} "
        f"{colors.white(f'Stopping {managed.name}')} "
        f"{colors.gray(f'(PID {process.pid})')}"
    )

    try:
        process.terminate()
        process.wait(
            timeout=5
        )
    except subprocess.TimeoutExpired:
        print(
            f"    {colors.yellow('⚠')} "
            f"{colors.yellow('Terminate timeout · killing process')}"
        )

        process.kill()

        try:
            process.wait(
                timeout=3
            )
        except subprocess.TimeoutExpired:
            pass

    except OSError:
        pass


def terminate_all(
    processes: list[ManagedProcess],
    colors: Colors,
) -> None:
    for managed in reversed(processes):
        terminate_process(
            managed,
            colors,
        )


# ============================================================
# WAIT LOOP
# ============================================================

def wait_for_processes(
    processes: list[ManagedProcess],
    colors: Colors,
) -> int:
    """
    Keep the supervisor alive while child processes run.

    If one child crashes unexpectedly, report it and stop the
    remaining processes so GUI/API don't silently diverge.
    """

    while True:
        alive = False

        for managed in processes:
            return_code = managed.process.poll()

            if return_code is None:
                alive = True
                continue

            print(
                f"\n  {colors.red('✖')} "
                f"{colors.red(managed.name)} "
                f"{colors.white('stopped with exit code')} "
                f"{colors.red(str(return_code))}"
            )

            return return_code

        if not alive:
            return 0

        try:
            time.sleep(0.5)
        except KeyboardInterrupt:
            return 130


# ============================================================
# VERSION
# ============================================================

def print_version(
    runtime: RuntimeInfo,
    colors: Colors,
) -> None:
    print()

    print(
        colors.bold(
            colors.magenta(
                APP_TITLE
            )
        )
    )

    print()

    print(
        f"  {styled_label(colors, 'G4F')}"
        f"{colors.white(runtime.g4f_version)}"
    )

    print(
        f"  {styled_label(colors, 'PYTHON')}"
        f"{colors.white(runtime.python_version)}"
    )

    print(
        f"  {styled_label(colors, 'PLATFORM')}"
        f"{colors.white(runtime.platform)}"
    )

    print(
        f"  {styled_label(colors, 'MEMORY')}"
        f"{colors.white(runtime.memory)}"
    )

    print()


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    args = parse_args()

    initial_colors = Colors(
        supports_color()
        and not args.no_color
    )

    try:
        runtime = collect_runtime_info()

        if args.version:
            print_version(
                runtime,
                initial_colors,
            )

            return 0

        config = build_config(
            args
        )

        colors = Colors(
            config.color
        )

        configure_environment(
            config
        )

        configure_logging(
            config
        )

        if args.check:
            run_diagnostics(
                config,
                runtime,
                colors,
            )

            return 0

        # ----------------------------------------------------
        # PORT CHECK
        # ----------------------------------------------------

        if mode_enabled(config, "gui"):
            if not is_port_available(
                config.gui_host,
                config.gui_port,
            ):
                print(
                    f"\n  {colors.bold(colors.red('✖ GUI PORT BUSY'))} "
                    f"{colors.red(str(config.gui_port))}"
                )

                print(
                    f"  {colors.gray('Use')} "
                    f"{colors.cyan('--gui-port <PORT>')}"
                )

                return 1

        if mode_enabled(config, "api"):
            if not is_port_available(
                config.api_host,
                config.api_port,
            ):
                print(
                    f"\n  {colors.bold(colors.red('✖ API PORT BUSY'))} "
                    f"{colors.red(str(config.api_port))}"
                )

                print(
                    f"  {colors.gray('Use')} "
                    f"{colors.cyan('--api-port <PORT>')}"
                )

                return 1

        # ----------------------------------------------------
        # STARTUP
        # ----------------------------------------------------

        print_banner(
            config,
            runtime,
            colors,
        )

        processes: list[ManagedProcess] = []

        # ----------------------------------------------------
        # GUI
        # ----------------------------------------------------

        if mode_enabled(
            config,
            "gui",
        ):
            gui_command = build_gui_command(
                config
            )

            processes.append(
                start_process(
                    "GUI",
                    gui_command,
                    config,
                    colors,
                )
            )

        # ----------------------------------------------------
        # API
        # ----------------------------------------------------

        if mode_enabled(
            config,
            "api",
        ):
            api_command = build_api_command(
                config
            )

            processes.append(
                start_process(
                    "API",
                    api_command,
                    config,
                    colors,
                )
            )

        print()

        print_separator(
            colors
        )

        print()

        print(
            f"  {styled_label(colors, 'STATUS')}"
            f"{colors.bold(colors.green('● RUNNING'))}"
        )

        if mode_enabled(
            config,
            "gui",
        ):
            print(
                f"  {colors.magenta('➜')} "
                f"{colors.cyan(f'GUI    http://127.0.0.1:{config.gui_port}/chat/')}"
            )

        if mode_enabled(
            config,
            "api",
        ):
            print(
                f"  {colors.magenta('➜')} "
                f"{colors.cyan(f'API    http://127.0.0.1:{config.api_port}/v1')}"
            )

            print(
                f"  {colors.magenta('➜')} "
                f"{colors.cyan(f'DOCS   http://127.0.0.1:{config.api_port}/docs')}"
            )

        print()

        # ----------------------------------------------------
        # SUPERVISOR
        # ----------------------------------------------------

        return_code = wait_for_processes(
            processes,
            colors,
        )

        terminate_all(
            processes,
            colors,
        )

        print(
            f"\n  {colors.green('●')} "
            f"{colors.white('ROCKSOUL launcher stopped.')}"
        )

        return return_code

    except KeyboardInterrupt:
        print(
            f"\n  {initial_colors.yellow('●')} "
            f"{initial_colors.yellow('Shutdown requested.')}"
        )

        return 130

    except ValueError as exc:
        print(
            f"\n  {initial_colors.bold(initial_colors.red('✖ CONFIG ERROR'))} "
            f"{initial_colors.red(str(exc))}"
        )

        return 2

    except OSError as exc:
        print(
            f"\n  {initial_colors.bold(initial_colors.red('✖ OS ERROR'))} "
            f"{initial_colors.red(str(exc))}"
        )

        return 1

    except Exception as exc:
        print(
            f"\n  {initial_colors.bold(initial_colors.red('✖ LAUNCHER ERROR'))} "
            f"{initial_colors.red(str(exc))}"
        )

        if args.debug:
            logging.exception(
                "Launcher traceback"
            )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )