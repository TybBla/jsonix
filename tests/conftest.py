from pathlib import Path

import pytest

from odw2json.logging_setup import reset_logging

ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "data" / "train"


@pytest.fixture
def train_dir() -> Path:
    return TRAIN


@pytest.fixture(autouse=True)
def _reset_logging_after_test():
    yield
    reset_logging()
