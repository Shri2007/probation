# Event-Driven Backtesting Engine

A Python backtester that replays historical daily market data event by event,
simulates realistic trading costs, and evaluates strategies with statistical rigor.
The whole point is making common backtesting mistakes (lookahead, ignoring costs,
tuning on test data) hard to commit, and proving it with tests.

## Core loop
market event -> strategy signal -> order -> fill -> portfolio update

Everything flows through one event queue, processed in time order.

## Hard rules (do not break these without asking)
1. Strategies NEVER access data directly. They only get data through the
   point-in-time handle, which only returns bars up to the engine clock.
2. Asking for future data raises `LookaheadError`. Never silently clip or return empty.
3. Orders fill at the NEXT bar's open, never the current close.
4. Money in the ledger is `Decimal` (or integer cents). No floats for cash or positions' value.
   Float prices convert via Decimal(str(float(x))), never Decimal(x).
5. Tests never touch the network. All tests use small synthetic fixtures in tests/fixtures/.
6. Everything is deterministic: same inputs and seeds give identical results.
7. No new dependencies without asking.
8. Test names state the rule they protect, e.g. `test_strategy_cannot_read_future_prices`.

## Commands
- Install: `pip install -e ".[dev]"`
- Test: `pytest -q`
- Lint: `ruff check .`
- Types: `mypy src`
Run all three before saying a task is done.

## Layout
- src/backtester/: data.py, events.py, engine.py, execution.py, portfolio.py,
  strategy.py, metrics.py, walkforward.py
- src/backtester/strategies/: buy_and_hold.py, momentum.py, mean_reversion.py
- tests/: tests, with fixtures/ for synthetic CSVs
- docs/: design doc

## Working style
- Tests first for any invariant: write the failing test, then make it pass.
- Small changes, one thing at a time. Don't refactor unrelated code.
- Commit implementation before the tests that import it, so every commit passes on its own.
- Expected values in accounting tests are hand-computed by me. Never generate them
  from the engine's own output.
- If a design choice isn't covered here, propose options and ask before building.

## Known limitations (keep updated, feeds docs/design.md)
- Daily bars only, no intraday or market impact modeling
- yfinance adjusted prices leak future split/dividend info (handle or document)
- Ticker universe has survivorship bias
- Orders placed on the final bar never fill (there is no next open); they are
  reported in `engine.unfilled_orders`
- No price rounding: fill prices, commissions and cash are full-precision `Decimal`,
  with no tick size or cent rounding
- Lookahead protection guards against accidents, not adversaries: `DataHandle._data`
  (the full history) is reachable from strategy code
