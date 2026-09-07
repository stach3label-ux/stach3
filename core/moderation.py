"""Vektra Open - optional AI spam screening for submissions.

Only active when one of SAMBANOVA_API_KEY / GROQ_API_KEY / OPENAI_API_KEY is
set in the environment. It asks a chat-completions model to judge whether a
demo submission looks like spam. Submissions are never hard-blocked; a flagged
submission is simply marked on the staff card for human review.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request

from core.config import ai_spam_provider

logger = logging.getLogger("vektra-open.moderation")

SYSTEM_PROMPT = (
    "You screen music-demo submission forms for a record label. "
    "A submission is spam if it is gibberish, off-topic advertising, an empty "
    "or fake demo link, repeated identical junk, or clearly not a real artist "
    "submitting music. Answer only with JSON: "
    '{"is_spam": true or false, "reason": "short one-line explanation"}'
)


def _screen_with(provider: dict, text: str) -> dict:
    payload = {
        "model": provider["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": 120,
    }
    request = urllib.request.Request(
        provider["api_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return {"flagged": False, "reason": None}
    parsed = json.loads(match.group(0))
    return {
        "flagged": bool(parsed.get("is_spam")),
        "reason": (parsed.get("reason") or "")[:200],
    }


def screen_submission(*, real_name: str, track_name: str, artist_names: str, demo_link: str, message: str) -> dict:
    """Return {'flagged': bool, 'reason': str|None}. Never raises on failure."""
    provider = ai_spam_provider()
    if not provider:
        return {"flagged": False, "reason": None}
    text = "\n".join(
        [
            f"Name: {real_name or '-'}",
            f"Track: {track_name or '-'}",
            f"Artists: {artist_names or '-'}",
            f"Demo link: {demo_link or '-'}",
            f"Message: {message or '-'}",
        ]
    )
    try:
        return _screen_with(provider, text)
    except Exception as exc:
        logger.warning("AI spam screening failed (%s); treating as not spam.", exc)
        return {"flagged": False, "reason": None}
