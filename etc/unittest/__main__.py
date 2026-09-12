import subprocess
import sys
import unittest

import g4f.debug

g4f.debug.version_check = False

# execute_safe_code intentionally abandons timed-out daemon threads. Running
# several timeout-hardening cases in one interpreter therefore lets CPU-bound
# synthetic infinite loops contend with later timing assertions. Execute every
# security-hardening case in a fresh child interpreter so its daemon threads are
# reaped when that case exits, while preserving the original timeout assertions.
from . import mcp as _mcp

for _test_name in unittest.defaultTestLoader.getTestCaseNames(
    _mcp.TestSecurityHardening
):
    _result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            f"etc.unittest.mcp.TestSecurityHardening.{_test_name}",
        ],
        check=False,
        timeout=45,
    )
    if _result.returncode != 0:
        raise SystemExit(_result.returncode)

_mcp.TestSecurityHardening.__unittest_skip__ = True
_mcp.TestSecurityHardening.__unittest_skip_why__ = (
    "executed individually in isolated subprocesses by etc.unittest"
)

from .asyncio import *
from .backend import *
from .main import *
from .model import *
from .client import *
from .image_client import *
from .include import *
from .retry_provider import *
from .thinking import *
from .web_search import *
from .models import *
from .mcp import *
from .tool_support_provider import *
from .config_provider import *
from .test_gemini import *
from .test_deepseek_chunk_log import *
from .test_deepseek_stream import *
from .test_deepseek_upload import *
from .test_auth_retry import *
from .test_cdp_parallel import *

unittest.main()
