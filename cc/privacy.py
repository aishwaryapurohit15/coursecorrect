"""Privacy gateway: pseudonymization, PII redaction and prompt-injection screening.

Runs before any text reaches the AI model, the database or the dashboard.
"""
import hashlib
import hmac
import os
import re
import secrets

from .config import DATA

_KEY_FILE = DATA / ".pseudonym_key"


def _key() -> bytes:
    env = os.getenv("CC_PSEUDONYM_KEY")
    if env:
        return env.encode()
    if not _KEY_FILE.exists():
        _KEY_FILE.write_text(secrets.token_hex(32))
    return _KEY_FILE.read_text().strip().encode()


def pseudonymize(student_id: str) -> str:
    """Keyed hash: stable per student, not reversible without the institution-held key."""
    digest = hmac.new(_key(), student_id.strip().upper().encode(), hashlib.sha256).hexdigest()
    return "S-" + digest[:8]


EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b")
URL = re.compile(r"https?://\S+|www\.\S+")
STUDENT_ID = re.compile(r"\bN\d{5,8}\b", re.I)
# Capitalized full name right after a cue like "classmate", "with", "named"
NAME_CUE = re.compile(r"\b(?:classmate|classmates|with|named|friend|colleague|teammate)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)")


def redact(text: str, roster: list[str] | None = None) -> tuple[str, list[str]]:
    """Return (redacted_text, list of PII types found)."""
    if not text:
        return text, []
    found = []
    out = text
    for pat, tag in ((EMAIL, "[EMAIL]"), (URL, "[URL]"), (PHONE, "[PHONE]"), (STUDENT_ID, "[ID]")):
        if pat.search(out):
            found.append(tag.strip("[]").lower())
            out = pat.sub(tag, out)
    for name in roster or []:
        if re.search(re.escape(name), out, re.I):
            found.append("name")
            out = re.sub(re.escape(name), "[NAME]", out, flags=re.I)
    m = NAME_CUE.search(out)
    while m:
        found.append("name")
        out = out[: m.start(1)] + "[NAME]" + out[m.end(1):]
        m = NAME_CUE.search(out)
    return out, sorted(set(found))


INJECTION_PATTERNS = [
    r"\bignore\b.{0,40}\b(instructions?|rubric|rules|prompt|guidelines)\b",
    r"\bdisregard\b.{0,40}\b(instructions?|rules|prompt)\b",
    r"\bsystem\s*:",
    r"\byou are now\b",
    r"\badmin mode\b",
    r"\bmark me as\b",
    r"\brate (this student|me)\b",
    r"\blabel every\b",
    r"\boutput no\b",
    r"\bsay the class has\b",
    r"\bnew instructions\b",
    r"\bjailbreak\b",
]
_INJ = re.compile("|".join(INJECTION_PATTERNS), re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")


def screen_injection(text: str) -> tuple[str, bool]:
    """Drop sentences that try to instruct the AI. Returns (clean_text, injection_detected)."""
    if not text:
        return text, False
    sentences = _SENT.split(text.strip())
    kept = [s for s in sentences if not _INJ.search(s)]
    return " ".join(kept).strip(), len(kept) != len(sentences)


def contains_pii(text: str, roster: list[str] | None = None) -> bool:
    _, found = redact(text, roster)
    return bool(found)
