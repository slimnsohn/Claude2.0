"""Calibration metrics from resolution audit data."""

import logging

from db.database import Database

logger = logging.getLogger(__name__)


def calculate_calibration_metrics(db: Database = None) -> dict:
    """
    From audit data, calculate:
    - What % of flagged mismatches actually led to 'surprise' resolutions?
    - What severity level is most predictive?
    - What's the average PnL if you traded on our flags?
    """
    db = db or Database()
    audits = db.get_all_audits()

    if not audits:
        return {"error": "No audit data available"}

    flagged = [a for a in audits if a.get("mismatch_was_flagged")]
    surprise_resolutions = [a for a in flagged if not a.get("resolved_per_rules")]

    # By severity breakdown
    by_severity = {}
    for sev in ["high", "medium", "low"]:
        sev_flagged = [a for a in flagged if a.get("mismatch_severity_at_flag") == sev]
        sev_surprised = [a for a in surprise_resolutions if a.get("mismatch_severity_at_flag") == sev]
        by_severity[sev] = {
            "flagged": len(sev_flagged),
            "surprised": len(sev_surprised),
            "surprise_rate": len(sev_surprised) / max(len(sev_flagged), 1),
        }

    # Hypothetical PnL: if you took the opposite side of retail assumption at flag time
    pnl_data = []
    for a in flagged:
        price_at_flag = a.get("price_at_flag")
        price_at_resolution = a.get("price_at_resolution")
        if price_at_flag is not None and price_at_resolution is not None:
            # Simplified: if mismatch found and we bet NO (against retail YES assumption)
            # PnL = (1 - price_at_resolution) - (1 - price_at_flag) = price_at_flag - price_at_resolution
            pnl = price_at_flag - price_at_resolution
            pnl_data.append(pnl)

    avg_pnl = sum(pnl_data) / max(len(pnl_data), 1) if pnl_data else None

    metrics = {
        "total_audited": len(audits),
        "total_flagged": len(flagged),
        "total_surprises": len(surprise_resolutions),
        "surprise_rate": len(surprise_resolutions) / max(len(flagged), 1),
        "by_severity": by_severity,
        "hypothetical_trades": len(pnl_data),
        "avg_pnl_per_trade": round(avg_pnl, 4) if avg_pnl is not None else None,
        "total_hypothetical_pnl": round(sum(pnl_data), 4) if pnl_data else None,
    }

    logger.info(
        f"Calibration: {metrics['total_flagged']} flagged, "
        f"{metrics['total_surprises']} surprises "
        f"({metrics['surprise_rate']:.0%} rate)"
    )

    return metrics
