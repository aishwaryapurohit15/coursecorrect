"""Pseudonymized SQLite signal store.

Only redacted text is stored (never raw text). For support cases only the label is
kept; there is no separate copy of the text and no at-risk list. A student's real ID
is stored only when they ticked "I'd like follow-up".
"""
import json
import sqlite3
from datetime import datetime, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS reflections (
  id TEXT PRIMARY KEY, pseudonym TEXT, week INTEGER, source TEXT,
  explain TEXT, unclear TEXT, apply TEXT, optional_prompt TEXT, optional TEXT,
  follow_up INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS results (
  reflection_id TEXT PRIMARY KEY, backend TEXT, concepts TEXT, findings TEXT,
  low_effort INTEGER, injection INTEGER, pii_types TEXT, support INTEGER,
  routes TEXT, needs_review INTEGER, review_reason TEXT, reviewed INTEGER DEFAULT 0, created_at TEXT
);
CREATE TABLE IF NOT EXISTS followups (
  id INTEGER PRIMARY KEY AUTOINCREMENT, reflection_id TEXT, week INTEGER, student_id TEXT,
  topic_hint TEXT, created_at TEXT, resolved INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, week INTEGER, concept TEXT, verdict TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS student_flags (
  id INTEGER PRIMARY KEY AUTOINCREMENT, reflection_id TEXT, note TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
-- AI tutor usage: which course concept a question was about. No question text, no student ID.
CREATE TABLE IF NOT EXISTS tutor_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, week INTEGER, concept TEXT, kind TEXT, created_at TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None) -> sqlite3.Connection:
    con = sqlite3.connect(str(path or DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def audit(con, actor, action, detail=""):
    con.execute("INSERT INTO audit(ts, actor, action, detail) VALUES (?,?,?,?)", (now(), actor, action, detail))
    con.commit()


def save(con, refl: dict, result: dict):
    support = int(result["support"])
    # Support cases keep the label only: the free text is not stored.
    keep = (lambda s: "") if support else (lambda s: s)
    con.execute(
        "INSERT OR REPLACE INTO reflections VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (refl["id"], result["pseudonym"], refl["week"], refl.get("source", "form"),
         keep(result["fields"].get("explain", "")), keep(result["fields"].get("unclear", "")),
         keep(result["fields"].get("apply", "")), refl.get("optional_prompt"),
         keep(result["fields"].get("optional", "")), int(bool(refl.get("follow_up"))), now()),
    )
    findings = result["findings"]
    if support:
        findings = [{**f, "evidence": "", "paraphrase": ""} for f in findings]
    con.execute(
        "INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (refl["id"], result["backend"], json.dumps(result["concepts"]), json.dumps(findings),
         int(result["low_effort"]), int(result["injection"]), json.dumps(result["pii_types"]), support,
         json.dumps(result["routes"]), int(result["needs_review"]), result["review_reason"], 0, now()),
    )
    if refl.get("follow_up"):
        hint = ", ".join(result["concepts"][:3])
        con.execute("INSERT INTO followups(reflection_id, week, student_id, topic_hint, created_at) VALUES (?,?,?,?,?)",
                    (refl["id"], refl["week"], refl["student_id"], hint, now()))
    con.commit()


def load_results(con) -> list[dict]:
    rows = con.execute(
        "SELECT r.id, r.week, r.pseudonym, r.explain, r.unclear, r.apply, r.optional, r.follow_up, "
        "s.backend, s.concepts, s.findings, s.low_effort, s.injection, s.pii_types, s.support, s.routes, "
        "s.needs_review, s.review_reason, s.reviewed "
        "FROM reflections r JOIN results s ON s.reflection_id = r.id ORDER BY r.week, r.id"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("concepts", "findings", "pii_types", "routes"):
            d[k] = json.loads(d[k])
        out.append(d)
    return out


def update_findings(con, reflection_id, findings, concepts, actor="faculty"):
    con.execute("UPDATE results SET findings=?, concepts=?, needs_review=0, reviewed=1 WHERE reflection_id=?",
                (json.dumps(findings), json.dumps(concepts), reflection_id))
    con.commit()
    audit(con, actor, "review", reflection_id)


def get_setting(con, key, default=None):
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(con, key, value):
    con.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))
    con.commit()


def log_tutor(con, week: int, concept: str | None, kind: str):
    """Record that the tutor answered a question about `concept`. Support conversations are never logged."""
    if kind == "support":
        return
    con.execute("INSERT INTO tutor_log(week, concept, kind, created_at) VALUES (?,?,?,?)", (week, concept or "none", kind, now()))
    con.commit()


def tutor_topic_counts(con, week: int) -> list[dict]:
    rows = con.execute("SELECT concept, COUNT(*) n FROM tutor_log WHERE week=? AND kind='answer' AND concept!='none' "
                       "GROUP BY concept ORDER BY n DESC", (week,)).fetchall()
    return [dict(r) for r in rows]


def purge_raw_text(con):
    """End-of-term retention: delete reflection text, keep only de-identified labels."""
    con.execute("UPDATE reflections SET explain='', unclear='', apply='', optional=''")
    con.execute("DELETE FROM followups")
    con.execute("DELETE FROM student_flags")
    con.commit()
    audit(con, "admin", "purge_raw_text", "end-of-term retention")


def reset(con):
    for t in ("reflections", "results", "followups", "feedback", "student_flags"):
        con.execute(f"DELETE FROM {t}")
    con.commit()
    audit(con, "admin", "reset", "all reflections cleared")
