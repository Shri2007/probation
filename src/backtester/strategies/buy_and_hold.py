"""Equal-weight buy-and-hold: the baseline an agent has to beat.

Orders are sized on the first bar's close but fill at the next open, after slippage and
commission. Sizing therefore assumes a worst case: the open is up to `gap_allowance`
above the close, slippage is applied on top, and the commission comes from the same fee
model the engine uses. A larger gap still raises InsufficientCashError at fill time.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_FLOOR, Decimal

from backtester.data import DataHandle
from backtester.events import MarketEvent, OrderEvent, Side
from backtester.execution import FeeModel, SlippageModel
from backtester.portfolio import TradeRecord


def _non_negative_decimal(name: str, value: object) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be finite and >= 0, got {value}")


class BuyAndHold:
    """Splits initial_cash equally across every symbol on the first bar, then holds.

    Pass the same fee and slippage model objects the engine uses, so sizing and fills
    agree on costs.
    """

    def __init__(
        self,
        initial_cash: Decimal,
        *,
        fees: FeeModel,
        slippage: SlippageModel,
        gap_allowance: Decimal,
    ) -> None:
        _non_negative_decimal("initial_cash", initial_cash)
        _non_negative_decimal("gap_allowance", gap_allowance)
        self._cash = initial_cash
        self._fees = fees
        self._slippage = slippage
        self._gap_allowance = gap_allowance
        self._ordered = False

    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        if self._ordered:
            return []
        self._ordered = True
        budget = self._cash / len(event.symbols)
        orders = []
        for symbol in event.symbols:
            close = Decimal(str(float(data.history(symbol, 1)["close"].iloc[-1])))
            worst = self._slippage.fill_price(Side.BUY, close * (1 + self._gap_allowance))
            quantity = self._largest_affordable(event, symbol, worst, budget)
            if quantity < 1:
                raise ValueError(
                    f"budget {budget} per symbol cannot buy one share of {symbol} "
                    f"at worst-case price {worst} plus commission"
                )
            orders.append(OrderEvent(event.timestamp, symbol, Side.BUY, quantity))
        return orders

    def _largest_affordable(
        self, event: MarketEvent, symbol: str, price: Decimal, budget: Decimal
    ) -> int:
        """Largest whole share count with shares * price + commission <= budget."""
        quantity = int((budget / price).to_integral_value(rounding=ROUND_FLOOR))
        while quantity >= 1:
            order = OrderEvent(event.timestamp, symbol, Side.BUY, quantity)
            if price * quantity + self._fees.commission(order, price) <= budget:
                return quantity
            quantity -= 1
        return 0


def cash_after_buys(trade_log: Sequence[TradeRecord]) -> Decimal:
    """Cash left unspent after the baseline's buys. Buy-and-hold never trades again, so
    this is idle cash for the whole run, and it biases a comparison in the agent's favor."""
    if not trade_log:
        raise ValueError("no fills: the baseline never bought anything")
    return trade_log[-1].cash_after
