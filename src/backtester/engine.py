"""Event loop: pops events in time order and dispatches them."""

from __future__ import annotations

from decimal import Decimal
from typing import assert_never

import pandas as pd

from backtester.data import Clock, ClockError, DataHandle, MarketData
from backtester.events import Event, EventQueue, FillEvent, MarketEvent, OrderEvent
from backtester.execution import ExecutionSimulator, FeeModel, SlippageModel
from backtester.portfolio import Portfolio
from backtester.strategy import Strategy


class Engine:
    def __init__(
        self,
        data: MarketData,
        strategy: Strategy,
        *,
        initial_cash: Decimal,
        fees: FeeModel,
        slippage: SlippageModel,
    ) -> None:
        self._data = data
        self._strategy = strategy
        self._clock = Clock()
        self._handle = DataHandle(data, self._clock)
        self._queue = EventQueue()
        self.execution = ExecutionSimulator(self._handle, fees, slippage)
        self.portfolio = Portfolio(initial_cash)
        self.order_log: list[OrderEvent] = []
        self.unfilled_orders: list[OrderEvent] = []

    @property
    def now(self) -> pd.Timestamp | None:
        return self._clock.now

    def run(self) -> None:
        for ts in self._data.timestamps():
            self._push(MarketEvent(ts, self._data.symbols))
        while self._queue:
            next_ts = self._queue.peek().timestamp
            if self._clock.now is None or next_ts > self._clock.now:
                self._open_bar(next_ts)
            event = self._queue.pop()
            self._clock.advance_to(event.timestamp)
            self._dispatch(event)
        # No bar left to fill at: these orders never execute.
        self.unfilled_orders = list(self.execution.pending)

    def _open_bar(self, ts: pd.Timestamp) -> None:
        """Advance to a new bar and queue fills at its open. FILL priority makes
        them pop before this bar's MarketEvent, so the strategy sees them applied."""
        self._clock.advance_to(ts)
        for fill in self.execution.fill_pending():
            self._push(fill)

    def _push(self, event: Event) -> None:
        now = self._clock.now
        if now is not None and event.timestamp < now:
            raise ClockError(f"cannot schedule {event!r} before engine clock {now}")
        self._queue.push(event)

    def _dispatch(self, event: Event) -> None:
        match event:
            case MarketEvent():
                for order in self._strategy.on_market_event(event, self._handle):
                    if order.timestamp != event.timestamp:
                        raise ClockError(f"order {order!r} must be dated {event.timestamp}")
                    self._push(order)
                self._mark_to_market(event)
            case OrderEvent():
                self.order_log.append(event)
                self.execution.submit(event)
            case FillEvent():
                self.portfolio.apply_fill(event)
            case _:
                assert_never(event)

    def _mark_to_market(self, event: MarketEvent) -> None:
        closes = {
            symbol: Decimal(str(float(self._handle.history(symbol, 1)["close"].iloc[-1])))
            for symbol in self.portfolio.positions
        }
        self.portfolio.mark_to_market(event.timestamp, closes)
