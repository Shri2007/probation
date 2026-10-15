"""Event loop: pops events in time order and dispatches them."""

from __future__ import annotations

from typing import assert_never

import pandas as pd

from backtester.data import Clock, ClockError, DataHandle, MarketData
from backtester.events import Event, EventQueue, FillEvent, MarketEvent, OrderEvent
from backtester.strategy import Strategy


class Engine:
    def __init__(self, data: MarketData, strategy: Strategy) -> None:
        self._data = data
        self._strategy = strategy
        self._clock = Clock()
        self._handle = DataHandle(data, self._clock)
        self._queue = EventQueue()
        self.order_log: list[OrderEvent] = []

    @property
    def now(self) -> pd.Timestamp | None:
        return self._clock.now

    def run(self) -> None:
        for ts in self._data.timestamps():
            self._push(MarketEvent(ts, self._data.symbols))
        while self._queue:
            event = self._queue.pop()
            self._clock.advance_to(event.timestamp)
            self._dispatch(event)

    def _push(self, event: Event) -> None:
        now = self._clock.now
        if now is not None and event.timestamp < now:
            raise ClockError(f"cannot schedule {event!r} before engine clock {now}")
        self._queue.push(event)

    def _dispatch(self, event: Event) -> None:
        match event:
            case MarketEvent():
                for order in self._strategy.on_market_event(event, self._handle):
                    self._push(order)
            case OrderEvent():
                # No execution handler yet (Milestone 2); just record it.
                self.order_log.append(event)
            case FillEvent():
                raise NotImplementedError("fills are not handled until Milestone 2")
            case _:
                assert_never(event)
