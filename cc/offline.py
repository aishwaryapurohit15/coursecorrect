"""Offline labeler: a transparent rule-based stand-in for the LLM.

Used when no API key is configured, so the demo always runs. It reads the same course
context as the LLM (aliases and known misconceptions from the course model), but it is
a baseline, not the proposed intelligence layer. The proposal itself argues keyword
rules fall short (Section 3); the evaluation page lets you compare the two.
"""
import re

from .course_model import match_concepts

_SENT = re.compile(r"(?<=[.!?;])\s+")

CONFUSION = re.compile(
    r"confus|unclear|not clear|not sure|don'?t (fully )?(get|understand)|do not understand|"
    r"mix(ing)? (up|them up)|mixing up|lost (on|me)|still don'?t|isn'?t every|why .*\?|how is .*\?|"
    r"when (does |an? )?.*becomes?|\bi (am|'m) confuse",
    re.I,
)
NOTHING = re.compile(r"^\s*(nothing|all clear|clear|pretty clear|not much|no(ne)?\b|n/?a)", re.I)
TRANSFER = re.compile(
    r"not sure (yet )?how|can'?t see how|don'?t know how|hard to apply|not sure how to (use|apply)|"
    r"i am not sure how|feels abstract",
    re.I,
)
PACING = re.compile(r"too fast|went by (very |so )?fast|went too fast|rushed|more time|too much in one|too quick", re.I)
RECUR_CUE = re.compile(r"\bstill\b|last week|again", re.I)
# Distress language. Deliberately excludes course idioms ("killing me", "killer use",
# "dying to try") and ordinary busy-professional complaints ("no time", "brutal deadlines").
SUPPORT = re.compile(
    r"can'?t cope|cannot cope|overwhelmed and|falling apart|hopeless|panic attack|"
    r"don'?t know if i can keep going|can'?t keep going|thinking about dropping|"
    r"haven'?t slept|i am not okay|i'?m not okay|cry every|want to give up|self[- ]harm|"
    r"hurt myself|no point in anything|alone and",
    re.I,
)


def _sentences(text: str) -> list[str]:
    return [s for s in _SENT.split(text.strip()) if s] if text else []


def _first_match_sentence(text: str, pattern: re.Pattern) -> str | None:
    for s in _sentences(text):
        if pattern.search(s):
            return s
    return None


def label(fields: dict, week: int, candidates: list[dict]) -> dict:
    explain, unclear = fields.get("explain", ""), fields.get("unclear", "")
    apply_, optional = fields.get("apply", ""), fields.get("optional", "")
    all_text = " ".join(x for x in (explain, unclear, apply_, optional) if x)
    by_id = {c["id"]: c for c in candidates}
    concepts = match_concepts(all_text, candidates)
    findings = []

    def add(signal, concept, evidence, paraphrase, conf):
        findings.append({"signal": signal, "concept": concept or "none", "evidence": evidence,
                         "paraphrase": paraphrase, "confidence": conf})

    # Support screen first, so a short distressed reflection is never dismissed as low effort.
    sup = _first_match_sentence(all_text, SUPPORT)
    if sup:
        add("support_need", None, sup, "Student may be struggling and was sent support resources.", 0.9)

    words = re.findall(r"[a-zA-Z]{3,}", all_text)
    low_effort = (not concepts and not sup and len(words) < 25
                  and not CONFUSION.search(unclear or "") and not PACING.search(all_text))
    if low_effort:
        return {"concepts": [], "low_effort": True, "findings": findings}

    # Known misconceptions from the course model, anywhere in the reflection.
    misconception_in_explain = False
    for c in candidates:
        for mc in c.get("misconceptions", []):
            for field_name, text in (("explain", explain), ("unclear", unclear), ("optional", optional)):
                s = _first_match_sentence(text, re.compile(mc["pattern"], re.I))
                if s:
                    if field_name == "explain":
                        misconception_in_explain = True
                    if not any(f["concept"] == c["id"] and f["signal"] == "conceptual_confusion" for f in findings):
                        add("conceptual_confusion", c["id"], s, f"Holds a common misconception: {mc['text'].lower()}.", 0.85)
                        if c["id"] not in concepts:
                            concepts.append(c["id"])

    # Comprehension: a substantive, concept-grounded answer to "what could you explain".
    exp_concepts = match_concepts(explain, candidates)
    if explain and exp_concepts and not misconception_in_explain:
        c = by_id[exp_concepts[0]]
        add("comprehension", c["id"], _sentences(explain)[0], f"Can explain {c['name']} in their own words.", 0.8)

    # Confusion and recurring issues from the "least clear" (and optional) answers.
    for text in (unclear, optional):
        for s in _sentences(text):
            if NOTHING.search(s) or not CONFUSION.search(s):
                continue
            s_concepts = match_concepts(s, candidates) or match_concepts(text, candidates)
            if not s_concepts:
                add("conceptual_confusion", None, s, "Unsure about part of this week's material (topic unclear).", 0.5)
                continue
            for cid in s_concepts:
                c = by_id[cid]
                if not any(f["concept"] == cid and f["signal"] == "conceptual_confusion" for f in findings):
                    add("conceptual_confusion", cid, s, f"Unsure about {c['name']}.", 0.75)
                if c["week"] < week and RECUR_CUE.search(s):
                    if not any(f["concept"] == cid and f["signal"] == "recurring_issue" for f in findings):
                        add("recurring_issue", cid, s, f"Still confused about {c['name']} from an earlier week.", 0.75)

    # Applied-transfer difficulty from the "apply at work" answer.
    t = _first_match_sentence(apply_, TRANSFER)
    if t:
        cid = (match_concepts(apply_, candidates) or exp_concepts or concepts or [None])[0]
        add("transfer_difficulty", cid, t, "Understands the idea but isn't sure how to apply it at work.", 0.75)

    # Pacing anywhere.
    p = _first_match_sentence(all_text, PACING)
    if p:
        cid = (match_concepts(p, candidates) or concepts or [None])[0]
        add("pacing_concern", cid, p, "Felt this part of the class moved too fast.", 0.8)

    return {"concepts": concepts, "low_effort": False, "findings": findings}
