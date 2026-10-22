from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pandas as pd

from backtester.data import DataHandle, MarketData
from backtester.engine import Engine
from backtester.events import MarketEvent, OrderEvent, Side
from backtester.execution import FixedBpsSlippage, FlatCommission

DAY_3 = pd.Timestamp("2024-01-05")
DAY_4 = pd.Timestamp("2024-01-08")
LAST_DAY = pd.Timestamp("2024-02-12")

ZERO_FEES = FlatCommission(Decimal("0"))
ZERO_SLIPPAGE = FixedBpsSlippage(Decimal("0"))


class OrderOn:
    """Buys `quantity` AAA on each listed day."""

    def __init__(self, *days: pd.Timestamp, quantity: int = 1) -> None:
        self.days = set(days)
        self.quantity = quantity

    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        if event.timestamp in self.days:
            return [OrderEvent(event.timestamp, "AAA", Side.BUY, self.quantity)]
        return []


class BuyAAAEveryDay:
    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        return [OrderEvent(event.timestamp, "AAA", Side.BUY, 1)]


def test_order_fills_at_next_bars_open_never_current_close(two_symbols_csv: Path) -> None:
    engine = Engine(
        MarketData.from_csv(two_symbols_csv),
        OrderOn(DAY_3),
        initial_cash=Decimal("10000"),
        fees=ZERO_FEES,
        slippage=ZERO_SLIPPAGE,
    )
    engine.run()

    (record,) = engine.portfolio.trade_log
    assert record.fill.timestamp == DAY_4
    # Fixture: day 4 open = 104, day 3 close = 103.5, day 4 close = 104.5.
    assert record.fill.fill_price == Decimal("104")


def test_order_on_final_bar_never_fills_and_is_reported_unfilled(two_symbols_csv: Path) -> None:
    order_strategy = OrderOn(LAST_DAY)
    engine = Engine(
        MarketData.from_csv(two_symbols_csv),
        order_strategy,
        initial_cash=Decimal("10000"),
        fees=ZERO_FEES,
        slippage=ZERO_SLIPPAGE,
    )
    engine.run()

    assert engine.unfilled_orders == [OrderEvent(LAST_DAY, "AAA", Side.BUY, 1)]
    assert engine.portfolio.trade_log == []
    assert engine.portfolio.positions == {}
    assert engine.portfolio.cash == Decimal("10000")


def test_costs_strictly_lower_final_equity(two_symbols_csv: Path) -> None:
    def final_equity(fees: FlatCommission, slippage: FixedBpsSlippage) -> Decimal:
        engine = Engine(
            MarketData.from_csv(two_symbols_csv),
            BuyAAAEveryDay(),
            initial_cash=Decimal("10000"),
            fees=fees,
            slippage=slippage,
        )
        engine.run()
        return engine.portfolio.equity_curve[-1].equity

    with_costs = final_equity(FlatCommission(Decimal("1")), FixedBpsSlippage(Decimal("10")))
    without_costs = final_equity(ZERO_FEES, ZERO_SLIPPAGE)

    assert with_costs < without_costs


def test_slippage_is_adverse_on_both_sides() -> None:
    slippage = FixedBpsSlippage(Decimal("10"))
    reference = Decimal("100")

    assert slippage.fill_price(Side.BUY, reference) > reference
    assert slippage.fill_price(Side.SELL, reference) < reference


def test_zero_bps_slippage_fills_at_reference_price() -> None:
    slippage = FixedBpsSlippage(Decimal("0"))

    assert slippage.fill_price(Side.BUY, Decimal("100")) == Decimal("100")
    assert slippage.fill_price(Side.SELL, Decimal("100")) == Decimal("100")


def test_flat_commission_is_the_same_for_every_fill() -> None:
    fees = FlatCommission(Decimal("1.25"))
    small = OrderEvent(DAY_3, "AAA", Side.BUY, 1)
    large = OrderEvent(DAY_3, "BBB", Side.SELL, 500)

    assert fees.commission(small, Decimal("10")) == Decimal("1.25")
    assert fees.commission(large, Decimal("999")) == Decimal("1.25")
