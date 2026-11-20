import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COURSE_MODEL_PATH = DATA / "course_model.json"
DATASET_PATH = DATA / "reflections.json"
DB_PATH = Path(os.getenv("CC_DB_PATH", str(DATA / "coursecorrect.db")))
REPORTS = ROOT / "reports"

SIGNALS = [
    "comprehension",
    "conceptual_confusion",
    "transfer_difficulty",
    "recurring_issue",
    "pacing_concern",
    "support_need",
]
SIGNAL_LABELS = {
    "comprehension": "Comprehension",
    "conceptual_confusion": "Conceptual confusion",
    "transfer_difficulty": "Applied-transfer difficulty",
    "recurring_issue": "Recurring issue",
    "pacing_concern": "Pacing concern",
    "support_need": "Support need",
}
# Signals that count as "something to revisit" on the dashboard.
ISSUE_SIGNALS = {"conceptual_confusion", "transfer_difficulty", "recurring_issue", "pacing_concern"}

MIN_GROUP_SIZE = 5          # topics with fewer responses are hidden
REVIEW_CONFIDENCE = 0.6     # findings below this go to human review first

CORE_PROMPTS = {
    "explain": "What from this week could you explain to a colleague?",
    "unclear": "What is still least clear to you?",
    "apply": "How would you apply one idea from this week at work?",
}
OPTIONAL_PROMPT_ROTATION = [
    "How would you teach this week's concept to someone new?",
    "What assumption did this week's material challenge?",
    "Where would this idea break down in practice?",
]

DISCLOSURE = (
    "**Before you start.** This weekly reflection takes about five minutes. "
    "It never affects your grade, and completion credit doesn't depend on what you write. "
    "Your student ID is replaced with a pseudonym and names or contact details are removed "
    "before an AI model reads your answers. Your instructor sees only class-level patterns "
    "(any topic with fewer than five responses is hidden) and paraphrased evidence, never your "
    "words or your name, unless you tick \"I'd like follow-up\". CourseCorrect never grades, ranks "
    "or disciplines anyone. Raw reflections are deleted at the end of term. "
    "CourseCorrect is not a crisis service."
)

SUPPORT_MESSAGE = (
    "It sounds like this week may have been a lot. You don't have to handle it alone. "
    "Your instructor holds office hours every week, and NYU SPS academic support can help "
    "with workload and study planning. The **NYU Wellness Exchange** is free, confidential "
    "and available 24/7 by phone or through the NYU Mobile app. If you are in immediate danger, "
    "call 911 or text/call 988. This message went only to you: your instructor does not "
    "receive an at-risk list."
)
FOLLOWUP_MESSAGE = "Thanks. You asked for follow-up, so your instructor will see your name on their follow-up list."


def default_backend() -> str:
    forced = os.getenv("CC_BACKEND")
    if forced:
        return forced
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "offline"
