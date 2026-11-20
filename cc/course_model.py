"""Course context layer: the faculty-approved course model plus TF-IDF retrieval."""
import json
import re
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import COURSE_MODEL_PATH


@lru_cache(maxsize=1)
def load_course_model() -> dict:
    return json.loads(COURSE_MODEL_PATH.read_text())


def all_concepts() -> list[dict]:
    out = []
    for m in load_course_model()["modules"]:
        for c in m["concepts"]:
            out.append({**c, "module": m["module"], "week": m["week"], "module_title": m["title"]})
    return out


def concept_by_id() -> dict:
    return {c["id"]: c for c in all_concepts()}


def module_for_week(week: int) -> dict | None:
    for m in load_course_model()["modules"]:
        if m["week"] == week:
            return m
    return None


def concepts_taught_by(week: int) -> list[dict]:
    """Concepts from the current module and every earlier one (the course builds on itself)."""
    return [c for c in all_concepts() if c["week"] <= week]


def alias_regex(alias: str) -> re.Pattern:
    # Prefix match on a word boundary, so "falsifiab" matches "falsifiability".
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias.lower()))


def match_concepts(text: str, candidates: list[dict]) -> list[str]:
    t = text.lower()
    hits = []
    for c in candidates:
        if any(alias_regex(a).search(t) for a in c["aliases"]) or c["name"].lower() in t:
            hits.append(c["id"])
    return hits


@lru_cache(maxsize=16)
def _index(week: int):
    cands = concepts_taught_by(week)
    docs = [f'{c["name"]} {c["description"]} {" ".join(c["aliases"])}' for c in cands]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    mat = vec.fit_transform(docs)
    return cands, vec, mat


def retrieve(text: str, week: int, k: int = 6) -> list[dict]:
    """Retrieve course context for a reflection: every concept in this week's module, plus
    the k best TF-IDF / alias matches from earlier modules."""
    cands, vec, mat = _index(week)
    sims = cosine_similarity(vec.transform([text]), mat)[0]
    alias_hits = set(match_concepts(text, cands))
    scored = []
    for c, s in zip(cands, sims):
        score = float(s) + (0.5 if c["id"] in alias_hits else 0.0) + (0.3 if c["week"] == week else 0.0)
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    chosen = [c for _, c in scored if c["week"] == week]
    earlier = [c for s, c in scored if c["week"] != week and s > 0.05]
    return chosen + earlier[:k]
