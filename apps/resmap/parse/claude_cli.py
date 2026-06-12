"""
`claude -p` subprocess wrapper — LLM calls via the Claude Code CLI (Max plan,
no per-call API cost). Ported from the proven resolution-mismatch-detector
client; function-first, no class.

    from parse.claude_cli import call_claude_json
    parsed = call_claude_json(prompt)   # dict, or raises ClaudeCliError
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("CLAUDE_CLI_MODEL", "sonnet")

_claude_bin: Optional[str] = None


class ClaudeCliError(RuntimeError):
    """The CLI failed after all retries (or isn't installed)."""


def _resolve_bin() -> str:
    """Resolve the claude binary once. Bare "claude" may not resolve from a
    Windows subprocess outside git-bash — shutil.which handles PATHEXT."""
    global _claude_bin
    if _claude_bin is None:
        found = shutil.which("claude")
        if not found:
            raise ClaudeCliError(
                "claude CLI not found on PATH. Install Claude Code or add "
                "~/.local/bin to PATH.")
        _claude_bin = found
    return _claude_bin


def _child_env() -> dict:
    """Strip Claude-Code session vars so runs launched from inside a Claude
    Code session behave like standalone runs."""
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("CLAUDE", "ANTHROPIC"))}


def call_claude_json(prompt: str, model: str | None = None,
                     timeout: int = 120, max_retries: int = 3) -> dict:
    """Send `prompt` to `claude -p`, parse the stdout as JSON, return the dict.
    Retries on nonzero exit, empty stdout, and non-JSON output; raises
    ClaudeCliError when retries are exhausted."""
    bin_path = _resolve_bin()
    model = model or DEFAULT_MODEL
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                [bin_path, "-p", "--model", model],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                env=_child_env(),
            )
        except subprocess.TimeoutExpired:
            logger.warning("claude CLI timed out (attempt %d)", attempt + 1)
            last_error = TimeoutError(f"CLI timed out after {timeout}s")
            time.sleep(2)
            continue

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            logger.warning("claude CLI exit %d (attempt %d): %s",
                           result.returncode, attempt + 1, stderr[:300])
            last_error = RuntimeError(stderr[:300])
            time.sleep(2 ** attempt)
            continue

        raw_text = (result.stdout or "").strip()
        if not raw_text:
            logger.debug("empty response (attempt %d)", attempt + 1)
            last_error = ValueError("empty stdout")
            time.sleep(1)
            continue

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            extracted = _extract_json(raw_text)
            if extracted is not None:
                logger.debug("extracted JSON from wrapped response")
                return extracted
            logger.warning("JSON parse failed (attempt %d). starts: %s",
                           attempt + 1, raw_text[:200])
            last_error = ValueError(f"not JSON: {raw_text[:100]}")
            time.sleep(1)

    raise ClaudeCliError(f"claude CLI failed after {max_retries} attempts: {last_error}")


def _extract_json(text: str) -> dict | None:
    """Extract JSON from a response with extra text around it (markdown fences,
    CLI update notices, preamble). Ported verbatim — it earns its keep."""
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            try:
                return json.loads(text[start:end].strip())
            except json.JSONDecodeError:
                pass
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            try:
                return json.loads(text[start:end].strip())
            except json.JSONDecodeError:
                pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None
