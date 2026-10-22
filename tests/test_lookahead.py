from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from backtester.data import (
    Clock,
    DataHandle,
    InsufficientHistoryError,
    LookaheadError,
    MarketData,
    UnknownSymbolError,
)
from backtester.engine import Engine
from backtester.events import MarketEvent, OrderEvent
from backtester.execution import FixedBpsSlippage, FlatCommission

ZERO_COSTS = {
    "initial_cash": Decimal("10000"),
    "fees": FlatCommission(Decimal("0")),
    "slippage": FixedBpsSlippage(Decimal("0")),
}


# Trading day index -> date in the fixture.
DAY_2 = pd.Timestamp("2024-01-04")
DAY_3 = pd.Timestamp("2024-01-05")
DAY_4 = pd.Timestamp("2024-01-08")
DAY_5 = pd.Timestamp("2024-01-09")
DAY_6 = pd.Timestamp("2024-01-10")
DAY_10 = pd.Timestamp("2024-01-16")


class PeekAtTomorrow:
    """On day 5, asks for bars ending on day 6."""

    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        if event.timestamp == DAY_5:
            data.history("AAA", 1, end=DAY_6)
        return []


def handle_at(csv: Path, ts: pd.Timestamp) -> DataHandle:
    clock = Clock()
    clock.advance_to(ts)
    return DataHandle(MarketData.from_csv(csv), clock)


def test_strategy_cannot_read_future_prices(two_symbols_csv: Path) -> None:
    engine = Engine(MarketData.from_csv(two_symbols_csv), PeekAtTomorrow(), **ZERO_COSTS)
    with pytest.raises(LookaheadError):
        engine.run()


def test_history_cannot_be_read_before_engine_clock_starts(two_symbols_csv: Path) -> None:
    handle = DataHandle(MarketData.from_csv(two_symbols_csv), Clock())
    with pytest.raises(LookaheadError):
        handle.history("AAA", 1)


def test_history_defaults_to_bars_up_to_and_including_now(two_symbols_csv: Path) -> None:
    result = handle_at(two_symbols_csv, DAY_5).history("AAA", 3)

    expected = pd.DataFrame(
        {
            "open": [103.0, 104.0, 105.0],
            "high": [104.0, 105.0, 106.0],
            "low": [102.0, 103.0, 104.0],
            "close": [103.5, 104.5, 105.5],
            "volume": [1003, 1004, 1005],
        },
        index=pd.DatetimeIndex([DAY_3, DAY_4, DAY_5], name="date"),
    )
    pd.testing.assert_frame_equal(result, expected, check_index_type=False, check_freq=False)


def test_history_with_past_end_returns_exactly_bars_up_to_that_date(
    two_symbols_csv: Path,
) -> None:
    result = handle_at(two_symbols_csv, DAY_10).history("BBB", 3, end=DAY_4)

    assert list(result.index) == [DAY_2, DAY_3, DAY_4]
    assert list(result["close"]) == [197.5, 196.5, 195.5]


def test_mutating_history_result_does_not_change_stored_data(two_symbols_csv: Path) -> None:
    handle = handle_at(two_symbols_csv, DAY_5)
    first = handle.history("AAA", 3)
    first.loc[:, "close"] = -1.0

    assert list(handle.history("AAA", 3)["close"]) == [103.5, 104.5, 105.5]


def test_asking_for_more_bars_than_exist_raises_instead_of_clipping(
    two_symbols_csv: Path,
) -> None:
    # Day 2 has exactly 3 bars of history (days 0, 1, 2).
    handle = handle_at(two_symbols_csv, DAY_2)
    assert len(handle.history("AAA", 3)) == 3
    with pytest.raises(InsufficientHistoryError):
        handle.history("AAA", 4)


def test_unknown_symbol_raises_unknown_symbol_error(two_symbols_csv: Path) -> None:
    handle = handle_at(two_symbols_csv, DAY_5)
    with pytest.raises(UnknownSymbolError):
        handle.history("ZZZ", 1)
    assert issubclass(UnknownSymbolError, KeyError)
