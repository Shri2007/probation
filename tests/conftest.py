from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def two_symbols_csv() -> Path:
    """30 trading days from 2024-01-02, AAA and BBB.

    For trading day index i (0-based):
      AAA: open 100+i, high 101+i, low 99+i, close 100.5+i, volume 1000+i
      BBB: open 200-i, high 201-i, low 199-i, close 199.5-i, volume 2000+i
    """
    return FIXTURES / "two_symbols_30d.csv"
