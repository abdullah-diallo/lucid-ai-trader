from loguru import logger as log


def resolve_signal_conflicts(signals: list) -> list:
    """If both LONG and SHORT signals fire for same instrument, keep higher confidence."""
    by_instrument = {}
    for sig in signals:
        inst = sig.get("instrument", "UNKNOWN")
        existing = by_instrument.get(inst)
        if not existing:
            by_instrument[inst] = sig
        else:
            if sig.get("confidence", 0) > existing.get("confidence", 0):
                log.warning(f"Signal conflict on {inst} — keeping higher confidence signal")
                by_instrument[inst] = sig
            else:
                log.warning(f"Signal conflict on {inst} — rejecting lower confidence signal")
    return list(by_instrument.values())
