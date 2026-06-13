"""Daily markdown report generator."""

import logging
from datetime import datetime
from pathlib import Path

from config import REPORTS_DIR

logger = logging.getLogger(__name__)


def _fmt_price(val):
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.0%}"
    except (ValueError, TypeError):
        return "N/A"


def _fmt_vol(val):
    if val is None:
        return "$0"
    try:
        return f"${float(val):,.0f}"
    except (ValueError, TypeError):
        return "$0"


def generate_daily_report(db, output_dir: Path = None) -> str:
    """
    Generate a daily markdown report from the latest analysis data.
    Returns the file path of the generated report.
    """
    output_dir = output_dir or REPORTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = output_dir / f"report_{today}.md"

    # Gather data
    high_analyses = db.get_analyses(severity="high")
    medium_analyses = db.get_analyses(severity="medium")
    cross_matches = db.get_cross_matches(min_confidence=0.65)
    watchlist = db.get_watchlist()
    positions = db.get_all_positions()

    lines = [
        f"# Mismatch Report — {today}",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
    ]

    # Summary
    lines.append("## Summary")
    lines.append(f"- **High severity:** {len(high_analyses)}")
    lines.append(f"- **Medium severity:** {len(medium_analyses)}")
    lines.append(f"- **Cross-platform matches:** {len(cross_matches)}")
    lines.append(f"- **Watched markets:** {len(watchlist)}")
    lines.append(f"- **Active positions:** {len(positions)}")
    lines.append("")

    # High severity mismatches
    if high_analyses:
        lines.append("## High Severity Mismatches")
        lines.append("")
        for a in high_analyses:
            market = db.get_market(a["market_id"])
            if not market:
                continue
            position = db.get_position(a["market_id"])
            pos_tag = " **[POSITION HELD]**" if position else ""
            lines.extend([
                f"### {market['title']}{pos_tag}",
                f"- **Platform:** {market['platform']}",
                f"- **Price:** {_fmt_price(market.get('current_yes_price'))}",
                f"- **Volume:** {_fmt_vol(market.get('volume'))}",
                f"- **Priority Score:** {a.get('priority_score', 0):.2f}",
                f"- **Retail assumes:** {a.get('retail_assumption', 'N/A')}",
                f"- **Rules say:** {a.get('actual_resolution', 'N/A')}",
                f"- **Categories:** {a.get('mismatch_categories', 'N/A')}",
                "",
            ])

    # Medium severity
    if medium_analyses:
        lines.append("## Medium Severity Mismatches")
        lines.append("")
        for a in medium_analyses:
            market = db.get_market(a["market_id"])
            if not market:
                continue
            lines.append(
                f"- **{market['title']}** ({market['platform']}) — "
                f"Price: {_fmt_price(market.get('current_yes_price'))}, "
                f"Priority: {a.get('priority_score', 0):.2f}"
            )
        lines.append("")

    # Cross-platform matches
    if cross_matches:
        lines.append("## Cross-Platform Matches")
        lines.append("")
        for m in cross_matches:
            arb_tag = " **[ARB SIGNAL]**" if m.get("arb_signal") else ""
            conf = _fmt_price(m.get("match_confidence"))
            lines.append(
                f"- Poly `{m['polymarket_id']}` <-> Kalshi `{m['kalshi_id']}`"
                f" (confidence: {conf}){arb_tag}"
            )
        lines.append("")

    # Position alerts
    position_markets = [p for p in positions if db.get_latest_analysis(p["market_id"])]
    if position_markets:
        lines.append("## Position Alerts")
        lines.append("")
        for p in position_markets:
            analysis = db.get_latest_analysis(p["market_id"])
            if analysis and analysis.get("mismatch_found"):
                lines.append(
                    f"- **{p['market_id']}**: {p['side']} @ {p['avg_price']} x {p['quantity']} "
                    f"— mismatch severity: {analysis.get('severity', 'unknown')}"
                )
        lines.append("")

    report_text = "\n".join(lines)
    filepath.write_text(report_text, encoding="utf-8")
    logger.info(f"Report written to {filepath}")
    return str(filepath)
