"""Market data storage and the point-in-time handle strategies read through."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BAR_COLUMNS = ["open", "high", "low", "close", "volume"]


class LookaheadError(Exception):
    """A request reached past the engine clock."""


class InsufficientHistoryError(Exception):
    """Fewer bars exist up to the requested time than were asked for."""


class UnknownSymbolError(KeyError):
    """The symbol is not in the loaded data."""


class ClockError(RuntimeError):
    """Something tried to move time backwards."""


class Clock:
    """Engine-owned clock. Strategies never receive this object, only a
    DataHandle that reads from it."""

    def __init__(self) -> None:
        self._now: pd.Timestamp | None = None

    @property
    def now(self) -> pd.Timestamp | None:
        return self._now

    def advance_to(self, ts: pd.Timestamp) -> None:
        if self._now is not None and ts < self._now:
            raise ClockError(f"clock cannot move backwards from {self._now} to {ts}")
        self._now = ts


class MarketData:
    """Full daily bar history. Only the engine holds a reference to this."""

    def __init__(self, frame: pd.DataFrame) -> None:
        missing = {"date", "symbol", *BAR_COLUMNS} - set(frame.columns)
        if missing:
            raise ValueError(f"missing columns: {sorted(missing)}")
        if frame.duplicated(["date", "symbol"]).any():
            raise ValueError("duplicate (date, symbol) rows")
        frame = frame.assign(date=pd.to_datetime(frame["date"]))
        self._bars: dict[str, pd.DataFrame] = {
            str(symbol): group.set_index("date")[BAR_COLUMNS].sort_index()
            for symbol, group in frame.groupby("symbol", sort=True)
        }
        self._timestamps = sorted(pd.DatetimeIndex(frame["date"]).unique())

    @classmethod
    def from_csv(cls, path: Path) -> MarketData:
        return cls(pd.read_csv(path))

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(self._bars)

    def timestamps(self) -> list[pd.Timestamp]:
        return list(self._timestamps)

    def bars(self, symbol: str) -> pd.DataFrame:
        """Every bar for `symbol`, past and future. Not for strategies."""
        try:
            return self._bars[symbol]
        except KeyError:
            raise UnknownSymbolError(symbol) from None


class DataHandle:
    """Point-in-time view: only bars at or before the engine clock."""

    def __init__(self, data: MarketData, clock: Clock) -> None:
        self._data = data
        self._clock = clock

    @property
    def now(self) -> pd.Timestamp:
        now = self._clock.now
        if now is None:
            raise LookaheadError("engine clock has not started")
        return now

    def history(self, symbol: str, n: int, end: pd.Timestamp | None = None) -> pd.DataFrame:
        """The last `n` bars with timestamp <= `end` (default: now), as a copy."""
        now = self.now
        end = now if end is None else pd.Timestamp(end)
        if end > now:
            raise LookaheadError(f"{symbol}: requested bars up to {end}, clock is at {now}")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        visible = self._data.bars(symbol).loc[:end]
        if len(visible) < n:
            raise InsufficientHistoryError(
                f"{symbol}: asked for {n} bars up to {end}, only {len(visible)} exist"
            )
        return visible.iloc[-n:].copy()
