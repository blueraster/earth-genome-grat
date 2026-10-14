from importlib.resources import files
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def oak_valley() -> Path:
    """Folder of the Oak Valley sample dataset shipped in grat.datasets."""
    return Path(str(files("grat.datasets") / "OakValley"))
