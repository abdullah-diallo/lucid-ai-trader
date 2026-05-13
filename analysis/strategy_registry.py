STRATEGY_REGISTRY = {
    "ORB_LONG":                {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "ORB_SHORT":               {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "BREAK_RETEST_LONG":       {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "BREAK_RETEST_SHORT":      {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "SWEEP_REVERSAL_LONG":     {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "SWEEP_REVERSAL_SHORT":    {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "MEAN_REVERSION_LONG":     {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "MEAN_REVERSION_SHORT":    {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "FVG_LONG":                {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "FVG_SHORT":               {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "IFVG_LONG":               {"active": True, "min_confidence": 0.62, "filters": [], "improvement_attempts": 0},
    "IFVG_SHORT":              {"active": True, "min_confidence": 0.62, "filters": [], "improvement_attempts": 0},
    "FIB_RETRACEMENT_LONG":    {"active": True, "min_confidence": 0.67, "filters": [], "improvement_attempts": 0},
    "FIB_RETRACEMENT_SHORT":   {"active": True, "min_confidence": 0.67, "filters": [], "improvement_attempts": 0},
    "VWAP_RECLAIM_LONG":       {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "VWAP_REJECTION_SHORT":    {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "FADE_SHORT":              {"active": True, "min_confidence": 0.68, "filters": [], "improvement_attempts": 0},
    "FADE_LONG":               {"active": True, "min_confidence": 0.68, "filters": [], "improvement_attempts": 0},
    "RANGE_LONG":              {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "RANGE_SHORT":             {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "ASIA_RANGE_BULL":         {"active": True, "min_confidence": 0.67, "filters": [], "improvement_attempts": 0},
    "ASIA_RANGE_BEAR":         {"active": True, "min_confidence": 0.67, "filters": [], "improvement_attempts": 0},
    "NEWS_CONTINUATION_LONG":  {"active": True, "min_confidence": 0.68, "filters": [], "improvement_attempts": 0},
    "NEWS_CONTINUATION_SHORT": {"active": True, "min_confidence": 0.68, "filters": [], "improvement_attempts": 0},
    "GAP_GO_LONG":             {"active": True, "min_confidence": 0.68, "filters": [], "improvement_attempts": 0},
    "GAP_GO_SHORT":            {"active": True, "min_confidence": 0.68, "filters": [], "improvement_attempts": 0},
    "BOS_LONG":                {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "BOS_SHORT":               {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "SMC_LONG":                {"active": True, "min_confidence": 0.72, "filters": [], "improvement_attempts": 0},
    "SMC_SHORT":               {"active": True, "min_confidence": 0.72, "filters": [], "improvement_attempts": 0},
    "MOMENTUM_LONG":           {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "MOMENTUM_SHORT":          {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "BREAKOUT_LONG":           {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "BREAKOUT_SHORT":          {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "SCALP_LONG":              {"active": True, "min_confidence": 0.70, "filters": [], "improvement_attempts": 0},
    "SCALP_SHORT":             {"active": True, "min_confidence": 0.70, "filters": [], "improvement_attempts": 0},
    "TREND_FOLLOW_LONG":       {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "TREND_FOLLOW_SHORT":      {"active": True, "min_confidence": 0.65, "filters": [], "improvement_attempts": 0},
    "REVERSAL_LONG":           {"active": True, "min_confidence": 0.70, "filters": [], "improvement_attempts": 0},
    "REVERSAL_SHORT":          {"active": True, "min_confidence": 0.70, "filters": [], "improvement_attempts": 0},
    "AMD_DISTRIBUTION_LONG":   {"active": True, "min_confidence": 0.70, "filters": [], "improvement_attempts": 0},
    "AMD_DISTRIBUTION_SHORT":  {"active": True, "min_confidence": 0.70, "filters": [], "improvement_attempts": 0},
}


def is_strategy_active(strategy_code: str) -> bool:
    entry = STRATEGY_REGISTRY.get(strategy_code, {})
    return entry.get("active", False)


def get_min_confidence(strategy_code: str) -> float:
    entry = STRATEGY_REGISTRY.get(strategy_code, {})
    return entry.get("min_confidence", 0.65)


def add_filter(strategy_code: str, filter_dict: dict) -> bool:
    """Called by self_improvement_engine to add a filter to a strategy."""
    if strategy_code in STRATEGY_REGISTRY:
        STRATEGY_REGISTRY[strategy_code]["filters"].append(filter_dict)
        return True
    return False


def pause_strategy(strategy_code: str, reason: str) -> bool:
    if strategy_code in STRATEGY_REGISTRY:
        STRATEGY_REGISTRY[strategy_code]["active"] = False
        STRATEGY_REGISTRY[strategy_code]["pause_reason"] = reason
        return True
    return False


def resume_strategy(strategy_code: str) -> bool:
    if strategy_code in STRATEGY_REGISTRY:
        STRATEGY_REGISTRY[strategy_code]["active"] = True
        STRATEGY_REGISTRY[strategy_code].pop("pause_reason", None)
        return True
    return False
