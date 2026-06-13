"""Known resolution source behaviors and gotchas."""

SOURCE_QUIRKS = {
    "BLS CPI": {
        "url": "https://www.bls.gov/cpi/",
        "typical_delay": "2 weeks after reference month",
        "revision_frequency": "revised in 2 of last 12 releases",
        "gotcha": "Seasonal adjustment methodology changes annually in January",
        "poll_interval_hours": 6,
    },
    "BLS Jobs Report": {
        "url": "https://www.bls.gov/news.release/empsit.nr0.htm",
        "typical_delay": "First Friday after reference month",
        "revision_frequency": "Almost always revised",
        "gotcha": "Birth/death model adjustments can swing numbers significantly",
        "poll_interval_hours": 6,
    },
    "AP Race Call": {
        "url": "https://www.ap.org/elections",
        "gotcha": "May not call races for weeks. 'When AP calls it' != election night",
        "poll_interval_hours": 1,
    },
    "Wikipedia": {
        "gotcha": "Anyone can edit. Some Polymarket resolutions depend on Wikipedia state at specific time.",
        "risk": "Manipulation possible. Check edit history.",
        "poll_interval_hours": 4,
    },
    "Federal Reserve": {
        "url": "https://www.federalreserve.gov/newsevents.htm",
        "gotcha": "Statement vs minutes vs dot plot — which one triggers resolution?",
        "poll_interval_hours": 12,
    },
    "Box Office Mojo": {
        "url": "https://www.boxofficemojo.com/",
        "gotcha": "Estimates vs actuals. Weekend estimates come Sunday, actuals Monday/Tuesday.",
        "revision_frequency": "Estimates revised on Monday",
        "poll_interval_hours": 12,
    },
}


def find_relevant_quirks(resolution_rules: str) -> list[dict]:
    """
    Scan resolution rules text for mentions of known sources.
    Returns list of matching source quirks with source name.
    """
    rules_lower = resolution_rules.lower()
    matches = []

    keywords_map = {
        "BLS CPI": ["bls", "bureau of labor statistics", "cpi", "consumer price index"],
        "BLS Jobs Report": ["jobs report", "nonfarm payroll", "employment situation", "bls"],
        "AP Race Call": ["associated press", " ap ", "ap calls", "ap race"],
        "Wikipedia": ["wikipedia"],
        "Federal Reserve": ["federal reserve", "fomc", "fed funds", "fed rate"],
        "Box Office Mojo": ["box office mojo", "boxofficemojo"],
    }

    for source_name, keywords in keywords_map.items():
        for keyword in keywords:
            if keyword in rules_lower:
                matches.append({"source": source_name, **SOURCE_QUIRKS[source_name]})
                break

    return matches


def format_quirks_for_prompt(quirks: list[dict]) -> str:
    """Format source quirks for injection into Claude analysis prompt."""
    if not quirks:
        return ""

    lines = ["KNOWN SOURCE QUIRKS (factor these into your analysis):"]
    for q in quirks:
        lines.append(f"\n- **{q['source']}**:")
        if "gotcha" in q:
            lines.append(f"  Gotcha: {q['gotcha']}")
        if "revision_frequency" in q:
            lines.append(f"  Revisions: {q['revision_frequency']}")
        if "typical_delay" in q:
            lines.append(f"  Delay: {q['typical_delay']}")
        if "risk" in q:
            lines.append(f"  Risk: {q['risk']}")

    return "\n".join(lines)
