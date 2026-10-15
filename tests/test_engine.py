from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import pytest

from backtester.data import Clock, ClockError, DataHandle, MarketData
from backtester.engine import Engine
from backtester.events import MarketEvent, OrderEvent, Side

FIRST_DAY = pd.Timestamp("2024-01-02")
LAST_DAY = pd.Timestamp("2024-02-12")


class Recorder:
    def __init__(self) -> None:
        self.seen: list[tuple[pd.Timestamp, pd.Timestamp, tuple[str, ...]]] = []

    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        self.seen.append((event.timestamp, data.now, event.symbols))
        return []


class BuyWhenCloseIsUp:
    """Buys 1 share of each symbol whose close rose versus the prior day."""

    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        if event.timestamp == FIRST_DAY:
            return []
        orders = []
        for symbol in event.symbols:
            prev, today = data.history(symbol, 2)["close"]
            if today > prev:
                orders.append(OrderEvent(event.timestamp, symbol, Side.BUY, 1))
        return orders


class BackdatedOrder:
    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        return [OrderEvent(event.timestamp - pd.Timedelta(days=1), "AAA", Side.BUY, 1)]


def test_strategy_sees_every_day_once_in_order_with_clock_at_event_time(
    two_symbols_csv: Path,
) -> None:
    recorder = Recorder()
    Engine(MarketData.from_csv(two_symbols_csv), recorder).run()

    timestamps = [ts for ts, _, _ in recorder.seen]
    assert len(timestamps) == 30
    assert timestamps == sorted(set(timestamps))
    assert timestamps[0] == FIRST_DAY
    assert timestamps[-1] == LAST_DAY
    assert all(ts == now for ts, now, _ in recorder.seen)
    assert all(symbols == ("AAA", "BBB") for _, _, symbols in recorder.seen)


def test_orders_returned_by_strategy_are_logged(two_symbols_csv: Path) -> None:
    engine = Engine(MarketData.from_csv(two_symbols_csv), BuyWhenCloseIsUp())
    engine.run()

    # AAA's close rises every day after the first; BBB's falls every day.
    assert len(engine.order_log) == 29
    assert {o.symbol for o in engine.order_log} == {"AAA"}
    assert engine.order_log[0].timestamp == pd.Timestamp("2024-01-03")
    assert engine.order_log[-1].timestamp == LAST_DAY


def test_same_inputs_produce_identical_order_logs(two_symbols_csv: Path) -> None:
    runs = []
    for _ in range(2):
        engine = Engine(MarketData.from_csv(two_symbols_csv), BuyWhenCloseIsUp())
        engine.run()
        runs.append(engine.order_log)

    assert runs[0] == runs[1]


def test_clock_cannot_move_backwards() -> None:
    clock = Clock()
    clock.advance_to(pd.Timestamp("2024-01-03"))
    with pytest.raises(ClockError):
        clock.advance_to(pd.Timestamp("2024-01-02"))


def test_engine_rejects_events_scheduled_before_the_clock(two_symbols_csv: Path) -> None:
    engine = Engine(MarketData.from_csv(two_symbols_csv), BackdatedOrder())
    with pytest.raises(ClockError):
        engine.run()
