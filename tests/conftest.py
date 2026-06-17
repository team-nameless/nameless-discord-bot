from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def pytest_addoption(parser):
    # add cli option to skip ffmpeg tests
    parser.addoption(
        "--skip-ffmpeg",
        action="store_true",
        default=False,
        help="skip tests that require ffmpeg",
    )


@pytest.fixture
def requires_ffmpeg(request):
    # skip if ffmpeg is missing or if skip option is passed
    if request.config.getoption("--skip-ffmpeg") or not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available or skipped via command line option")
