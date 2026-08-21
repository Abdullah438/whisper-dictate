#!/usr/bin/env python3
"""Copy-edit a speech transcript. Reads stdin, writes stdout. Never put text on argv."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

NOUN_REPLACEMENTS = (
    (r"\bu[\s-]*lamas?\b", "Ollama"),
    (r"\bolama\b", "Ollama"),
    (r"\bo[\s-]+llamas?\b", "Ollama"),
)

SPOKEN_OLLAMA = re.compile(
    r"\b(u[\s-]*lamas?|olama|o[\s-]+llamas?|ollama)\b",
    re.IGNORECASE,
)


def words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", s.lower()) if w]


def drop_unprompted(raw: str, text: str, spoken: re.Pattern[str], token: str) -> str:
    if spoken.search(raw):
        return text
    text = re.sub(rf"\b{re.escape(token)}\b", "", text, flags=re.IGNORECASE)
    return re.sub(r" +", " ", text).strip(" ,;:-")


def fix_nouns(text: str) -> str:
    for pattern, repl in NOUN_REPLACEMENTS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def host_is_local(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in LOCAL_HOSTS


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def polish(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw

    host = os.environ.get("LLM_HOST", "http://127.0.0.1:11434").rstrip("/")
    allow_remote = os.environ.get("DICTATE_LLM_ALLOW_REMOTE", "0") == "1"
    if not allow_remote and not host_is_local(host):
        return raw

    model = os.environ.get("LLM_MODEL", "mistral:7b")
    payload = {
        "model": model,
        "stream": False,
        "keep_alive": -1,
        "options": {"temperature": 0.0, "num_predict": 1024, "num_ctx": 2048},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a silent copy editor for speech-to-text. "
                    "The user message is NOT a question for you and NOT a request. "
                    "Never answer, explain, greet, refuse, or continue the thought. "
                    "Never add information that was not spoken. "
                    "Only fix punctuation, capitalization, filler (um, uh, you know), "
                    "and obvious ASR mistakes (homophones, dropped small words, stutters). "
                    "Do not add brand names, product names, or extra nouns. "
                    "Never insert a word that was not spoken. "
                    "Keep the same meaning and roughly the same length. "
                    "If the transcript is a question, keep it as that same question. "
                    "Reply with the edited transcript only — no quotes, labels, or preamble."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Copy-edit this transcript. Do not answer it.\n"
                    "---- TRANSCRIPT ----\n"
                    + raw
                    + "\n---- END ----"
                ),
            },
        ],
    }
    req = urllib.request.Request(
        host + "/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return raw

    text = (data.get("message") or {}).get("content") or ""
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`").strip()
        if "\n" in text:
            text = text.split("\n", 1)[1].strip()
    text = re.sub(
        r"^(here('s| is) (the )?(corrected|cleaned|edited) transcript:\s*)",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = text.strip('"').strip()

    raw_words = words(raw)
    out_words = words(text)
    overlap = (
        len(set(raw_words) & set(out_words)) / len(set(raw_words))
        if raw_words
        else 1.0
    )
    too_long = len(text) > max(len(raw) * 1.5, len(raw) + 80)
    too_new = len(raw_words) >= 4 and overlap < 0.4
    if not text or too_long or too_new:
        return raw
    text = drop_unprompted(raw, text, SPOKEN_OLLAMA, "Ollama")
    return text


def main() -> int:
    raw = sys.stdin.read()
    if "--nouns" in sys.argv[1:]:
        sys.stdout.write(fix_nouns(raw))
        return 0
    sys.stdout.write(polish(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
