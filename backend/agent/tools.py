"""Tool schemas passed to the Claude API."""

TOOLS = [
    {
        "name": "get_portfolio_snapshot",
        "description": (
            "Fetch the current market value, P&L, and weight of each holding "
            "in a client's portfolio using live prices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "integer", "description": "Portfolio database ID"}
            },
            "required": ["portfolio_id"],
        },
    },
    {
        "name": "get_performance_metrics",
        "description": (
            "Compute annualized return, volatility, Sharpe ratio, and max drawdown "
            "for a portfolio over a given period, compared to a benchmark (default SPY)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "integer"},
                "period": {
                    "type": "string",
                    "enum": ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
                    "description": "Lookback period for performance calculation",
                },
                "benchmark": {
                    "type": "string",
                    "description": "Benchmark ticker, e.g. SPY, QQQ",
                    "default": "SPY",
                },
            },
            "required": ["portfolio_id"],
        },
    },
    {
        "name": "get_ticker_info",
        "description": "Get metadata for a stock ticker: name, sector, P/E ratio, market cap, 52-week range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"}
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "suggest_rebalancing",
        "description": (
            "Compare the portfolio's current allocation against target weights "
            "and surface positions that have drifted beyond a threshold."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "integer"},
                "target_weights": {
                    "type": "object",
                    "description": "Map of ticker -> target weight percentage, e.g. {AAPL: 25, MSFT: 25}",
                },
                "threshold_pct": {
                    "type": "number",
                    "description": "Minimum drift (%) before flagging a position",
                    "default": 5.0,
                },
            },
            "required": ["portfolio_id", "target_weights"],
        },
    },
    {
        "name": "optimize_portfolio",
        "description": (
            "Run mean-variance (Markowitz) optimization on the portfolio's current tickers "
            "and return the max Sharpe ratio weights with expected performance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "integer"},
                "period": {
                    "type": "string",
                    "enum": ["1y", "2y", "3y", "5y"],
                    "default": "1y",
                },
            },
            "required": ["portfolio_id"],
        },
    },
]
