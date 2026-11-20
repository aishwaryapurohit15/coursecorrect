"""NYU-inspired look and feel for the Streamlit app.

Visual only: nothing here changes what the app does. Colours follow NYU's public
brand palette (NYU violet #57068C). No official NYU logo artwork is used; the
header shows a plain text wordmark instead.
"""
import html

import streamlit as st

VIOLET = "#57068C"
VIOLET_DARK = "#330662"
VIOLET_BRIGHT = "#8900E1"
VIOLET_TINT = "#F6F2FA"
VIOLET_LINE = "#E4DAEE"
INK = "#1D1626"
MUTED = "#6B6275"

# Sequential scales for Plotly charts (light -> NYU violet).
VIOLET_SCALE = [[0.0, "#F6F2FA"], [0.25, "#D9C2EC"], [0.5, "#A970D6"], [0.75, "#7520AE"], [1.0, "#330662"]]
TEAL_SCALE = [[0.0, "#F1F8F9"], [0.5, "#7CC6D1"], [1.0, "#16707F"]]

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* Body font comes from .streamlit/config.toml; this is a fallback for text blocks only
   (icons use their own font, so no global override). */
.stMarkdown, .stCaption {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}

/* Thin violet bar across the very top of the page, like NYU web properties. */
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stAppViewContainer"]::before {{
  content: ""; position: fixed; top: 0; left: 0; right: 0; height: 4px;
  background: {VIOLET}; z-index: 1000;
}}
.block-container {{ padding-top: 2.2rem; max-width: 1180px; }}

/* Headings */
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
h3 {{ font-size: 1.15rem !important; }}

/* Page header band */
.cc-hero {{
  background: linear-gradient(120deg, {VIOLET_DARK} 0%, {VIOLET} 55%, #6f1fa5 100%);
  color: #fff; border-radius: 14px; padding: 1.4rem 1.6rem 1.3rem; margin: 0 0 1.4rem;
  box-shadow: 0 6px 20px rgba(87, 6, 140, 0.18);
}}
.cc-hero .cc-eyebrow {{
  font-size: 0.72rem; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase;
  opacity: 0.8; margin-bottom: 0.35rem;
}}
.cc-hero .cc-title {{ font-size: 1.75rem; font-weight: 700; line-height: 1.2; margin: 0; color: #fff; }}
.cc-hero .cc-sub {{ font-size: 0.95rem; opacity: 0.88; margin-top: 0.4rem; max-width: 60rem; }}

/* Sidebar wordmark */
.cc-brand {{ padding: 0.2rem 0 0.9rem; border-bottom: 1px solid {VIOLET_LINE}; margin-bottom: 0.9rem; }}
.cc-brand .cc-nyu {{
  display: inline-block; background: {VIOLET}; color: #fff; font-weight: 700; font-size: 0.8rem;
  letter-spacing: 0.08em; padding: 0.18rem 0.5rem; border-radius: 4px;
}}
.cc-brand .cc-school {{ display: block; font-size: 0.68rem; color: {MUTED}; font-weight: 600; margin-top: 0.45rem;
  letter-spacing: 0.08em; text-transform: uppercase; }}
.cc-brand .cc-name {{ font-size: 1.35rem; font-weight: 700; color: {VIOLET}; margin-top: 0.55rem; letter-spacing: -0.01em; }}
.cc-brand .cc-tag {{ font-size: 0.82rem; color: {MUTED}; margin-top: 0.1rem; }}

/* Sidebar navigation radio: make options look like a nav list */
[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 0.15rem; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{
  padding: 0.38rem 0.6rem; border-radius: 8px; width: 100%; transition: background .15s;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: #EDE3F6; }}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{ background: #E6D7F2; }}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {{ color: {VIOLET}; font-weight: 600; }}

/* Bordered containers become cards */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
  background: #fff; border-color: {VIOLET_LINE} !important;
  box-shadow: 0 1px 2px rgba(29, 22, 38, 0.04), 0 4px 14px rgba(87, 6, 140, 0.05);
}}

/* Metrics */
[data-testid="stMetric"] {{
  background: {VIOLET_TINT}; border: 1px solid {VIOLET_LINE}; border-radius: 10px; padding: 0.7rem 0.9rem;
}}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.78rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em; }}
[data-testid="stMetricValue"] {{ color: {VIOLET}; }}

/* Buttons */
.stButton button, .stDownloadButton button, .stFormSubmitButton button {{ font-weight: 600; }}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {{
  box-shadow: 0 2px 8px rgba(87, 6, 140, 0.25);
}}

/* Expanders and forms */
[data-testid="stExpander"] details {{ border-color: {VIOLET_LINE}; border-radius: 10px; }}
[data-testid="stExpander"] summary:hover p {{ color: {VIOLET}; }}
[data-testid="stForm"] {{ border-color: {VIOLET_LINE}; background: #fff; padding: 1.2rem 1.4rem; }}
textarea, input {{ background: #fff !important; }}

/* Section label used above groups of content */
.cc-section {{ font-size: 0.75rem; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase;
  color: {VIOLET}; margin: 1.6rem 0 0.15rem; }}

/* Small pills */
.cc-pill {{ display: inline-block; font-size: 0.78rem; font-weight: 600; padding: 0.15rem 0.6rem; border-radius: 999px;
  background: #EEE5F5; color: {VIOLET}; margin: 0 0.3rem 0.3rem 0; }}

/* Footer */
.cc-footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid {VIOLET_LINE}; color: {MUTED};
  font-size: 0.78rem; }}
</style>
"""


def apply():
    """Inject the global stylesheet. Call once per run, right after set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


def sidebar_brand():
    st.sidebar.markdown(
        '<div class="cc-brand">'
        '<span class="cc-nyu">NYU</span><span class="cc-school">School of Professional Studies</span>'
        '<div class="cc-name">CourseCorrect</div>'
        '<div class="cc-tag">The AI diagnoses; faculty decide.</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def page_header(title, subtitle="", eyebrow="CourseCorrect · NYU SPS"):
    st.markdown(
        f'<div class="cc-hero"><div class="cc-eyebrow">{html.escape(eyebrow)}</div>'
        f'<h1 class="cc-title">{html.escape(title)}</h1>'
        + (f'<div class="cc-sub">{html.escape(subtitle)}</div>' if subtitle else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def section(label):
    st.markdown(f'<div class="cc-section">{html.escape(label)}</div>', unsafe_allow_html=True)


def footer():
    st.markdown(
        '<div class="cc-footer">CourseCorrect prototype for the NYU School of Professional Studies · '
        "Simulated data only, no real student data · Not an official NYU service</div>",
        unsafe_allow_html=True,
    )


def style_fig(fig):
    """Apply consistent typography and colours to a Plotly figure."""
    fig.update_layout(
        font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=[VIOLET, VIOLET_BRIGHT, "#B98CDB", "#28A0B4", "#F2A900"],
        hoverlabel=dict(bgcolor="#fff", bordercolor=VIOLET_LINE, font=dict(color=INK)),
    )
    fig.update_xaxes(gridcolor=VIOLET_LINE, zerolinecolor=VIOLET_LINE)
    fig.update_yaxes(gridcolor=VIOLET_LINE, zerolinecolor=VIOLET_LINE)
    return fig
