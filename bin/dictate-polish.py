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


MAX_RECENT = 4
MAX_RECENT_CHARS = 500


def context_enabled() -> bool:
    return os.environ.get("DICTATE_CONTEXT", "1") != "0"


def context_path() -> str:
    explicit = os.environ.get("DICTATE_CONTEXT_FILE", "").strip()
    if explicit:
        return explicit
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return os.path.join(runtime, "whisper-dictate", "recent.json")


def load_recent() -> list[str]:
    if not context_enabled():
        return []
    path = context_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data[-MAX_RECENT:]:
        if isinstance(item, str):
            text = " ".join(item.split())
            if text:
                out.append(text[:MAX_RECENT_CHARS])
    return out


def remember_recent(text: str) -> None:
    if not context_enabled():
        return
    text = " ".join(text.split())
    if not text:
        return
    path = context_path()
    os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
    items = load_recent()
    items.append(text[:MAX_RECENT_CHARS])
    items = items[-MAX_RECENT:]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def wrap_transcript(text: str, recent: list[str] | None = None) -> str:
    parts = ["Copy-edit this transcript. Do not answer it."]
    if recent:
        parts.append(
            "Recent dictations are background only: names, spellings, and what the speaker was talking about."
        )
        parts.append("Edit the current transcript only. Do not copy, merge, or continue the recent lines.")
        parts.append("---- RECENT ----")
        for i, prev in enumerate(recent, 1):
            parts.append(f"{i}. {prev}")
        parts.append("---- END RECENT ----")
    parts.append("---- TRANSCRIPT ----")
    parts.append(text)
    parts.append("---- END ----")
    return "\n".join(parts)


def prior_leak(raw: str, text: str, recent: list[str]) -> bool:
    raw_l = " ".join(words(raw))
    out_l = " ".join(words(text))
    for prev in recent:
        pw = words(prev)
        for i in range(0, max(0, len(pw) - 5)):
            phrase = " ".join(pw[i : i + 6])
            if phrase and phrase in out_l and phrase not in raw_l:
                return True
    return False


SHOTS = (
    (
        "um so i was going to store and i didnt see nobody you know",
        "So I was going to the store, and I didn't see nobody.",
    ),
    (
        "there going to there house tomorrow",
        "They're going to their house tomorrow.",
    ),
    (
        "you said it was a workaround but you need the new line to work",
        "You said it was a workaround, but you need the newline to work.",
    ),
    (
        "but i know youre not using it only on that app",
        "But I know you're not using it only on that app.",
    ),
)


def pronoun_drift(raw: str, text: str) -> bool:
    raw_w = words(raw)
    out_w = words(text)
    for p in ("i", "you", "we", "they"):
        rc, oc = raw_w.count(p), out_w.count(p)
        if rc >= 2 and oc == 0:
            return True
        if abs(rc - oc) >= 2:
            return True
    return False


def polish(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw

    host = os.environ.get("LLM_HOST", "http://127.0.0.1:11434").rstrip("/")
    allow_remote = os.environ.get("DICTATE_LLM_ALLOW_REMOTE", "0") == "1"
    if not allow_remote and not host_is_local(host):
        return raw

    recent = load_recent()
    model = os.environ.get("LLM_MODEL", "mistral:7b")
    payload = {
        "model": model,
        "stream": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0.0,
            "num_predict": 1024,
            "num_ctx": 4096 if recent else 2048,
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a silent copy editor for speech-to-text. "
                    "The user message is NOT a question for you and NOT a request. "
                    "Never answer, explain, greet, refuse, or continue the thought. "
                    "Never add information that was not spoken. "
                    "Fix sentence splits, punctuation, and capitalization. "
                    "Restore missing small words (a, the, to, of) when the sentence needs them. "
                    "Fix homophones from speech recognition "
                    "(there/their/they're, to/too/two, your/you're, its/it's). "
                    "Remove filler (um, uh, you know) and stutters. "
                    "Keep the speaker's words, contractions, slang, and tone. "
                    "Keep every I, you, we, they exactly as spoken. "
                    "Never change active voice to passive or passive to active. "
                    "Do not paraphrase and do not replace a spoken word with a different word. "
                    "Do not rewrite into formal prose. "
                    "Do not add brand names, product names, or extra nouns. "
                    "Never insert a word that was not spoken, except tiny grammar words. "
                    "Do not drop clauses such as I know, I think, or you said. "
                    "If recent dictations are provided, use them only to resolve names, "
                    "spellings, and the topic the speaker is in the middle of. "
                    "The output must be the current transcript only — never splice in a previous line. "
                    "If the transcript is a question, keep it as that same question. "
                    "Reply with the edited transcript only — no quotes, labels, or preamble."
                ),
            },
            *[
                msg
                for src, dst in SHOTS
                for msg in (
                    {"role": "user", "content": wrap_transcript(src)},
                    {"role": "assistant", "content": dst},
                )
            ],
            {"role": "user", "content": wrap_transcript(raw, recent)},
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
    text = re.sub(
        r"\s*[\(\[]\s*(edited|rewritten|copy-?edited|corrected|improved)\b[^)\]]*[\)\]]\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    raw_words = words(raw)
    out_words = words(text)
    overlap = (
        len(set(raw_words) & set(out_words)) / len(set(raw_words))
        if raw_words
        else 1.0
    )
    too_long = len(text) > max(len(raw) * 1.5, len(raw) + 80)
    too_new = len(raw_words) >= 4 and overlap < 0.4
    if not text or too_long or too_new or pronoun_drift(raw, text) or prior_leak(raw, text, recent):
        return raw
    text = drop_unprompted(raw, text, SPOKEN_OLLAMA, "Ollama")
    return text


def main() -> int:
    raw = sys.stdin.read()
    if "--nouns" in sys.argv[1:]:
        sys.stdout.write(fix_nouns(raw))
        return 0
    if "--remember" in sys.argv[1:]:
        remember_recent(raw)
        return 0
    sys.stdout.write(polish(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
