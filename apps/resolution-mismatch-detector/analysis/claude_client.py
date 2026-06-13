"""Claude Code CLI wrapper — routes analysis through `claude -p` instead of the API.

Uses your Max subscription, so no per-call API cost.
"""

import json
import logging
import subprocess
import time
from datetime import datetime, timezone

from analysis.prompts import SYSTEM_PROMPT, PROMPT_VERSION

logger = logging.getLogger(__name__)


class ClaudeClient:
    def __init__(self, model: str = None):
        self.model = model or "sonnet"
        self.call_count = 0
        self.total_calls_today = 0
        self.daily_reset_date = datetime.now(timezone.utc).date().isoformat()

    def _reset_daily_if_needed(self):
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.daily_reset_date:
            self.total_calls_today = 0
            self.daily_reset_date = today

    def analyze(self, user_prompt: str, max_retries: int = 3) -> dict:
        """
        Send analysis prompt to Claude Code CLI via `claude -p`.
        Returns parsed JSON response.
        """
        self._reset_daily_if_needed()

        # Combine system prompt + user prompt
        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

        last_error = None
        raw_text = ""

        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    ["claude", "-p", "--model", self.model],
                    input=full_prompt,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    logger.warning(f"claude CLI error (attempt {attempt + 1}): {stderr}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                    last_error = RuntimeError(stderr)
                    continue

                raw_text = result.stdout.strip()

                # Empty response — retry without counting as a real call
                if not raw_text:
                    logger.debug(f"Empty response (attempt {attempt + 1}), retrying...")
                    time.sleep(1)
                    continue

                self.call_count += 1
                self.total_calls_today += 1

                # Try direct JSON parse first
                try:
                    parsed = json.loads(raw_text)
                except json.JSONDecodeError:
                    # Try extracting JSON from markdown or wrapped text
                    extracted = self._extract_json(raw_text)
                    if extracted:
                        parsed = extracted
                        logger.debug("Extracted JSON from wrapped response")
                    else:
                        logger.warning(
                            f"JSON parse failed (attempt {attempt + 1}). "
                            f"Response starts with: {raw_text[:200]}"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(1)
                        last_error = ValueError(f"Not JSON: {raw_text[:100]}")
                        continue

                parsed["_meta"] = {
                    "prompt_version": PROMPT_VERSION,
                    "model": self.model,
                    "backend": "claude-code-cli",
                    "raw_response": raw_text,
                }
                return parsed

            except subprocess.TimeoutExpired:
                logger.warning(f"claude CLI timed out (attempt {attempt + 1})")
                last_error = TimeoutError("CLI timed out after 120s")
                if attempt < max_retries - 1:
                    time.sleep(2)

            except FileNotFoundError:
                raise RuntimeError(
                    "claude CLI not found. Make sure Claude Code is installed "
                    "and `claude` is on your PATH."
                )

        raise RuntimeError(f"Claude CLI failed after {max_retries} attempts: {last_error}")

    def _extract_json(self, text: str) -> dict | None:
        """Try to extract JSON from a response that has extra text around it."""
        # Strip markdown code fences
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

        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return None

    def get_spend_summary(self) -> dict:
        """Return call tracking info."""
        return {
            "daily_spend_usd": 0.0,
            "daily_limit_usd": float("inf"),
            "remaining_usd": float("inf"),
            "total_calls": self.call_count,
            "total_calls_today": self.total_calls_today,
            "backend": "claude-code-cli (Max plan)",
        }
