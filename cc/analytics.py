"""Aggregation for the faculty dashboard: topic x week counts, small-group hiding,
SPC-style spike flags, recurring-issue flags and suggested topics to revisit."""
import math
from collections import defaultdict

import pandas as pd

from .config import ISSUE_SIGNALS, MIN_GROUP_SIZE
from .course_model import concept_by_id


def topic_week_table(results: list[dict]) -> pd.DataFrame:
    """One row per (week, concept): distinct reflections mentioning it and per-signal counts."""
    concepts = concept_by_id()
    cells = defaultdict(lambda: defaultdict(set))
    for r in results:
        if r["low_effort"] or r["support"] and not r["concepts"]:
            continue
        for cid in r["concepts"]:
            cells[(r["week"], cid)]["mentions"].add(r["id"])
        for f in r["findings"]:
            if f["concept"] in concepts and f["signal"] != "support_need":
                cells[(r["week"], f["concept"])]["mentions"].add(r["id"])
                cells[(r["week"], f["concept"])][f["signal"]].add(r["id"])
                if f["signal"] in ISSUE_SIGNALS:
                    cells[(r["week"], f["concept"])]["issue"].add(r["id"])
    rows = []
    for (week, cid), d in cells.items():
        c = concepts[cid]
        n = len(d["mentions"])
        rows.append({
            "week": week, "concept": cid, "topic": c["name"], "module": c["module"], "responses": n,
            "issues": len(d["issue"]), "confusion": len(d["conceptual_confusion"]),
            "transfer": len(d["transfer_difficulty"]), "recurring": len(d["recurring_issue"]),
            "pacing": len(d["pacing_concern"]), "comprehension": len(d["comprehension"]),
            "hidden": n < MIN_GROUP_SIZE,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["issue_rate"] = (df["issues"] / df["responses"]).round(2)
    return add_flags(df.sort_values(["week", "issues"], ascending=[True, False]).reset_index(drop=True))


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Spike: issue rate above the class p-chart 2-sigma warning limit (Module 2 SPC idea).
    Recurring: issues on the same topic in 2+ visible weeks, or 3+ recurring-issue labels."""
    vis = df[~df["hidden"]]
    tot_i, tot_n = vis["issues"].sum(), vis["responses"].sum()
    pbar = tot_i / max(1, tot_n)

    def ucl(r):
        # Leave-one-out baseline so a big spike doesn't inflate its own control limit.
        i, n = (tot_i - r["issues"], tot_n - r["responses"]) if not r["hidden"] else (tot_i, tot_n)
        p = i / max(1, n)
        return round(min(1.0, p + 2 * math.sqrt(p * (1 - p) / r["responses"])), 2)

    df["ucl"] = df.apply(ucl, axis=1)
    df["spike"] = (~df["hidden"]) & (df["issue_rate"] > df["ucl"]) & (df["issues"] >= 3)
    weeks_with_issues = vis[vis["issues"] >= 2].groupby("concept")["week"].apply(set).to_dict()
    df["recurring_flag"] = df.apply(
        lambda r: (not r["hidden"]) and r["issues"] >= 2 and (
            r["recurring"] >= 3 or any(w < r["week"] for w in weeks_with_issues.get(r["concept"], set()))),
        axis=1,
    )
    df.attrs["pbar"] = round(pbar, 3)
    return df


def visible(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df["hidden"]] if not df.empty else df


def top_topics(df: pd.DataFrame, week: int, n: int = 3) -> pd.DataFrame:
    w = visible(df)
    if w.empty:
        return w
    w = w[(w["week"] == week) & (w["issues"] > 0)]
    return w.sort_values(["issues", "issue_rate"], ascending=False).head(n)


def evidence_for(results: list[dict], week: int, concept: str, limit: int = 8) -> list[dict]:
    """Paraphrased evidence only (never quotes), for a visible topic."""
    out = []
    for r in results:
        if r["week"] != week or r["support"]:
            continue
        for f in r["findings"]:
            if f["concept"] == concept and f["signal"] != "support_need":
                out.append({"signal": f["signal"], "paraphrase": f["paraphrase"], "confidence": f["confidence"]})
    order = {"conceptual_confusion": 0, "recurring_issue": 1, "transfer_difficulty": 2, "pacing_concern": 3, "comprehension": 4}
    out.sort(key=lambda x: order.get(x["signal"], 9))
    seen, uniq = set(), []
    for e in out:
        k = (e["signal"], e["paraphrase"])
        if k not in seen:
            seen.add(k)
            uniq.append({**e, "count": sum(1 for x in out if (x["signal"], x["paraphrase"]) == k)})
    return uniq[:limit]


def suggestions(df: pd.DataFrame, results: list[dict], week: int) -> list[str]:
    """AI-suggested topics to revisit. Always labeled as suggestions; faculty decide."""
    concepts = concept_by_id()
    tips = []
    for _, r in top_topics(df, week).iterrows():
        if r["issue_rate"] < 0.3:
            continue
        c = concepts[r["concept"]]
        kinds = []
        if r["confusion"]:
            kinds.append(f"{r['confusion']} unsure or holding a misconception")
        if r["transfer"]:
            kinds.append(f"{r['transfer']} unsure how to apply it at work")
        if r["pacing"]:
            kinds.append(f"{r['pacing']} felt it moved too fast")
        if r["recurring"]:
            kinds.append(f"{r['recurring']} still confused from an earlier week")
        tip = f"**{c['name']}** ({r['responses']} responses: {'; '.join(kinds)})."
        mis = [f for x in results if x["week"] == week for f in x["findings"]
               if f["concept"] == r["concept"] and "misconception" in f["paraphrase"].lower()]
        if mis and c.get("misconceptions"):
            tip += f" A common misconception is showing up: *{c['misconceptions'][0]['text']}*. Correct version: {c['description']}"
        elif r["pacing"] > max(r["confusion"], r["transfer"]):
            tip += " Consider slowing down: a five-minute recap at the start of next class, or moving some slides to a short video."
        elif r["transfer"] > r["confusion"]:
            tip += " Consider a short worked example of applying it to a workplace problem."
        else:
            tip += " Consider a five-minute review at the start of next class."
        tips.append(tip)
    return tips
