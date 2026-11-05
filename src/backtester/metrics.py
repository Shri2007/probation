"""Performance metrics computed from a finished run's equity curve and trade log.

Money (equity, commissions) is Decimal in the ledger. Statistics such as returns,
volatility, Sharpe and drawdown are ratios, not money, so they are computed in float
after one explicit Decimal -> float conversion of the equity series.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from backtester.portfolio import EquityPoint, TradeRecord

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True, slots=True)
class Metrics:
    total_return: float
    cagr: float
    volatility: float  # annualized, sample std (ddof=1)
    sharpe: float  # annualized; nan when volatility is zero (undefined, not zero)
    max_drawdown: float  # positive fraction, e.g. 0.10 means a 10% peak-to-trough fall
    max_drawdown_duration: int  # longest stretch underwater, in bars, peak to recovery
    underwater_at_end: bool  # True if the curve ends below its previous peak
    trade_count: int  # number of fills
    commissions_paid: Decimal


def compute_metrics(
    equity_curve: Sequence[EquityPoint],
    trade_log: Sequence[TradeRecord],
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    risk_free_rate: float = 0.0,
) -> Metrics:
    """Summarize a run. Raises ValueError rather than guessing on unusable input."""
    if len(equity_curve) < 2:
        raise ValueError(f"need at least 2 equity points, got {len(equity_curve)}")
    if periods_per_year < 1:
        raise ValueError(f"periods_per_year must be >= 1, got {periods_per_year}")

    equity = [float(point.equity) for point in equity_curve]
    if any(value <= 0 for value in equity):
        raise ValueError("equity must stay positive to compute returns")

    returns = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity))]
    n_returns = len(returns)

    total_return = equity[-1] / equity[0] - 1
    cagr = (equity[-1] / equity[0]) ** (periods_per_year / n_returns) - 1

    volatility = _annualized_std(returns, periods_per_year)
    sharpe = _sharpe(returns, periods_per_year, risk_free_rate)
    max_dd, longest, underwater = _drawdown(equity)

    commissions = sum((record.fill.commission for record in trade_log), Decimal("0"))
    return Metrics(
        total_return=total_return,
        cagr=cagr,
        volatility=volatility,
        sharpe=sharpe,
        max_drawdown=max_dd,
        max_drawdown_duration=longest,
        underwater_at_end=underwater,
        trade_count=len(trade_log),
        commissions_paid=commissions,
    )


def _annualized_std(returns: Sequence[float], periods_per_year: int) -> float:
    if len(returns) < 2:
        return math.nan
    return statistics.stdev(returns) * math.sqrt(periods_per_year)


def _sharpe(returns: Sequence[float], periods_per_year: int, risk_free_rate: float) -> float:
    if len(returns) < 2:
        return math.nan
    excess = [r - risk_free_rate / periods_per_year for r in returns]
    std = statistics.stdev(excess)
    if std == 0:
        return math.nan
    return statistics.fmean(excess) / std * math.sqrt(periods_per_year)


def _drawdown(equity: Sequence[float]) -> tuple[float, int, bool]:
    """Return (max drawdown fraction, longest underwater stretch in bars, underwater at end).

    A stretch runs from a peak to the first bar that gets back to that peak (or to the
    last bar if it never does). Equal to the peak counts as recovered.
    """
    peak = equity[0]
    peak_index = 0
    max_dd = 0.0
    longest = 0
    underwater = False
    for i, value in enumerate(equity):
        if value >= peak:
            if underwater:
                longest = max(longest, i - peak_index)
                underwater = False
            peak = value
            peak_index = i
        else:
            underwater = True
            max_dd = max(max_dd, (peak - value) / peak)
    if underwater:
        longest = max(longest, len(equity) - 1 - peak_index)
    return max_dd, longest, underwater
