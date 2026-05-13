import pandas as pd
import numpy as np
from loguru import logger as log
from pytz import timezone

EASTERN = timezone('US/Eastern')
REQUIRED_COLUMNS = ['open', 'high', 'low', 'close', 'volume']

def validate_dataframe(df, min_bars=30, caller="unknown") -> bool:
    """Validates OHLCV DataFrame. Returns True if safe to use, False otherwise."""
    if df is None:
        log.warning(f"[{caller}] DataFrame is None")
        return False
    if len(df) < min_bars:
        log.warning(f"[{caller}] Only {len(df)} bars, need {min_bars}")
        return False
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            log.warning(f"[{caller}] Missing column: {col}")
            return False
    if df['close'].iloc[-20:].isna().any():
        log.warning(f"[{caller}] NaN values found in recent close prices")
        return False
    return True

SWING_LOOKBACK = {
    "1m": 8,
    "3m": 6,
    "5m": 5,
    "15m": 4,
    "1h": 3,
    "4h": 3,
    "1d": 2,
}

MIN_FVG_SIZE_POINTS = {"MES": 0.75, "MNQ": 3.0}

KILL_ZONE_REQUIRED = ["ORB", "SMC", "BOS", "FVG", "SWEEP", "AMD", "ASIA"]
KILL_ZONE_OPTIONAL = ["MEAN_REV", "RANGE", "TREND", "VWAP", "FIBONACCI"]
KILL_ZONE_BLOCKED  = ["SCALP"]

def get_swing_lookback(timeframe: str) -> int:
    return SWING_LOOKBACK.get(timeframe.lower(), 5)

def get_min_fvg_size(instrument: str) -> float:
    return MIN_FVG_SIZE_POINTS.get(instrument.upper(), 0.75)

def apply_kill_zone_penalty(confidence: float, strategy_type: str,
                             is_kill_zone: bool) -> float:
    """Adjusts confidence based on session timing rules."""
    if strategy_type in KILL_ZONE_BLOCKED and not is_kill_zone:
        return 0.0
    if strategy_type in KILL_ZONE_REQUIRED and not is_kill_zone:
        return confidence * 0.70
    return confidence
