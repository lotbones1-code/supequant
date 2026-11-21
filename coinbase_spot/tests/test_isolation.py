"""Verify imports in a clean interpreter with sensitive capabilities blocked."""

import ast
from pathlib import Path
import subprocess
import sys
import unittest


PACKAGE = Path(__file__).resolve().parents[1]


class IsolationTests(unittest.TestCase):
    def test_core_import_surface_is_only_stdlib_and_relative_package_modules(self):
        for path in PACKAGE.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [(node.module or "").split(".")[0]]
                else:
                    continue
                for module in modules:
                    self.assertIn(module, sys.stdlib_module_names, (path.name, module))
                    self.assertNotIn(module, {"socket", "urllib", "http", "subprocess", "threading", "ctypes", "importlib"},
                                     (path.name, "unexpected active capability", module))

    def test_imports_cannot_access_credentials_start_services_or_write_state(self):
        probe = r'''
import importlib, os, pathlib, sqlite3, sys, threading
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
def blocked(*args, **kwargs):
    raise AssertionError("forbidden import-time capability")
os.getenv = blocked
os._Environ.__getitem__ = blocked
sqlite3.connect = blocked
threading.Thread.start = blocked
def audit(event, args):
    if event.startswith("socket.") or event.startswith("subprocess.") or event in {"os.system", "os.exec", "os.fork", "os.spawn"}:
        blocked()
    if event == "open":
        path, mode, flags = args
        if (isinstance(mode, str) and any(x in mode for x in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            blocked()
        if isinstance(path, (str, bytes)) and not str(path).endswith((".py", ".pyc", ".so")):
            raise AssertionError("unexpected import-time data-file read")
sys.addaudithook(audit)
for name in ["coinbase_spot", "coinbase_spot.models", "coinbase_spot.ledger", "coinbase_spot.risk", "coinbase_spot.market_data", "coinbase_spot.strategy", "coinbase_spot.replay", "coinbase_spot.__main__"]:
    importlib.import_module(name)
for name in ["config", "data_feed", "execution", "backtesting", "strategy", "risk", "agents", "dotenv", "requests"]:
    assert name not in sys.modules, name
print("offline import boundary verified")
'''
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", probe, str(PACKAGE.parent)],
                                text=True, capture_output=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "offline import boundary verified")


if __name__ == "__main__":
    unittest.main()
