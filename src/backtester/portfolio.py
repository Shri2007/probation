"""Cash, positions, trade log and equity curve. All money is Decimal."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from backtester.events import FillEvent, Side


class InsufficientCashError(Exception):
    """A fill would make cash negative."""


class InsufficientPositionError(Exception):
    """A sell exceeds the shares held (no shorting)."""


@dataclass(frozen=True, slots=True)
class TradeRecord:
    fill: FillEvent
    cash_after: Decimal
    position_after: int


@dataclass(frozen=True, slots=True)
class EquityPoint:
    timestamp: pd.Timestamp
    cash: Decimal
    holdings_value: Decimal
    equity: Decimal
    positions: dict[str, int]


class Portfolio:
    def __init__(self, initial_cash: Decimal) -> None:
        if not isinstance(initial_cash, Decimal):
            raise TypeError(f"initial_cash must be a Decimal, got {type(initial_cash).__name__}")
        if not initial_cash.is_finite() or initial_cash < 0:
            raise ValueError(f"initial_cash must be finite and >= 0, got {initial_cash}")
        self._cash = initial_cash
        self._positions: dict[str, int] = {}
        self.trade_log: list[TradeRecord] = []
        self.equity_curve: list[EquityPoint] = []

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def positions(self) -> dict[str, int]:
        return dict(self._positions)

    def apply_fill(self, fill: FillEvent) -> None:
        """Apply a fill, or raise and leave the books untouched."""
        notional = fill.fill_price * fill.quantity
        held = self._positions.get(fill.symbol, 0)
        if fill.side is Side.BUY:
            cash = self._cash - notional - fill.commission
            position = held + fill.quantity
        else:
            if fill.quantity > held:
                raise InsufficientPositionError(
                    f"{fill.timestamp} sell {fill.quantity} {fill.symbol}: only {held} held"
                )
            cash = self._cash + notional - fill.commission
            position = held - fill.quantity
        if cash < 0:
            raise InsufficientCashError(
                f"{fill.timestamp} {fill.side.value} {fill.quantity} {fill.symbol} "
                f"@ {fill.fill_price} + {fill.commission}: cash {self._cash} would go to {cash}"
            )

        self._cash = cash
        if position:
            self._positions[fill.symbol] = position
        else:
            del self._positions[fill.symbol]
        self.trade_log.append(TradeRecord(fill, cash, position))

    def mark_to_market(self, timestamp: pd.Timestamp, prices: Mapping[str, Decimal]) -> None:
        holdings = sum(
            (prices[symbol] * qty for symbol, qty in self._positions.items()), Decimal("0")
        )
        equity = self._cash + holdings
        # Copy: a later fill must not rewrite this day's recorded positions.
        snapshot = dict(self._positions)
        self.equity_curve.append(EquityPoint(timestamp, self._cash, holdings, equity, snapshot))
