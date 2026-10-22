"""Hand-computed accounting scenario. Expected values are supplied by hand,
never generated from engine output. Do not edit them to make a test pass."""

from collections.abc import Sequence
from decimal import Decimal
from decimal import Decimal as D
from typing import Any

import pandas as pd
import pytest

from backtester.data import DataHandle, MarketData
from backtester.engine import Engine
from backtester.events import MarketEvent, OrderEvent, Side
from backtester.execution import FixedBpsSlippage, FlatCommission

# (day, symbol, open, close)
SCENARIO_BARS = [
    ("D1", "AAA", D("100"), D("102")),
    ("D1", "BBB", D("50"), D("51")),
    ("D2", "AAA", D("103"), D("101")),
    ("D2", "BBB", D("52"), D("54")),
    ("D3", "AAA", D("102"), D("105")),
    ("D3", "BBB", D("55"), D("53")),
    ("D4", "AAA", D("106"), D("104")),
    ("D4", "BBB", D("52"), D("50")),
]

# (day submitted, symbol, side, qty), in submission order
SCENARIO_ORDERS = [
    ("D1", "AAA", "BUY", 10),
    ("D1", "BBB", "BUY", 20),
    ("D2", "AAA", "SELL", 4),
    ("D3", "BBB", "SELL", 20),
    ("D4", "AAA", "BUY", 5),  # never fills, no next bar
]

START_CASH = D("10000.00")
COMMISSION = D("1.00")

# (day, symbol, side, qty, fill_price, cash_after, position_after)
EXPECTED_TRADES = [
    ("D2", "AAA", "BUY", 10, D("103"), D("8969.00"), 10),   # 1030 + 1
    ("D2", "BBB", "BUY", 20, D("52"),  D("7928.00"), 20),   # 1040 + 1
    ("D3", "AAA", "SELL", 4, D("102"), D("8335.00"), 6),    # 408 - 1
    ("D4", "BBB", "SELL", 20, D("52"), D("9374.00"), 0),    # 1040 - 1
]

# (day, cash, holdings_value, equity, positions)
EXPECTED_EQUITY = [
    ("D1", D("10000.00"), D("0"),    D("10000.00"), {}),
    ("D2", D("7928.00"),  D("2090"), D("10018.00"), {"AAA": 10, "BBB": 20}),
    ("D3", D("8335.00"),  D("1690"), D("10025.00"), {"AAA": 6,  "BBB": 20}),
    ("D4", D("9374.00"),  D("624"),  D("9998.00"),  {"AAA": 6}),
]

EXPECTED_UNFILLED = 1  # the D4 buy of 5 AAA


# ---------------------------------------------------------------------------
# Runner. Everything below only replays the scenario and compares; it must
# never compute or adjust an expected value.
# ---------------------------------------------------------------------------

DAYS = {
    "D1": pd.Timestamp("2026-01-05"),
    "D2": pd.Timestamp("2026-01-06"),
    "D3": pd.Timestamp("2026-01-07"),
    "D4": pd.Timestamp("2026-01-08"),
}
SCENARIO_VOLUME = 1_000_000


def scenario_data() -> MarketData:
    """Bars from SCENARIO_BARS. high/low/volume are filler the engine never reads
    for fills (open) or marks (close)."""
    rows = [
        {
            "date": DAYS[day],
            "symbol": symbol,
            "open": float(open_),
            "high": float(max(open_, close)),
            "low": float(min(open_, close)),
            "close": float(close),
            "volume": SCENARIO_VOLUME,
        }
        for day, symbol, open_, close in SCENARIO_BARS
    ]
    return MarketData(pd.DataFrame(rows))


class ScriptedOrders:
    """Submits SCENARIO_ORDERS on their days, in listed order."""

    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        return [
            OrderEvent(event.timestamp, symbol, Side(side), qty)
            for day, symbol, side, qty in SCENARIO_ORDERS
            if DAYS[day] == event.timestamp
        ]


@pytest.fixture(scope="module")
def engine() -> Engine:
    engine = Engine(
        scenario_data(),
        ScriptedOrders(),
        initial_cash=START_CASH,
        fees=FlatCommission(COMMISSION),
        slippage=FixedBpsSlippage(Decimal("0")),
    )
    engine.run()
    return engine


def mismatches(label: str, fields: dict[str, tuple[Any, Any]]) -> list[str]:
    """`fields` maps name -> (expected, actual). Decimals must be Decimal on both
    sides and compare with exact ==; no tolerance, no rounding."""
    problems = []
    for name, (expected, actual) in fields.items():
        if isinstance(expected, Decimal) and not isinstance(actual, Decimal):
            problems.append(f"{label} {name}: expected Decimal, got {type(actual).__name__}")
        elif expected != actual:
            problems.append(f"{label} {name}: expected {expected!r}, got {actual!r}")
    return problems


def test_scenario_produces_expected_number_of_trades_and_days(engine: Engine) -> None:
    assert len(engine.portfolio.trade_log) == len(EXPECTED_TRADES)
    assert len(engine.portfolio.equity_curve) == len(EXPECTED_EQUITY)


@pytest.mark.parametrize(
    ("index", "row"),
    list(enumerate(EXPECTED_TRADES)),
    ids=[f"{r[0]}-{r[2]}-{r[1]}" for r in EXPECTED_TRADES],
)
def test_trade_matches_hand_computed_values(
    engine: Engine, index: int, row: tuple[Any, ...]
) -> None:
    day, symbol, side, qty, fill_price, cash_after, position_after = row
    record = engine.portfolio.trade_log[index]
    fill = record.fill
    problems = mismatches(
        f"trade {index} ({day} {side} {symbol})",
        {
            "timestamp": (DAYS[day], fill.timestamp),
            "symbol": (symbol, fill.symbol),
            "side": (side, fill.side.value),
            "quantity": (qty, fill.quantity),
            "fill_price": (fill_price, fill.fill_price),
            "commission": (COMMISSION, fill.commission),
            "cash_after": (cash_after, record.cash_after),
            "position_after": (position_after, record.position_after),
        },
    )
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    ("index", "row"),
    list(enumerate(EXPECTED_EQUITY)),
    ids=[r[0] for r in EXPECTED_EQUITY],
)
def test_equity_marked_at_close_matches_hand_computed_values(
    engine: Engine, index: int, row: tuple[Any, ...]
) -> None:
    day, cash, holdings_value, equity, positions = row
    point = engine.portfolio.equity_curve[index]
    problems = mismatches(
        f"equity {day}",
        {
            "timestamp": (DAYS[day], point.timestamp),
            "cash": (cash, point.cash),
            "holdings_value": (holdings_value, point.holdings_value),
            "equity": (equity, point.equity),
            "positions": (positions, dict(point.positions)),
        },
    )
    assert not problems, "\n".join(problems)


def test_order_on_final_bar_is_left_unfilled(engine: Engine) -> None:
    assert len(engine.unfilled_orders) == EXPECTED_UNFILLED
