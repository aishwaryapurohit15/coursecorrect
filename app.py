"""CourseCorrect Streamlit app.  Run:  streamlit run app.py"""
import json
import uuid

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cc import analytics, store, theme, tutor
from cc.agent import process
from cc.config import (CORE_PROMPTS, DISCLOSURE, MIN_GROUP_SIZE, OPTIONAL_PROMPT_ROTATION,
                       REVIEW_CONFIDENCE, SIGNAL_LABELS, SIGNALS, default_backend)
from cc.course_model import concept_by_id, load_course_model, module_for_week
from cc.pipeline import load_dataset, run_dataset
from cc.privacy import redact

st.set_page_config(page_title="CourseCorrect · NYU SPS", page_icon="🟣", layout="wide")
theme.apply()


@st.cache_resource
def get_con():
    return store.connect()


con = get_con()
CONCEPTS = concept_by_id()
WEEKS = [m["week"] for m in load_course_model()["modules"]]


def week_label(w):
    m = module_for_week(w)
    return f"Week {w}: Module {m['module']} · {m['title']}" if m else f"Week {w}"


# ---------------- Sidebar ----------------
theme.sidebar_brand()
page = st.sidebar.radio("Navigate", ["Student reflection", "AI tutor", "Faculty dashboard", "Review queue", "Evaluation", "Setup & governance"])
backends = ["offline", "claude", "openai"]
if "backend" not in st.session_state:
    st.session_state.backend = default_backend()
st.session_state.backend = st.sidebar.selectbox(
    "AI labeler", backends, index=backends.index(st.session_state.backend),
    help="Used by the reflection labeler and the AI tutor. claude needs ANTHROPIC_API_KEY, openai needs OPENAI_API_KEY. "
         "offline is a rule-based fallback.")
if st.session_state.backend == "offline":
    st.sidebar.info("Offline mode: rule-based labeler and retrieval-only tutor (no API key). Set a key and pick claude or openai for the real agent.")
st.sidebar.caption("Prototype · simulated data only · no real student data")


# ---------------- Student reflection ----------------
def page_student():
    theme.page_header("Weekly reflection", "About five minutes. It never affects your grade, and only class-level patterns reach your instructor.",
                      eyebrow="Student · CourseCorrect")
    with st.expander("What is collected and who sees it", expanded=True):
        st.markdown(DISCLOSURE)
    theme.section("Your details")
    c1, c2 = st.columns([1, 2])
    week = c1.selectbox("Week", WEEKS, index=len(WEEKS) - 1, format_func=week_label)
    student_id = c2.text_input("Student ID (simulated, e.g. N10001)", value="N10001")
    optional_prompt = OPTIONAL_PROMPT_ROTATION[week % len(OPTIONAL_PROMPT_ROTATION)]
    theme.section("This week's prompts")
    with st.form("reflection", clear_on_submit=False):
        explain = st.text_area(CORE_PROMPTS["explain"], height=90)
        unclear = st.text_area(CORE_PROMPTS["unclear"], height=90)
        apply_ = st.text_area(CORE_PROMPTS["apply"], height=90)
        optional = st.text_area(f"Optional this week: {optional_prompt}", height=70)
        follow_up = st.checkbox("I'd like follow-up from my instructor (they will see my name)")
        submitted = st.form_submit_button("Submit reflection", type="primary")
    if submitted:
        if not (explain or unclear or apply_):
            st.warning("Please answer at least one prompt.")
            return
        refl = {"id": "F-" + uuid.uuid4().hex[:8], "week": week, "student_id": student_id, "source": "form",
                "explain": explain, "unclear": unclear, "apply": apply_, "optional": optional,
                "optional_prompt": optional_prompt, "follow_up": follow_up}
        roster = load_dataset()["roster"]
        with st.spinner("Reading your reflection..."):
            res = process(refl, st.session_state.backend, roster)
        store.save(con, refl, res)
        st.session_state.last = (refl["id"], res)
    if "last" in st.session_state:
        rid, res = st.session_state.last
        st.success("Thanks, your reflection was submitted.")
        for msg in res["student_messages"]:
            st.info(msg)
        with st.expander("How your reflection was read (you can flag mistakes)"):
            if res["low_effort"]:
                st.write("No course topics were identified.")
            for f in res["findings"]:
                if f["signal"] == "support_need":
                    continue
                c = CONCEPTS.get(f["concept"])
                st.write(f"- **{SIGNAL_LABELS[f['signal']]}**{' · ' + c['name'] if c else ''}: {f['paraphrase']}")
            note = st.text_input("Something misread? Tell us what.", key=f"flag_{rid}")
            if st.button("Flag this reading", key=f"flagbtn_{rid}") and note:
                con.execute("INSERT INTO student_flags(reflection_id, note, created_at) VALUES (?,?,?)", (rid, note, store.now()))
                con.commit()
                st.toast("Thanks, flagged for review.")


# ---------------- AI tutor ----------------
TUTOR_STARTERS = ["What's the difference between invention and innovation?",
                  "Explain crossing the chasm with a workplace example",
                  "Is disruptive just a more advanced technology?",
                  "Quiz me on falsifiability"]


def page_tutor():
    theme.page_header("AI course tutor", "Ask about any idea from the course so far. It explains, corrects common mix-ups and quizzes you; it won't do graded work for you.",
                      eyebrow="Student · CourseCorrect")
    c1, c2 = st.columns([2, 1])
    week = c1.selectbox("I'm in", WEEKS, index=len(WEEKS) - 1, format_func=week_label, key="tutor_week",
                        help="The tutor only uses material taught up to this week.")
    if c2.button("Start a new chat", width="stretch"):
        st.session_state.tutor_msgs = []
        st.session_state.tutor_last = []
    with st.expander("How the tutor works and what it keeps"):
        st.markdown(
            "- Answers come only from the instructor-approved **course model**; if something isn't there, it says so rather than guess.\n"
            "- Your message passes the same **privacy gateway** as reflections: names, emails, phone numbers and IDs are removed, "
            "and instruction-like text aimed at the AI is ignored.\n"
            "- It keeps **no transcript** and no student ID. Your instructor sees only how many questions were asked per topic, "
            f"and topics with fewer than {MIN_GROUP_SIZE} questions are hidden.\n"
            "- If you mention you're struggling, it points you to support right away. That stays with you: nothing is logged.\n"
            "- It is an AI and can be wrong. It is not a crisis service and has no effect on your grade.")

    msgs = st.session_state.setdefault("tutor_msgs", [])
    if not msgs:
        msgs.append({"role": "assistant", "content": tutor.intro_message(week), "kind": "intro"})

    for m in msgs:
        with st.chat_message(m["role"], avatar="🟣" if m["role"] == "assistant" else "🧑‍🎓"):
            st.markdown(m["content"])
            if m.get("sources"):
                st.markdown("".join(f'<span class="cc-pill">Module {c["module"]} · {c["name"]}</span>' for c in m["sources"]),
                            unsafe_allow_html=True)
            for n in m.get("notes", []):
                st.caption("🛡️ " + n)
            if m["role"] == "assistant" and m.get("backend"):
                st.caption("Written by " + {"offline": "the course-model retriever (offline)", "claude": "Claude, grounded in the course model",
                                            "openai": "OpenAI, grounded in the course model", "rules": "CourseCorrect's guardrails"}[m["backend"]])

    prompt = None
    if len(msgs) <= 1:
        cols = st.columns(len(TUTOR_STARTERS))
        for col, q in zip(cols, TUTOR_STARTERS):
            if col.button(q, key="starter_" + q, width="stretch"):
                prompt = q
    typed = st.chat_input("Ask about a concept, or say \"quiz me\"")
    prompt = typed or prompt
    if prompt:
        history = [{"role": m["role"], "content": m["content"]} for m in msgs if m.get("kind") != "intro"]
        with st.spinner("Thinking..."):
            res = tutor.respond(prompt, week, st.session_state.backend, history=history,
                                roster=load_dataset()["roster"], last_concepts=st.session_state.get("tutor_last"))
        shown, _ = redact(prompt, load_dataset()["roster"])  # the on-screen transcript is redacted too
        msgs.append({"role": "user", "content": shown})
        msgs.append({"role": "assistant", "content": res["text"], "kind": res["kind"], "backend": res["backend"],
                     "sources": [{"module": c["module"], "name": c["name"]} for c in res["sources"]], "notes": res["notes"]})
        if res["sources"]:
            st.session_state.tutor_last = [c["id"] for c in res["sources"]]
        store.log_tutor(con, week, res["sources"][0]["id"] if res["sources"] else None, res["kind"])
        st.rerun()


# ---------------- Faculty dashboard ----------------
def page_dashboard():
    theme.page_header("Faculty dashboard", "Class-level patterns from weekly reflections. The AI diagnoses; you decide what, if anything, to change.",
                      eyebrow="Faculty · CourseCorrect")
    results = store.load_results(con)
    if not results:
        st.info("No reflections yet. Go to **Setup & governance** and load the simulated dataset, or submit a reflection.")
        return
    df = analytics.topic_week_table(results)
    weeks = sorted({r["week"] for r in results})
    week = st.selectbox("Week", weeks, index=len(weeks) - 1, format_func=week_label)
    wk_results = [r for r in results if r["week"] == week]
    top = analytics.top_topics(df, week)
    fups = con.execute("SELECT * FROM followups WHERE week=? AND resolved=0", (week,)).fetchall()
    queue = [r for r in wk_results if r["needs_review"] and not r["reviewed"] and not r["support"]]
    vis_week = analytics.visible(df)
    vis_week = vis_week[vis_week["week"] == week] if not vis_week.empty else vis_week

    # Summary card
    with st.container(border=True):
        st.subheader("This week at a glance")
        st.caption(week_label(week))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Reflections", len(wk_results))
        m2.metric("Topics to revisit", len(top))
        m3.metric("Follow-up requests", len(fups))
        m4.metric("Awaiting review", len(queue))
        if not top.empty:
            st.markdown("**Top topics needing attention**")
            st.markdown("".join(f'<span class="cc-pill">{r.topic} · {r.issues}/{r.responses}</span>'
                                for r in top.itertuples()), unsafe_allow_html=True)
        flags = []
        if not vis_week.empty:
            flags += [f"⚡ Spike: **{r.topic}** ({int(r.issue_rate*100)}% vs. class warning limit {int(r.ucl*100)}%)"
                      for r in vis_week[vis_week["spike"]].itertuples()]
            flags += [f"🔁 Recurring: **{r.topic}** keeps coming up across weeks" for r in vis_week[vis_week["recurring_flag"]].itertuples()]
        for f in flags:
            st.markdown(f)
        hidden_n = int(df[(df["week"] == week) & df["hidden"]].shape[0]) if not df.empty else 0
        if hidden_n:
            st.caption(f"{hidden_n} topic(s) this week had fewer than {MIN_GROUP_SIZE} responses and are hidden to protect privacy.")

    theme.section("Suggestions")
    st.subheader("AI-suggested topics to revisit")
    st.caption("Suggestions from the AI, with their evidence. You decide what, if anything, to change.")
    tips = analytics.suggestions(df, results, week)
    if not tips:
        st.write("Nothing stands out this week.")
    for i, (tip, row) in enumerate(zip(tips, top.itertuples())):
        with st.container(border=True):
            st.markdown(":violet-badge[AI suggestion] " + tip)
            b1, b2, _ = st.columns([1, 1, 6])
            if b1.button("👍 Useful", key=f"u{week}{i}"):
                con.execute("INSERT INTO feedback(week, concept, verdict, created_at) VALUES (?,?,?,?)", (week, row.concept, "useful", store.now()))
                con.commit(); st.toast("Thanks, recorded.")
            if b2.button("👎 Off", key=f"o{week}{i}"):
                con.execute("INSERT INTO feedback(week, concept, verdict, created_at) VALUES (?,?,?,?)", (week, row.concept, "off", store.now()))
                con.commit(); st.toast("Thanks, recorded.")

    theme.section("Trends")
    st.subheader("Topic heatmap")
    metric = st.radio("Show", ["issue_rate", "confusion", "transfer", "pacing", "comprehension"], horizontal=True,
                      format_func=lambda m: {"issue_rate": "Share with an issue", "confusion": "Confusion",
                                             "transfer": "Transfer difficulty", "pacing": "Pacing", "comprehension": "Comprehension"}[m])
    order = [c["name"] for c in CONCEPTS.values()]
    hm = df.copy()
    hm["val"] = hm.apply(lambda r: float("nan") if r["hidden"] else float(r[metric]), axis=1)
    hm["txt"] = hm.apply(lambda r: f"<{MIN_GROUP_SIZE}" if r["hidden"] else (f"{int(r[metric]*100)}%" if metric == "issue_rate" else str(r[metric])), axis=1)
    piv = hm.pivot_table(index="topic", columns="week", values="val", aggfunc="first", dropna=False).reindex([o for o in order if o in set(hm["topic"])])
    txt = hm.pivot_table(index="topic", columns="week", values="txt", aggfunc="first").reindex(index=piv.index, columns=piv.columns).fillna("")
    piv = piv.astype(float)
    fig = go.Figure(go.Heatmap(z=piv.values, x=[f"W{w}" for w in piv.columns], y=piv.index, text=txt.values,
                               texttemplate="%{text}", colorscale=theme.VIOLET_SCALE if metric != "comprehension" else theme.TEAL_SCALE,
                               hoverongaps=False, xgap=2, ygap=2, colorbar=dict(title="", thickness=12, outlinewidth=0)))
    fig.update_layout(height=40 * len(piv.index) + 120, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(autorange="reversed"))
    theme.style_fig(fig).update_xaxes(showgrid=False).update_yaxes(showgrid=False)
    st.plotly_chart(fig, width="stretch")
    st.caption(f"Cells marked <{MIN_GROUP_SIZE} are hidden (fewer than {MIN_GROUP_SIZE} responses).")

    theme.section("Drill down")
    st.subheader("Topic detail")
    if vis_week.empty:
        st.write("No topics this week have enough responses to show.")
    else:
        topic = st.selectbox("Topic", vis_week.sort_values("issues", ascending=False)["concept"].tolist(),
                             format_func=lambda c: CONCEPTS[c]["name"])
        row = vis_week[vis_week["concept"] == topic].iloc[0]
        c1, c2 = st.columns([1, 2])
        counts = pd.DataFrame({"signal": ["Comprehension", "Confusion", "Transfer", "Recurring", "Pacing"],
                               "students": [row.comprehension, row.confusion, row.transfer, row.recurring, row.pacing]})
        bar = px.bar(counts, x="students", y="signal", orientation="h", height=260,
                     color_discrete_sequence=[theme.VIOLET])
        bar.update_traces(marker_line_width=0)
        c1.plotly_chart(theme.style_fig(bar).update_layout(margin=dict(l=0, r=0, t=0, b=0), yaxis_title=None,
                                                          bargap=0.35), width="stretch")
        c2.markdown(f"**{CONCEPTS[topic]['name']}** · {row.responses} responses")
        c2.caption("Paraphrased evidence (never direct quotes)")
        for e in analytics.evidence_for(results, week, topic):
            c2.markdown(f"- *{SIGNAL_LABELS[e['signal']]}* · {e['paraphrase']}" + (f" (×{e['count']})" if e["count"] > 1 else ""))

    theme.section("AI tutor")
    st.subheader("What students asked the tutor about")
    st.caption(f"Question counts per topic only: no question text and no names. Topics with fewer than {MIN_GROUP_SIZE} questions are hidden.")
    tq = store.tutor_topic_counts(con, week)
    shown_tq = [t for t in tq if t["n"] >= MIN_GROUP_SIZE]
    if shown_tq:
        st.markdown("".join(f'<span class="cc-pill">{CONCEPTS[t["concept"]]["name"] if t["concept"] in CONCEPTS else t["concept"]} · {t["n"]} questions</span>'
                            for t in shown_tq), unsafe_allow_html=True)
    else:
        st.write("Not enough tutor questions this week to show." if tq else "No tutor questions this week yet.")
    if len(tq) > len(shown_tq):
        st.caption(f"{len(tq) - len(shown_tq)} topic(s) hidden (fewer than {MIN_GROUP_SIZE} questions).")

    theme.section("Students")
    st.subheader("Follow-up requests")
    st.caption("Only students who ticked \"I'd like follow-up\" appear here. There is never an at-risk list.")
    if fups:
        st.dataframe(pd.DataFrame([dict(f) for f in fups])[["student_id", "week", "topic_hint", "created_at"]], hide_index=True)
    else:
        st.write("None this week.")

    fb = pd.read_sql("SELECT verdict, COUNT(*) n FROM feedback GROUP BY verdict", con)
    if not fb.empty:
        st.caption("Insight-quality feedback so far: " + ", ".join(f"{r.verdict}: {r.n}" for r in fb.itertuples()))


# ---------------- Review queue ----------------
def page_review():
    theme.page_header("Human review queue", "A person checks uncertain labels before they count.", eyebrow="Faculty · CourseCorrect")
    st.caption(f"Low-confidence (< {REVIEW_CONFIDENCE}) labels, failed evidence checks and screened injection attempts "
               "are checked by a person before they count. Support cases are never shown here.")
    items = [r for r in store.load_results(con) if r["needs_review"] and not r["reviewed"] and not r["support"]]
    if not items:
        st.success("Queue is empty.")
        return
    for r in items:
        with st.expander(f"{r['id']} · Week {r['week']} · {r['review_reason']}"):
            st.markdown(f"**Explain:** {r['explain'] or '—'}  \n**Least clear:** {r['unclear'] or '—'}  \n"
                        f"**Apply:** {r['apply'] or '—'}" + (f"  \n**Optional:** {r['optional']}" if r["optional"] else ""))
            st.caption("Text shown after redaction and injection screening.")
            keep = []
            for j, f in enumerate(r["findings"]):
                c = CONCEPTS.get(f["concept"])
                lab = f"{SIGNAL_LABELS[f['signal']]} · {c['name'] if c else 'no topic'} · conf {f['confidence']:.2f} · evidence: \"{f['evidence']}\""
                if st.checkbox(lab, value=True, key=f"k{r['id']}{j}"):
                    keep.append(f)
            add_sig = st.multiselect("Add missing signal", [s for s in SIGNALS if s != "support_need"], key=f"a{r['id']}",
                                     format_func=lambda s: SIGNAL_LABELS[s])
            add_con = st.selectbox("…for topic", ["none"] + list(CONCEPTS), key=f"c{r['id']}",
                                   format_func=lambda c: "no topic" if c == "none" else CONCEPTS[c]["name"])
            if st.button("Approve", key=f"ap{r['id']}", type="primary"):
                for s in add_sig:
                    keep.append({"signal": s, "concept": add_con, "evidence": "(added by reviewer)",
                                 "paraphrase": f"Reviewer added: {SIGNAL_LABELS[s].lower()}.", "confidence": 1.0})
                for f in keep:
                    f["confidence"] = max(f["confidence"], REVIEW_CONFIDENCE)
                concepts = sorted({f["concept"] for f in keep if f["concept"] != "none"} | set(r["concepts"]))
                store.update_findings(con, r["id"], keep, concepts)
                st.rerun()


# ---------------- Evaluation ----------------
def page_eval():
    from cc.evaluate import evaluate, to_markdown
    theme.page_header("Evaluation", "Scored against pre-registered criteria (H1–H7).", eyebrow="Research · CourseCorrect")
    st.caption("Runs all 100 simulated reflections through the agent in a temporary database and scores Table 6. "
               "Thresholds were set before testing; a miss is a finding to report, not a reason to move the target.")
    b = st.session_state.backend
    if b != "offline":
        st.warning(f"This makes about 140 calls to the {b} API (100 reflections + stability reruns on 20).")
    if st.button(f"Run evaluation with the {b} labeler", type="primary"):
        bar = st.progress(0.0)
        rep = evaluate(b, progress=bar.progress)
        st.session_state.rep = rep
    rep = st.session_state.get("rep")
    if rep:
        (st.success if rep["core_pass"] else st.error)(
            f"Core criteria H1, H3, H5, H6: {'met' if rep['core_pass'] else 'not met'} ({rep['backend']} labeler)")
        tbl = pd.DataFrame([{"Hypothesis": h, "Metric": d["metric"], "Threshold": d["threshold"], "Result": str(d["value"]),
                             "Pass": "—" if d["pass"] is None else ("✅" if d["pass"] else "❌")} for h, d in rep["hypotheses"].items()])
        st.dataframe(tbl, hide_index=True, width="stretch")
        if rep["backend"] == "offline":
            st.info("Offline scores are optimistic: its rules were written alongside this dataset. Treat them as a pipeline "
                    "check. The real test is the LLM labeler, plus fresh hand-written reflections the rules have never seen.")
        with st.expander("Per-signal F1 and H1 detail"):
            st.json({"per_signal_f1": rep["hypotheses"]["H2"]["detail"], "planted": rep["hypotheses"]["H1"]["detail"]})
        with st.expander(f"Failure log ({len(rep['errors'])})"):
            st.dataframe(pd.DataFrame(rep["errors"]), hide_index=True, width="stretch")
        st.download_button("Download report (Markdown)", to_markdown(rep), file_name=f"eval_{rep['backend']}.md")


# ---------------- Setup & governance ----------------
def page_setup():
    theme.page_header("Setup & governance", "Load data, approve the course model, and review how the system is governed.", eyebrow="Admin · CourseCorrect")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.subheader("1. Load simulated dataset")
        st.write("100 fictional reflections: 10 personas × Weeks 2–9 plus 20 adversarial cases.")
        if st.button(f"Process dataset with the {st.session_state.backend} labeler", type="primary"):
            store.reset(con)
            bar = st.progress(0.0)
            run_dataset(con, st.session_state.backend, progress=bar.progress)
            st.success("Done. Open the Faculty dashboard.")
        if st.button("Clear all reflections"):
            store.reset(con); st.success("Cleared.")
    with c2, st.container(border=True):
        st.subheader("Retention")
        st.write("End of term: delete all reflection text and follow-up names; keep only de-identified labels.")
        if st.button("Run end-of-term purge"):
            store.purge_raw_text(con); st.success("Raw text deleted.")

    with st.container(border=True):
        st.subheader("2. Course model (faculty approval)")
        cm = load_course_model()
        approved = store.get_setting(con, "course_model_approved") == "yes"
        st.write(("✅ Approved by faculty." if approved else "⚠️ Draft: not yet approved by the instructor.") + " " + cm["note"])
        for m in cm["modules"]:
            with st.expander(f"Week {m['week']} · Module {m['module']}: {m['title']}"):
                st.write("**Objectives:** " + "; ".join(m["objectives"]))
                for c in m["concepts"]:
                    st.markdown(f"- **{c['name']}**: {c['description']}" +
                                (f"  \n  _Known misconception:_ {c['misconceptions'][0]['text']}" if c["misconceptions"] else ""))
        if st.button("Approve course model" if not approved else "Revoke approval"):
            store.set_setting(con, "course_model_approved", "no" if approved else "yes")
            store.audit(con, "faculty", "course_model_approval", "revoked" if approved else "approved")
            st.rerun()

    with st.container(border=True):
        st.subheader("Prohibited uses")
        st.markdown("CourseCorrect may never be used for: grading; ranking or comparing students; discipline or "
                    "academic-integrity cases; admissions or reference decisions; inferring protected traits; scoring "
                    "emotions or engagement; sharing data outside the course team; or training outside AI models. "
                    "The agent has no write access to grades, the LMS or student records.")

    with st.expander("Audit log"):
        st.dataframe(pd.read_sql("SELECT ts, actor, action, detail FROM audit ORDER BY id DESC LIMIT 200", con),
                     hide_index=True, width="stretch")
    with st.expander("Student flags on how reflections were read"):
        st.dataframe(pd.read_sql("SELECT reflection_id, note, created_at FROM student_flags", con), hide_index=True)


{"Student reflection": page_student, "AI tutor": page_tutor, "Faculty dashboard": page_dashboard, "Review queue": page_review,
 "Evaluation": page_eval, "Setup & governance": page_setup}[page]()
theme.footer()
