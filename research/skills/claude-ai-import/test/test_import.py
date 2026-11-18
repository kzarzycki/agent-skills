import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a pyc in the skill folder would count as an unnamed file
spec = importlib.util.spec_from_file_location(
    "claude_ai_import", Path(__file__).parents[1] / "scripts" / "claude_ai_import.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_self_test():
    mod.self_test()
