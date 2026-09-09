from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--skip-ffmpeg",
        action="store_true",
        default=False,
        help="skip tests that require ffmpeg",
    )
    parser.addoption(
        "--run-lyrics-api",
        action="store_true",
        default=False,
        help="run real lyrics API tests",
    )
    parser.addoption(
        "--only-run-lyrics-api",
        action="store_true",
        default=False,
        help="only run real lyrics API tests",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--only-run-lyrics-api"):
        selected = []
        deselected = []
        for item in items:
            if item.name == "test_real_lyrics_api":
                selected.append(item)
            else:
                deselected.append(item)
        items[:] = selected
        if deselected:
            config.hook.pytest_deselected(items=deselected)


@pytest.fixture
def requires_ffmpeg(request: pytest.FixtureRequest) -> None:
    if request.config.getoption("--skip-ffmpeg") or not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available or skipped via command line option")


@pytest.fixture
def run_lyrics_api(request: pytest.FixtureRequest) -> None:
    if not (request.config.getoption("--run-lyrics-api") or request.config.getoption("--only-run-lyrics-api")):
        pytest.skip("skipping real lyrics API tests (use --run-lyrics-api or --only-run-lyrics-api to run)")
        # pytest.param
