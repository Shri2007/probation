"""Strategy interface."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backtester.data import DataHandle
from backtester.events import MarketEvent, OrderEvent


class Strategy(Protocol):
    def on_market_event(self, event: MarketEvent, data: DataHandle) -> Sequence[OrderEvent]:
        """React to a new bar. `data` is the only way to read prices."""
        ...
