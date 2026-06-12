"""
Prompt templates for polling synthetic population personas.

Assembles structured prompts that keep simulated persons grounded
in their backstory, media diet, and prior opinions — not in
what a policy analyst would say.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# News source display names
# ---------------------------------------------------------------------------

_NEWS_SOURCE_LABELS: dict[str, str] = {
    "fox_news": "Fox News",
    "msnbc": "MSNBC",
    "cnn": "CNN",
    "nbc_news": "NBC News",
    "abc_news": "ABC News",
    "cbs_news": "CBS News",
    "npr": "NPR",
    "bbc": "BBC",
    "local_tv": "local TV news",
    "local_newspaper": "a local newspaper",
    "newsmax": "Newsmax",
    "oann": "OAN",
    "breitbart": "Breitbart",
    "new_york_times": "the New York Times",
    "washington_post": "the Washington Post",
    "the_hill": "The Hill",
    "politico": "Politico",
    "none": "no regular news source",
}

_SOCIAL_MEDIA_LABELS: dict[str, str] = {
    "facebook": "Facebook",
    "twitter": "Twitter/X",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "reddit": "Reddit",
    "truth_social": "Truth Social",
    "none": "no social media",
}


def _format_news_source(raw: str) -> str:
    key = raw.strip().lower()
    return _NEWS_SOURCE_LABELS.get(key, raw)


def _format_social_media(raw: str) -> str:
    key = raw.strip().lower()
    return _SOCIAL_MEDIA_LABELS.get(key, raw)


# ---------------------------------------------------------------------------
# Conviction anchoring block — never changes
# ---------------------------------------------------------------------------

_CONVICTION_ANCHORING = """\
IMPORTANT — You are NOT a policy analyst or debate moderator. You have real \
opinions shaped by your life, your community, and what you've been exposed to. \
Express your views the way this specific person actually would:
- If you'd have a strong opinion, express it strongly. Don't hedge.
- If you wouldn't know or care about this topic, say so bluntly.
- If you'd be misinformed or only partly informed, reflect that — do NOT \
correct yourself with facts you wouldn't have.
- Your media diet shapes what arguments and framings you've even heard.
- Do NOT add caveats or qualifiers unless this person genuinely would use them.\
"""


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_poll_prompt(
    profile: dict[str, Any],
    question: str,
    include_history: bool = True,
) -> str:
    """
    Build a full prompt string for polling a synthetic persona.

    Parameters
    ----------
    profile:
        Dict with at minimum a ``backstory`` key. Optional keys:
        ``primary_news_source``, ``social_media_primary``, ``drift_log``.
    question:
        The poll question to ask.
    include_history:
        If True (default), include relevant prior opinions from ``drift_log``.

    Returns
    -------
    str
        A complete prompt ready to send to an LLM.
    """
    parts: list[str] = []

    # 1. System instruction
    parts.append(
        "You are roleplaying as a specific person. Stay fully in character "
        "throughout your response. Do not break character to add disclaimers "
        "or explain your reasoning meta-cognitively."
    )

    # 2. Conviction anchoring
    parts.append(_CONVICTION_ANCHORING)

    # 3. Backstory
    backstory = profile.get("backstory", "").strip()
    if backstory:
        parts.append(f"YOUR BACKGROUND:\n{backstory}")

    # 4. Media diet
    media_lines: list[str] = []
    news_raw = profile.get("primary_news_source", "")
    if news_raw and isinstance(news_raw, str):
        media_lines.append(f"- Primary news source: {_format_news_source(news_raw)}")
    social_raw = profile.get("social_media_primary", "")
    if social_raw and isinstance(social_raw, str):
        media_lines.append(f"- Primary social media: {_format_social_media(social_raw)}")
    if media_lines:
        parts.append("YOUR MEDIA DIET:\n" + "\n".join(media_lines))

    # 5. Prior opinions from drift_log (filtered to topic relevance)
    if include_history:
        drift_log: list[dict[str, Any]] = profile.get("drift_log", [])
        if drift_log:
            question_lower = question.lower()
            relevant = [
                entry for entry in drift_log
                if entry.get("topic", "").lower() in question_lower
                or question_lower in entry.get("topic", "").lower()
            ]
            if relevant:
                opinion_lines = []
                for entry in relevant:
                    topic = entry.get("topic", "unknown")
                    position = entry.get("position", "unknown")
                    confidence = entry.get("confidence", "?")
                    opinion_lines.append(
                        f"- On {topic}: {position} (confidence {confidence}/10)"
                    )
                parts.append(
                    "YOUR PRIOR OPINIONS (on related topics):\n"
                    + "\n".join(opinion_lines)
                )

    # 6. The question
    parts.append(f"QUESTION:\n{question}")

    # 7. Response format
    parts.append(
        "RESPOND IN THIS FORMAT:\n"
        "Opinion: [yes / no / unsure]\n"
        "Confidence: [1-10]\n"
        "Reasoning: [2-3 sentences, in your own voice as this person]"
    )

    return "\n\n".join(parts)
