from decimal import Decimal

import pandas as pd

from backtester.events import EventQueue, FillEvent, MarketEvent, OrderEvent, Side

D1 = pd.Timestamp("2024-01-02")
D2 = pd.Timestamp("2024-01-03")


def test_queue_pops_events_in_timestamp_order() -> None:
    queue = EventQueue()
    later = MarketEvent(D2, ("AAA",))
    earlier = MarketEvent(D1, ("AAA",))
    queue.push(later)
    queue.push(earlier)

    assert [queue.pop(), queue.pop()] == [earlier, later]


def test_same_timestamp_pops_fill_then_market_then_order() -> None:
    queue = EventQueue()
    order = OrderEvent(D1, "AAA", Side.BUY, 10)
    market = MarketEvent(D1, ("AAA",))
    fill = FillEvent(D1, "AAA", Side.BUY, 10, Decimal("100.00"), Decimal("0"))
    for event in (order, market, fill):
        queue.push(event)

    assert [queue.pop() for _ in range(3)] == [fill, market, order]


def test_identical_timestamp_and_type_pop_in_insertion_order() -> None:
    queue = EventQueue()
    orders = [OrderEvent(D1, sym, Side.BUY, 1) for sym in ("CCC", "AAA", "BBB")]
    for order in orders:
        queue.push(order)

    assert [queue.pop() for _ in range(3)] == orders
