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


@dataclass(frozen=True, slots=True)
class MarketEvent:
    """A new bar is available for every listed symbol. Carries no prices:
    strategies must read data through the point-in-time handle."""

    timestamp: pd.Timestamp
    symbols: tuple[str, ...]
    priority: ClassVar[EventPriority] = EventPriority.MARKET


@dataclass(frozen=True, slots=True)
class OrderEvent:
    timestamp: pd.Timestamp
    symbol: str
    side: Side
    quantity: int
    priority: ClassVar[EventPriority] = EventPriority.ORDER


@dataclass(frozen=True, slots=True)
class FillEvent:
    timestamp: pd.Timestamp
    symbol: str
    side: Side
    quantity: int
    fill_price: Decimal
    commission: Decimal
    priority: ClassVar[EventPriority] = EventPriority.FILL


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

    def pop(self) -> Event:
        return heapq.heappop(self._heap)[-1]

    def __len__(self) -> int:
        return len(self._heap)
