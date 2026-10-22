"""Event types and the time-ordered event queue."""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, IntEnum
from typing import ClassVar

import pandas as pd


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class EventPriority(IntEnum):
    """Tie-break order for events sharing a timestamp.

    On day D: fills from D-1's orders happen at D's open, then the strategy
    sees D's bar, then it emits new orders.
    """

    FILL = 0
    MARKET = 1
    ORDER = 2


def _check_timestamp(timestamp: object) -> None:
    if not isinstance(timestamp, pd.Timestamp):
        raise TypeError(f"timestamp must be a pd.Timestamp, got {type(timestamp).__name__}")


def _check_symbol(symbol: object) -> None:
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be a str, got {type(symbol).__name__}")
    if not symbol:
        raise ValueError("symbol must be non-empty")


def _check_trade(side: object, quantity: object) -> None:
    if not isinstance(side, Side):
        raise TypeError(f"side must be a Side, got {type(side).__name__}")
    # bool is an int subclass; True shares is a bug, not a quantity.
    if not isinstance(quantity, int) or isinstance(quantity, bool):
        raise TypeError(f"quantity must be an int, got {type(quantity).__name__}")
    if quantity < 1:
        raise ValueError(f"quantity must be >= 1, got {quantity}")


def _check_money(name: str, value: object, *, allow_zero: bool) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite, got {value}")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'>= 0' if allow_zero else '> 0'}, got {value}")


@dataclass(frozen=True, slots=True)
class MarketEvent:
    """A new bar is available for every listed symbol. Carries no prices:
    strategies must read data through the point-in-time handle."""

    timestamp: pd.Timestamp
    symbols: tuple[str, ...]
    priority: ClassVar[EventPriority] = EventPriority.MARKET

    def __post_init__(self) -> None:
        _check_timestamp(self.timestamp)
        for symbol in self.symbols:
            _check_symbol(symbol)


@dataclass(frozen=True, slots=True)
class OrderEvent:
    timestamp: pd.Timestamp
    symbol: str
    side: Side
    quantity: int
    priority: ClassVar[EventPriority] = EventPriority.ORDER

    def __post_init__(self) -> None:
        _check_timestamp(self.timestamp)
        _check_symbol(self.symbol)
        _check_trade(self.side, self.quantity)


@dataclass(frozen=True, slots=True)
class FillEvent:
    timestamp: pd.Timestamp
    symbol: str
    side: Side
    quantity: int
    fill_price: Decimal
    commission: Decimal
    priority: ClassVar[EventPriority] = EventPriority.FILL

    def __post_init__(self) -> None:
        _check_timestamp(self.timestamp)
        _check_symbol(self.symbol)
        _check_trade(self.side, self.quantity)
        _check_money("fill_price", self.fill_price, allow_zero=False)
        _check_money("commission", self.commission, allow_zero=True)


Event = MarketEvent | OrderEvent | FillEvent


class EventQueue:
    """Min-heap keyed on (timestamp, priority, insertion seq).

    The sequence number makes ordering fully deterministic and FIFO for
    exact ties, and means event objects are never compared directly.
    """

    def __init__(self) -> None:
        self._heap: list[tuple[pd.Timestamp, int, int, Event]] = []
        self._seq = itertools.count()

    def push(self, event: Event) -> None:
        heapq.heappush(
            self._heap, (event.timestamp, int(event.priority), next(self._seq), event)
        )

    def peek(self) -> Event:
        return self._heap[0][-1]

    def pop(self) -> Event:
        return heapq.heappop(self._heap)[-1]

    def __len__(self) -> int:
        return len(self._heap)
