from __future__ import annotations

# ============================================================
# ROCKSOUL · PROCESS SAFETY
# Configure before spawning/importing g4f workloads.
# ============================================================

import argparse
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

# Bound numerical backends before any child process starts.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ.setdefault("G4F_TIMEOUT", "30")
os.environ.setdefault("G4F_STREAM_TIMEOUT", "30")


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

APP_TITLE = "ROCKSOUL · g4f Launcher"
DEFAULT_GUI_HOST = "0.0.0.0"
DEFAULT_GUI_PORT = 8080
DEFAULT_API_HOST = "0.0.0.0"
DEFAULT_API_PORT = 8081
DEFAULT_TIMEOUT = 30
DEFAULT_STREAM_TIMEOUT = 30
HEADER_WIDTH = 58
LABEL_WIDTH = 18


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


class Colors:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def apply(self, text: str, color: str) -> str:
        return f"{color}{text}{RESET}" if self.enabled else text

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


def supports_color() -> bool:
    return os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb" and sys.stdout.isatty()


def styled_label(colors: Colors, text: str) -> str:
    return colors.bold(colors.blue(text.ljust(LABEL_WIDTH)))


def status_on(colors: Colors) -> str:
    return colors.bold(colors.green("● ON"))


def status_off(colors: Colors) -> str:
    return colors.bold(colors.gray("● OFF"))


def status_ok(colors: Colors) -> str:
    return colors.bold(colors.green("✓ OK"))


def status_warn(colors: Colors) -> str:
    return colors.bold(colors.yellow("⚠ WARN"))


def status_fail(colors: Colors) -> str:
    return colors.bold(colors.red("✖ FAIL"))


def separator(colors: Colors) -> None:
    print(colors.cyan("  " + "─" * HEADER_WIDTH))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rockg4f",
        description="ROCKSOUL launcher for the official g4f GUI and Interference API",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("mode", nargs="?", choices=["gui", "api", "both"], default="both")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging; API also enables reload")
    parser.add_argument("--no-reload", action="store_true", help="Disable API auto reload")
    parser.add_argument("--gui-host", default=DEFAULT_GUI_HOST)
    parser.add_argument("--gui-port", type=int, default=DEFAULT_GUI_PORT)
    parser.add_argument("--api-host", default=DEFAULT_API_HOST)
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--stream-timeout", type=int, default=DEFAULT_STREAM_TIMEOUT)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--check", action="store_true", help="Run diagnostics without starting services")
    parser.add_argument("--version", action="store_true", help="Show runtime and g4f version")
    return parser.parse_args()


def get_g4f_version() -> str:
    try:
        return importlib.metadata.version("g4f")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def get_ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")


def get_lan_ip() -> str | None:
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return None
    finally:
        if sock is not None:
            sock.close()


def get_memory_info() -> str:
    try:
        import ctypes

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

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total = status.ullTotalPhys / (1024 ** 3)
            available = status.ullAvailPhys / (1024 ** 3)
            return f"{available:.1f} GB free / {total:.1f} GB ({int(status.dwMemoryLoad)}% used)"
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


def validate_port(value: int, name: str) -> None:
    if not 1 <= value <= 65535:
        raise ValueError(f"Invalid {name}: {value}")


def build_config(args: argparse.Namespace) -> Config:
    validate_port(args.gui_port, "GUI port")
    validate_port(args.api_port, "API port")
    if args.mode == "both" and args.gui_port == args.api_port:
        raise ValueError("GUI and API ports must be different in 'both' mode")
    if args.timeout <= 0 or args.stream_timeout <= 0:
        raise ValueError("Timeout values must be greater than zero")
    return Config(
        mode=args.mode,
        debug=bool(args.debug),
        reload=bool(args.debug and not args.no_reload),
        gui_host=args.gui_host,
        gui_port=args.gui_port,
        api_host=args.api_host,
        api_port=args.api_port,
        timeout=args.timeout,
        stream_timeout=args.stream_timeout,
        color=supports_color() and not args.no_color,
        quiet=args.quiet,
    )


def configure_environment(config: Config) -> None:
    os.environ["G4F_TIMEOUT"] = str(config.timeout)
    os.environ["G4F_STREAM_TIMEOUT"] = str(config.stream_timeout)
    # Force thread pools to one worker to avoid reload-related memory spikes.
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"
    if config.debug:
        os.environ["G4F_DEBUG"] = "1"
        os.environ["FLASK_DEBUG"] = "1"
        os.environ["FLASK_ENV"] = "development"


def child_environment(config: Config) -> dict[str, str]:
    env = os.environ.copy()
    env["G4F_TIMEOUT"] = str(config.timeout)
    env["G4F_STREAM_TIMEOUT"] = str(config.stream_timeout)
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["NUMEXPR_NUM_THREADS"] = "1"
    if config.debug:
        env["G4F_DEBUG"] = "1"
        env["FLASK_DEBUG"] = "1"
        env["FLASK_ENV"] = "development"
    return env


def is_port_available(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host == "localhost" else host
    if bind_host == "::":
        bind_host = "0.0.0.0"
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_host, port))
        return True
    except OSError:
        return False
    finally:
        if sock is not None:
            sock.close()


def command_text(command: list[str]) -> str:
    return " ".join(f'"{item}"' if " " in item else item for item in command)


def has_gui(config: Config) -> bool:
    return config.mode in ("gui", "both")


def has_api(config: Config) -> bool:
    return config.mode in ("api", "both")


def build_gui_command(config: Config) -> list[str]:
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
        command.append("--debug")
    return command


def build_api_command(config: Config) -> list[str]:
    # IMPORTANT: g4f's CLI has an explicit `api` mode. Keep the mode
    # before the mode-specific options so argparse cannot interpret the
    # bind host as the positional mode.
    command = [
        sys.executable,
        "-m",
        "g4f",
        "api",
        "--bind",
        f"{config.api_host}:{config.api_port}",
        "--no-gui",
        "--timeout",
        str(config.timeout),
        "--stream-timeout",
        str(config.stream_timeout),
    ]
    if config.debug:
        command.append("--debug")
    if config.reload:
        command.append("--reload")
    if not config.color:
        command.append("--disable-colors")
    return command


def start_process(name: str, command: list[str], config: Config, colors: Colors) -> ManagedProcess:
    print(f"  {colors.green('▶')} {colors.white(f'Starting {name}')}" )
    if config.debug:
        print(f"    {colors.gray(command_text(command))}")
    process = subprocess.Popen(command, cwd=str(Path.cwd()), env=child_environment(config))
    print(f"    {styled_label(colors, 'PID')}{colors.white(str(process.pid))}")
    return ManagedProcess(name=name, process=process)


def stop_process(managed: ManagedProcess, colors: Colors) -> None:
    process = managed.process
    if process.poll() is not None:
        return
    print(f"  {colors.yellow('■')} {colors.white(f'Stopping {managed.name}')} {colors.gray(f'(PID {process.pid})')}")
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
    except OSError:
        pass


def stop_all(processes: list[ManagedProcess], colors: Colors) -> None:
    for managed in reversed(processes):
        stop_process(managed, colors)


def wait_for_processes(processes: list[ManagedProcess], colors: Colors) -> int:
    while True:
        for managed in processes:
            code = managed.process.poll()
            if code is None:
                continue
            print(f"\n  {colors.red('✖')} {colors.red(managed.name)} {colors.white('stopped with exit code')} {colors.red(str(code))}")
            return int(code)
        time.sleep(0.5)


def print_banner(config: Config, runtime: RuntimeInfo, colors: Colors) -> None:
    if config.quiet:
        return
    inner = HEADER_WIDTH - 2
    title = "ROCKSOUL"
    subtitle = "g4f Launcher"
    plain = f"{title} · {subtitle}"
    padding = max(2, inner - len(plain))
    left = max(1, padding // 2)
    right = max(1, padding - left)

    print()
    print(colors.cyan("  ╭" + "─" * inner + "╮"))
    print(colors.cyan("  │") + " " * left + colors.magenta(title) + colors.gray(" · ") + colors.cyan(subtitle) + " " * right + colors.cyan("│"))
    print(colors.cyan("  ╰" + "─" * inner + "╯"))
    print()

    print(colors.bold(colors.magenta("  MODE")))
    print(f"  {styled_label(colors, 'MODE')}{colors.cyan(config.mode.upper())}")
    print(f"  {styled_label(colors, 'DEBUG')}{status_on(colors) if config.debug else status_off(colors)}")
    print(f"  {styled_label(colors, 'API RELOAD')}{status_on(colors) if config.reload else status_off(colors)}")
    print(f"  {styled_label(colors, 'GUI RELOAD')}{colors.gray('● OFF (official runner)')}")
    print()

    if has_gui(config):
        print(colors.bold(colors.magenta("  GUI SERVER")))
        print(f"  {styled_label(colors, 'HOST')}{colors.white(config.gui_host)}")
        print(f"  {styled_label(colors, 'PORT')}{colors.white(str(config.gui_port))}")
        print(f"  {styled_label(colors, 'CHAT')}{colors.cyan(f'http://127.0.0.1:{config.gui_port}/chat/')}")
        print()

    if has_api(config):
        print(colors.bold(colors.magenta("  INTERFERENCE API")))
        print(f"  {styled_label(colors, 'HOST')}{colors.white(config.api_host)}")
        print(f"  {styled_label(colors, 'PORT')}{colors.white(str(config.api_port))}")
        print(f"  {styled_label(colors, 'BASE URL')}{colors.cyan(f'http://127.0.0.1:{config.api_port}/v1')}")
        print(f"  {styled_label(colors, 'SWAGGER')}{colors.cyan(f'http://127.0.0.1:{config.api_port}/docs')}")
        print(f"  {styled_label(colors, 'REDOC')}{colors.cyan(f'http://127.0.0.1:{config.api_port}/redoc')}")
        print()

    print(colors.bold(colors.magenta("  RUNTIME")))
    print(f"  {styled_label(colors, 'PYTHON')}{colors.white(runtime.python_version)}")
    print(f"  {styled_label(colors, 'G4F')}{colors.white(runtime.g4f_version)}")
    print(f"  {styled_label(colors, 'TIMEOUT')}{colors.yellow(f'{config.timeout}s')}")
    print(f"  {styled_label(colors, 'STREAM TIMEOUT')}{colors.yellow(f'{config.stream_timeout}s')}")
    print(f"  {styled_label(colors, 'MEMORY')}{colors.white(runtime.memory)}")
    print()

    print(colors.bold(colors.magenta("  PERFORMANCE")))
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        print(f"  {styled_label(colors, key.removesuffix('_NUM_THREADS'))}{colors.green(os.environ.get(key, '1'))}{colors.gray(' threads')}")
    print()

    print(colors.bold(colors.magenta("  DEPENDENCIES")))
    if runtime.ffmpeg:
        print(f"  {styled_label(colors, 'FFMPEG')}{colors.green('AVAILABLE')} {status_ok(colors)}")
    else:
        print(f"  {styled_label(colors, 'FFMPEG')}{colors.yellow('NOT FOUND')} {status_warn(colors)}")

    print()
    separator(colors)
    print()
    print(f"  {styled_label(colors, 'STATUS')}{colors.bold(colors.green('● READY'))}")
    if config.debug and config.reload:
        print(f"  {colors.green('✓')} {colors.white('Development mode')} {colors.gray('·')} {colors.green('API debug + auto reload enabled')}")
    elif config.debug:
        print(f"  {colors.yellow('!')} {colors.white('Debug mode')} {colors.gray('·')} {colors.yellow('API reload disabled')}")
    else:
        print(f"  {colors.gray('•')} {colors.gray('Normal mode · debug disabled')}")
    if has_gui(config):
        print(f"  {colors.gray('•')} {colors.gray('GUI uses the official runner; auto reload is disabled upstream')}")
    if runtime.ffmpeg is None:
        print(f"  {colors.yellow('⚠')} {colors.yellow('FFmpeg not found · audio features may be limited')}")
    print()


def run_diagnostics(config: Config, runtime: RuntimeInfo, colors: Colors) -> bool:
    all_ok = True
    print()
    print(colors.bold(colors.magenta("ROCKSOUL · Diagnostics")))
    print()
    print(f"  {styled_label(colors, 'G4F')}{colors.green(runtime.g4f_version)} {status_ok(colors) if runtime.g4f_version != 'unknown' else status_fail(colors)}")
    print(f"  {styled_label(colors, 'PYTHON')}{colors.white(runtime.python_version)} {status_ok(colors)}")
    print(f"  {styled_label(colors, 'MEMORY')}{colors.white(runtime.memory)}")
    print(f"  {styled_label(colors, 'OPENBLAS')}{colors.green(os.environ.get('OPENBLAS_NUM_THREADS', '1'))}")
    print(f"  {styled_label(colors, 'OMP')}{colors.green(os.environ.get('OMP_NUM_THREADS', '1'))}")
    if runtime.ffmpeg:
        print(f"  {styled_label(colors, 'FFMPEG')}{colors.green(runtime.ffmpeg)} {status_ok(colors)}")
    else:
        print(f"  {styled_label(colors, 'FFMPEG')}{colors.yellow('not found')} {status_warn(colors)}")
    if has_gui(config):
        available = is_port_available(config.gui_host, config.gui_port)
        print(f"  {styled_label(colors, 'GUI PORT')}{colors.green(str(config.gui_port)) if available else colors.red(str(config.gui_port))} {status_ok(colors) if available else status_fail(colors)}")
        all_ok = all_ok and available
    if has_api(config):
        available = is_port_available(config.api_host, config.api_port)
        print(f"  {styled_label(colors, 'API PORT')}{colors.green(str(config.api_port)) if available else colors.red(str(config.api_port))} {status_ok(colors) if available else status_fail(colors)}")
        all_ok = all_ok and available
    print()
    print(f"  {colors.green('✓ Diagnostics passed.') if all_ok else colors.yellow('⚠ Diagnostics completed with errors.')}")
    print()
    return all_ok


def print_version(runtime: RuntimeInfo, colors: Colors) -> None:
    print()
    print(colors.bold(colors.magenta(APP_TITLE)))
    print()
    print(f"  {styled_label(colors, 'G4F')}{colors.white(runtime.g4f_version)}")
    print(f"  {styled_label(colors, 'PYTHON')}{colors.white(runtime.python_version)}")
    print(f"  {styled_label(colors, 'PLATFORM')}{colors.white(runtime.platform)}")
    print(f"  {styled_label(colors, 'MEMORY')}{colors.white(runtime.memory)}")
    print()


def main() -> int:
    args = parse_args()
    colors = Colors(supports_color() and not args.no_color)
    processes: list[ManagedProcess] = []

    try:
        runtime = collect_runtime_info()
        if args.version:
            print_version(runtime, colors)
            return 0

        config = build_config(args)
        colors = Colors(config.color)
        configure_environment(config)

        if args.check:
            return 0 if run_diagnostics(config, runtime, colors) else 1

        if has_gui(config) and not is_port_available(config.gui_host, config.gui_port):
            print(f"\n  {colors.bold(colors.red('✖ GUI PORT BUSY'))} {colors.red(str(config.gui_port))}")
            return 1
        if has_api(config) and not is_port_available(config.api_host, config.api_port):
            print(f"\n  {colors.bold(colors.red('✖ API PORT BUSY'))} {colors.red(str(config.api_port))}")
            return 1

        print_banner(config, runtime, colors)

        if has_gui(config):
            processes.append(start_process("GUI", build_gui_command(config), config, colors))
        if has_api(config):
            processes.append(start_process("API", build_api_command(config), config, colors))

        print()
        separator(colors)
        print()
        print(f"  {styled_label(colors, 'STATUS')}{colors.bold(colors.green('● RUNNING'))}")
        if has_gui(config):
            print(f"  {colors.magenta('➜')} {colors.cyan(f'GUI    http://127.0.0.1:{config.gui_port}/chat/')}")
        if has_api(config):
            print(f"  {colors.magenta('➜')} {colors.cyan(f'API    http://127.0.0.1:{config.api_port}/v1')}")
            print(f"  {colors.magenta('➜')} {colors.cyan(f'DOCS   http://127.0.0.1:{config.api_port}/docs')}")
            print(f"  {colors.magenta('➜')} {colors.cyan(f'REDOC  http://127.0.0.1:{config.api_port}/redoc')}")
        print()
        return wait_for_processes(processes, colors)

    except KeyboardInterrupt:
        print(f"\n  {colors.yellow('●')} {colors.yellow('Shutdown requested.')}")
        return 130
    except (ValueError, OSError) as exc:
        print(f"\n  {colors.bold(colors.red('✖ LAUNCHER ERROR'))} {colors.red(str(exc))}")
        return 1
    finally:
        stop_all(processes, colors)


if __name__ == "__main__":
    raise SystemExit(main())
