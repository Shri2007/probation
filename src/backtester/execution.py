"""Order execution: turns OrderEvents into FillEvents with costs applied."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from backtester.data import DataHandle
from backtester.events import FillEvent, OrderEvent, Side

BPS = Decimal("10000")


class FeeModel(Protocol):
    def commission(self, order: OrderEvent, fill_price: Decimal) -> Decimal: ...


class SlippageModel(Protocol):
    def fill_price(self, side: Side, reference: Decimal) -> Decimal: ...


def _non_negative_decimal(name: str, value: object) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be finite and >= 0, got {value}")


@dataclass(frozen=True, slots=True)
class FlatCommission:
    """The same commission on every fill, regardless of size."""

    per_fill: Decimal

    def __post_init__(self) -> None:
        _non_negative_decimal("per_fill", self.per_fill)

    def commission(self, order: OrderEvent, fill_price: Decimal) -> Decimal:
        return self.per_fill


@dataclass(frozen=True, slots=True)
class FixedBpsSlippage:
    """Moves the fill price `bps` basis points against the trader."""

    bps: Decimal

    def __post_init__(self) -> None:
        _non_negative_decimal("bps", self.bps)

    def fill_price(self, side: Side, reference: Decimal) -> Decimal:
        adjustment = reference * self.bps / BPS
        return reference + adjustment if side is Side.BUY else reference - adjustment


class ExecutionSimulator:
    """Holds submitted orders and fills them at the next bar's open."""

    def __init__(self, data: DataHandle, fees: FeeModel, slippage: SlippageModel) -> None:
        self._data = data
        self._fees = fees
        self._slippage = slippage
        self._pending: list[OrderEvent] = []

    @property
    def pending(self) -> tuple[OrderEvent, ...]:
        return tuple(self._pending)

    def submit(self, order: OrderEvent) -> None:
        self._pending.append(order)

    def fill_pending(self) -> list[FillEvent]:
        """Fill every order placed before now at now's open, in submission order.

        Orders stay pending if they were placed at the current bar, or if their
        symbol has no bar dated exactly now (never fill at a stale price).
        """
        now = self._data.now
        fills: list[FillEvent] = []
        still_pending: list[OrderEvent] = []
        for order in self._pending:
            if order.timestamp >= now:
                still_pending.append(order)
                continue
            bar = self._data.history(order.symbol, 1)
            if bar.index[-1] != now:
                still_pending.append(order)
                continue
            reference = Decimal(str(float(bar["open"].iloc[-1])))
            price = self._slippage.fill_price(order.side, reference)
            commission = self._fees.commission(order, price)
            fills.append(
                FillEvent(now, order.symbol, order.side, order.quantity, price, commission)
            )
        self._pending = still_pending
        return fills
