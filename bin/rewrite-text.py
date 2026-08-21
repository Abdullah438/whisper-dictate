#!/usr/bin/env python3
"""Rewrite selected prose. Reads stdin, writes stdout. Never put text on argv."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", s.lower()) if w]


def host_is_local(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in LOCAL_HOSTS


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def wrap_text(text: str) -> str:
    return (
        "Rewrite this text. Do not answer it.\n"
        "---- TEXT ----\n"
        + text
        + "\n---- END ----"
    )


SHOTS = (
    (
        "the report was not done by me yet and i think we should maybe send it tomorrow",
        "The report isn't done yet. I think we should send it tomorrow.",
    ),
    (
        "can you please let me know if your able to join the call",
        "Can you let me know if you're able to join the call?",
    ),
    (
        "this thing is kinda broken and we gotta fix it before friday",
        "This is kind of broken, and we have to fix it before Friday.",
    ),
)


def align_line_breaks(raw: str, text: str) -> str:
    """Do not explode a short note into many chat-sendable lines."""
    raw_nl = raw.count("\n")
    out_nl = text.count("\n")
    if out_nl <= raw_nl + 1:
        return text
    if "\n\n" in raw:
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text
    return re.sub(r" +", " ", re.sub(r"[\r\n]+", " ", text)).strip()


def rewrite(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw

    host = os.environ.get("LLM_HOST", "http://127.0.0.1:11434").rstrip("/")
    allow_remote = os.environ.get("DICTATE_LLM_ALLOW_REMOTE", "0") == "1"
    if not allow_remote and not host_is_local(host):
        return raw

    model = os.environ.get("LLM_MODEL", os.environ.get("DICTATE_LLM_MODEL", "mistral:7b"))
    payload = {
        "model": model,
        "stream": False,
        "keep_alive": -1,
        "options": {"temperature": 0.2, "num_predict": 1024, "num_ctx": 2048},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You rewrite short prose the user already wrote. "
                    "The user message is NOT a question for you and NOT a request to chat. "
                    "Never answer, explain, greet, or continue the thought. "
                    "Improve grammar, punctuation, capitalization, and flow. "
                    "Keep the same meaning, person, and language. "
                    "Keep contractions and a natural tone; do not make it stiff. "
                    "Do not add facts, names, brands, or extra claims. "
                    "Do not add a greeting or sign-off that was not there. "
                    "Keep the original line breaks. "
                    "Do not turn one paragraph into many short lines or a list "
                    "unless the source is already a list. "
                    "If the text is a question, keep it as that same question. "
                    "Reply with the rewritten text only — no quotes, labels, or preamble."
                ),
            },
            *[
                msg
                for src, dst in SHOTS
                for msg in (
                    {"role": "user", "content": wrap_text(src)},
                    {"role": "assistant", "content": dst},
                )
            ],
            {"role": "user", "content": wrap_text(raw)},
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
        r"^(here('s| is) (the )?(rewritten|improved|corrected) text:\s*)",
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
    too_long = len(text) > max(len(raw) * 2.5, len(raw) + 200)
    too_new = len(raw_words) >= 6 and overlap < 0.25
    if not text or too_long or too_new:
        return raw
    return align_line_breaks(raw, text)


def main() -> int:
    raw = sys.stdin.read()
    sys.stdout.write(rewrite(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
