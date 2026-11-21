from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "data" / "train"


@pytest.fixture
def train_dir() -> Path:
    return TRAIN
