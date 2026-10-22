from decimal import Decimal

import pandas as pd
import pytest

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


@pytest.mark.parametrize("quantity", [0, -1])
def test_order_quantity_must_be_positive(quantity: int) -> None:
    with pytest.raises(ValueError):
        OrderEvent(D1, "AAA", Side.BUY, quantity)


@pytest.mark.parametrize("quantity", [1.5, True, Decimal("1")])
def test_order_quantity_must_be_an_int(quantity: object) -> None:
    with pytest.raises(TypeError):
        OrderEvent(D1, "AAA", Side.BUY, quantity)  # type: ignore[arg-type]


def test_order_side_must_be_a_side_enum() -> None:
    with pytest.raises(TypeError):
        OrderEvent(D1, "AAA", "BUY", 1)  # type: ignore[arg-type]


def test_order_symbol_must_be_a_non_empty_string() -> None:
    with pytest.raises(ValueError):
        OrderEvent(D1, "", Side.BUY, 1)


def test_event_timestamp_must_be_a_pandas_timestamp() -> None:
    with pytest.raises(TypeError):
        OrderEvent("2024-01-02", "AAA", Side.BUY, 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        MarketEvent("2024-01-02", ("AAA",))  # type: ignore[arg-type]


def test_fill_quantity_must_be_positive() -> None:
    with pytest.raises(ValueError):
        FillEvent(D1, "AAA", Side.BUY, 0, Decimal("100"), Decimal("0"))


def test_fill_price_must_be_decimal_not_float() -> None:
    with pytest.raises(TypeError):
        FillEvent(D1, "AAA", Side.BUY, 1, 100.0, Decimal("0"))  # type: ignore[arg-type]


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity"])
def test_fill_price_must_be_finite_and_positive(price: str) -> None:
    with pytest.raises(ValueError):
        FillEvent(D1, "AAA", Side.BUY, 1, Decimal(price), Decimal("0"))


def test_commission_must_be_decimal_not_float() -> None:
    with pytest.raises(TypeError):
        FillEvent(D1, "AAA", Side.BUY, 1, Decimal("100"), 0.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("commission", ["-0.01", "NaN", "Infinity"])
def test_commission_must_be_finite_and_non_negative(commission: str) -> None:
    with pytest.raises(ValueError):
        FillEvent(D1, "AAA", Side.BUY, 1, Decimal("100"), Decimal(commission))
