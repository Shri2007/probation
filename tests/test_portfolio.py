from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from backtester.data import DataHandle, MarketData
from backtester.engine import Engine
from backtester.events import FillEvent, MarketEvent, OrderEvent, Side
from backtester.execution import FixedBpsSlippage, FlatCommission
from backtester.portfolio import InsufficientCashError, InsufficientPositionError, Portfolio

D1 = pd.Timestamp("2024-01-03")
FIRST_DAY = pd.Timestamp("2024-01-02")


def fill(side: Side, quantity: int, price: str, commission: str = "0") -> FillEvent:
    return FillEvent(
        D1, "AAA", side, quantity, Decimal(price), Decimal(commission), Decimal(price)
    )


class SellAAAOnFirstDay:
    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        if event.timestamp == FIRST_DAY:
            return [OrderEvent(event.timestamp, "AAA", Side.SELL, 1)]
        return []


class BuyAAAOnFirstDay:
    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        if event.timestamp == FIRST_DAY:
            return [OrderEvent(event.timestamp, "AAA", Side.BUY, 1)]
        return []


def test_buy_that_would_make_cash_negative_raises_and_leaves_books_unchanged() -> None:
    portfolio = Portfolio(Decimal("100"))
    with pytest.raises(InsufficientCashError):
        portfolio.apply_fill(fill(Side.BUY, 1, "100", commission="0.01"))

    assert portfolio.cash == Decimal("100")
    assert portfolio.positions == {}
    assert portfolio.trade_log == []


def test_buy_costing_exactly_all_cash_is_allowed() -> None:
    portfolio = Portfolio(Decimal("101"))
    portfolio.apply_fill(fill(Side.BUY, 1, "100", commission="1"))

    assert portfolio.cash == Decimal("0")
    assert portfolio.positions == {"AAA": 1}


def test_selling_more_than_held_raises_and_leaves_books_unchanged() -> None:
    portfolio = Portfolio(Decimal("1000"))
    portfolio.apply_fill(fill(Side.BUY, 2, "100"))
    cash_before = portfolio.cash
    with pytest.raises(InsufficientPositionError):
        portfolio.apply_fill(fill(Side.SELL, 3, "100"))

    assert portfolio.positions == {"AAA": 2}
    assert portfolio.cash == cash_before
    assert len(portfolio.trade_log) == 1


def test_selling_with_no_position_raises_because_shorting_is_not_allowed() -> None:
    portfolio = Portfolio(Decimal("1000"))
    with pytest.raises(InsufficientPositionError):
        portfolio.apply_fill(fill(Side.SELL, 1, "100"))


def test_sell_whose_commission_exceeds_cash_plus_proceeds_raises() -> None:
    portfolio = Portfolio(Decimal("1"))
    portfolio.apply_fill(fill(Side.BUY, 1, "1"))
    with pytest.raises(InsufficientCashError):
        portfolio.apply_fill(fill(Side.SELL, 1, "0.50", commission="1"))


def test_trade_log_records_cash_and_position_after_each_fill() -> None:
    portfolio = Portfolio(Decimal("1000"))
    first = fill(Side.BUY, 3, "100")
    second = fill(Side.SELL, 1, "100")
    portfolio.apply_fill(first)
    after_first = (portfolio.cash, portfolio.positions["AAA"])
    portfolio.apply_fill(second)

    records = portfolio.trade_log
    assert [r.fill for r in records] == [first, second]
    assert (records[0].cash_after, records[0].position_after) == after_first
    assert (records[1].cash_after, records[1].position_after) == (
        portfolio.cash,
        portfolio.positions["AAA"],
    )


def test_cash_and_equity_are_decimal_never_float(two_symbols_csv: Path) -> None:
    engine = Engine(
        MarketData.from_csv(two_symbols_csv),
        BuyAAAOnFirstDay(),
        initial_cash=Decimal("10000"),
        fees=FlatCommission(Decimal("1")),
        slippage=FixedBpsSlippage(Decimal("10")),
    )
    engine.run()

    assert isinstance(engine.portfolio.cash, Decimal)
    for point in engine.portfolio.equity_curve:
        assert isinstance(point.cash, Decimal)
        assert isinstance(point.holdings_value, Decimal)
        assert isinstance(point.equity, Decimal)


def test_portfolio_rejects_float_initial_cash() -> None:
    with pytest.raises(TypeError):
        Portfolio(10000.0)  # type: ignore[arg-type]


def test_equity_curve_has_one_close_mark_per_trading_day(two_symbols_csv: Path) -> None:
    data = MarketData.from_csv(two_symbols_csv)
    engine = Engine(
        data,
        BuyAAAOnFirstDay(),
        initial_cash=Decimal("10000"),
        fees=FlatCommission(Decimal("1")),
        slippage=FixedBpsSlippage(Decimal("10")),
    )
    engine.run()

    curve = engine.portfolio.equity_curve
    assert [p.timestamp for p in curve] == data.timestamps()
    assert all(p.equity == p.cash + p.holdings_value for p in curve)


def test_insufficient_cash_aborts_the_run(two_symbols_csv: Path) -> None:
    engine = Engine(
        MarketData.from_csv(two_symbols_csv),
        BuyAAAOnFirstDay(),
        initial_cash=Decimal("50"),
        fees=FlatCommission(Decimal("0")),
        slippage=FixedBpsSlippage(Decimal("0")),
    )
    with pytest.raises(InsufficientCashError):
        engine.run()


def test_oversell_aborts_the_run(two_symbols_csv: Path) -> None:
    engine = Engine(
        MarketData.from_csv(two_symbols_csv),
        SellAAAOnFirstDay(),
        initial_cash=Decimal("10000"),
        fees=FlatCommission(Decimal("0")),
        slippage=FixedBpsSlippage(Decimal("0")),
    )
    with pytest.raises(InsufficientPositionError):
        engine.run()


class BuyAAAOnDays2And4:
    """Orders on day 2 and day 4 fill at the opens of day 3 and day 5."""

    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        if event.timestamp in (pd.Timestamp("2024-01-04"), pd.Timestamp("2024-01-08")):
            return [OrderEvent(event.timestamp, "AAA", Side.BUY, 1)]
        return []


def test_later_fill_does_not_change_earlier_recorded_positions(two_symbols_csv: Path) -> None:
    engine = Engine(
        MarketData.from_csv(two_symbols_csv),
        BuyAAAOnDays2And4(),
        initial_cash=Decimal("10000"),
        fees=FlatCommission(Decimal("0")),
        slippage=FixedBpsSlippage(Decimal("0")),
    )
    engine.run()

    by_day = {p.timestamp: p.positions for p in engine.portfolio.equity_curve}
    assert by_day[pd.Timestamp("2024-01-05")] == {"AAA": 1}  # day 3
    assert by_day[pd.Timestamp("2024-01-09")] == {"AAA": 2}  # day 5
