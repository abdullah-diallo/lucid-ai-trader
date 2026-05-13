"""
backtesting/data_fetcher.py
===========================
Fetches historical OHLCV data via yfinance.
Handles TradingView symbol → yfinance ticker conversion automatically.

Supported:
  Futures  : MES1!, ES1!, MNQ1!, NQ1!, GC1!, CL1!, RTY1!, YM1!
  Forex    : EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF  (or EUR/USD, etc.)
  Stocks   : AAPL, SPY, QQQ, ...
  Crypto   : BTC-USD, ETH-USD
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# TradingView continuous contract → yfinance ticker
_FUTURES_MAP: dict[str, str] = {
    "MES": "MES=F",
    "ES":  "ES=F",
    "MNQ": "MNQ=F",
    "NQ":  "NQ=F",
    "RTY": "RTY=F",
    "YM":  "YM=F",
    "GC":  "GC=F",
    "MGC": "MGC=F",
    "CL":  "CL=F",
    "SI":  "SI=F",
    "ZN":  "ZN=F",
    "ZB":  "ZB=F",
    "6E":  "6E=F",   # EUR/USD futures
    "6B":  "6B=F",   # GBP/USD futures
    "6J":  "6J=F",   # JPY futures
}

# Forex spot → yfinance ticker
_FOREX_MAP: dict[str, str] = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCHF": "USDCHF=X",
    "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
}

# yfinance interval strings and their max history lookback
_INTERVAL_MAX_DAYS: dict[str, int] = {
    "1m":  7,
    "2m":  60,
    "5m":  60,
    "15m": 60,
    "30m": 60,
    "60m": 730,
    "1h":  730,
    "1d":  99999,
    "1wk": 99999,
}


def tv_to_yf(symbol: str) -> str:
    """Convert a TradingView symbol to a yfinance ticker."""
    s = symbol.strip().upper()

    # Strip TradingView prefixes like "CME_MINI:MES1!" or "AMEX:SPY"
    if ":" in s:
        s = s.split(":")[-1]

    # Continuous contract suffix
    if s.endswith("1!"):
        s = s[:-2]
    elif s.endswith("!"):
        s = s[:-1]
    s = s.lstrip("@")

    # Futures
    if s in _FUTURES_MAP:
        return _FUTURES_MAP[s]

    # Forex spot (e.g. "EUR/USD" → "EURUSD")
    s_clean = s.replace("/", "").replace("-", "")
    if s_clean in _FOREX_MAP:
        return _FOREX_MAP[s_clean]

    # Crypto (e.g. "BTCUSD" → "BTC-USD")
    if len(s_clean) == 6 and s_clean.endswith("USD") and s_clean[:3] in ("BTC", "ETH", "SOL", "ADA", "XRP"):
        return f"{s_clean[:3]}-USD"

    return s  # Assume it's already a valid yfinance ticker (e.g. "SPY", "AAPL")


def fetch_ohlcv(
    symbol: str,
    start: str,
    end: str,
    interval: str = "5m",
) -> pd.DataFrame:
    """
    Download OHLCV bars and return a clean DataFrame.

    Parameters
    ----------
    symbol   : TradingView or yfinance symbol
    start    : "YYYY-MM-DD"
    end      : "YYYY-MM-DD"
    interval : yfinance interval string (1m, 5m, 15m, 1h, 1d …)

    Returns
    -------
    DataFrame with columns: open, high, low, close, volume
    DatetimeIndex in US/Eastern timezone
    """
    ticker = tv_to_yf(symbol)
    logger.info("Fetching %s (%s) %s → %s @ %s", symbol, ticker, start, end, interval)

    max_days = _INTERVAL_MAX_DAYS.get(interval, 60)
    try:
        df = yf.download(
            ticker,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
    except Exception as exc:
        raise RuntimeError(f"yfinance download failed for {ticker}: {exc}") from exc

    if df.empty:
        raise ValueError(
            f"No data returned for {ticker} ({start} → {end}, {interval}). "
            f"Note: intraday data is limited to the last {max_days} days."
        )

    # Flatten multi-level columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]

    # Ensure required columns exist
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"Missing column '{col}' in downloaded data for {ticker}")

    if "volume" not in df.columns:
        df["volume"] = 0

    # Convert index to Eastern time
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    import pytz
    df.index = df.index.tz_convert(pytz.timezone("US/Eastern"))

    df = df[["open", "high", "low", "close", "volume"]].dropna()
    logger.info("Fetched %d bars for %s", len(df), ticker)
    return df
