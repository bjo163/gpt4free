import unittest

import g4f.version
from g4f.errors import VersionNotFoundError

DEFAULT_MESSAGES = [{"role": "user", "content": "Hello"}]


class TestGetLastProvider(unittest.TestCase):
    def test_get_latest_version(self):
        current_version = g4f.version.utils.current_version
        if current_version is not None:
            self.assertIsInstance(current_version, str)
        try:
            latest_version = g4f.version.utils.latest_version
        except VersionNotFoundError:
            return
        # The version endpoint may be unavailable in CI/offline environments.
        # Treat an unavailable value like VersionNotFoundError rather than making
        # the entire suite network-dependent.
        if latest_version is not None:
            self.assertIsInstance(latest_version, str)
