"""Keep tests away from the owner's real data, cache and downloaded sounds."""

import os
import tempfile

_ROOT = tempfile.mkdtemp(prefix="mfl-tests-")
os.environ["XDG_DATA_HOME"] = os.path.join(_ROOT, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_ROOT, "cache")
