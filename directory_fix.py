import os
import sys
from pathlib import Path


cwd = Path(os.getcwd())
required_paths = [cwd / "nameless", cwd / "tests"]
for path in required_paths:
    if path not in sys.path:
        sys.path.append(str(path))
