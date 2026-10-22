"""Hand-computed accounting scenario. Expected values are supplied by hand,
never generated from engine output. Do not edit them to make a test pass."""

from decimal import Decimal as D

# (day, symbol, open, close)
SCENARIO_BARS = [
    ("D1", "AAA", D("100"), D("102")),
    ("D1", "BBB", D("50"), D("51")),
    ("D2", "AAA", D("103"), D("101")),
    ("D2", "BBB", D("52"), D("54")),
    ("D3", "AAA", D("102"), D("105")),
    ("D3", "BBB", D("55"), D("53")),
    ("D4", "AAA", D("106"), D("104")),
    ("D4", "BBB", D("52"), D("50")),
]

# (day submitted, symbol, side, qty), in submission order
SCENARIO_ORDERS = [
    ("D1", "AAA", "BUY", 10),
    ("D1", "BBB", "BUY", 20),
    ("D2", "AAA", "SELL", 4),
    ("D3", "BBB", "SELL", 20),
    ("D4", "AAA", "BUY", 5),  # never fills, no next bar
]

START_CASH = D("10000.00")
COMMISSION = D("1.00")

# (day, symbol, side, qty, fill_price, cash_after, position_after)
EXPECTED_TRADES = [
    ("D2", "AAA", "BUY", 10, D("103"), D("8969.00"), 10),   # 1030 + 1
    ("D2", "BBB", "BUY", 20, D("52"),  D("7928.00"), 20),   # 1040 + 1
    ("D3", "AAA", "SELL", 4, D("102"), D("8335.00"), 6),    # 408 - 1
    ("D4", "BBB", "SELL", 20, D("52"), D("9374.00"), 0),    # 1040 - 1
]

# (day, cash, holdings_value, equity, positions)
EXPECTED_EQUITY = [
    ("D1", D("10000.00"), D("0"),    D("10000.00"), {}),
    ("D2", D("7928.00"),  D("2090"), D("10018.00"), {"AAA": 10, "BBB": 20}),
    ("D3", D("8335.00"),  D("1690"), D("10025.00"), {"AAA": 6,  "BBB": 20}),
    ("D4", D("9374.00"),  D("624"),  D("9998.00"),  {"AAA": 6}),
]

EXPECTED_UNFILLED = 1  # the D4 buy of 5 AAA
