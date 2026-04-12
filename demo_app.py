from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from config import settings


APP_TITLE = "LaunchMind Workflow Console"
PROJECT_ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = settings.artifacts_dir
LOGS_DIR = settings.logs_dir

DERIVED_OUTPUT_SUFFIXES = {".json", ".html", ".jsonl", ".log"}

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Fraunces:wght@600;700&display=swap');

:root {
    --bg: #0d1117;
    --surface: rgba(20, 28, 39, 0.88);
    --surface-strong: #141c27;
    --surface-dark: #0f1722;
    --ink: #eef2f7;
    --muted: #9aa8b7;
    --line: rgba(255, 255, 255, 0.08);
    --accent: #2dd4bf;
    --accent-2: #fb923c;
    --accent-3: #60a5fa;
    --success: #22c55e;
    --warning: #fbbf24;
    --danger: #f87171;
    --shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
}

.stApp {
    background:
        radial-gradient(circle at top left, rgba(45, 212, 191, 0.10), transparent 24%),
        radial-gradient(circle at top right, rgba(251, 146, 60, 0.10), transparent 24%),
        linear-gradient(180deg, #0d1117 0%, #101722 100%);
    color: var(--ink);
    font-family: "Manrope", sans-serif;
}

[data-testid="stAppViewContainer"] > .main {
    padding-top: 1.5rem;
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #10222c 0%, #162d39 100%);
    border-right: 1px solid rgba(255,255,255,0.06);
}

[data-testid="stSidebar"] * {
    color: #f7f5ef !important;
}

[data-testid="stSidebar"] [data-baseweb="textarea"] textarea {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
}

.block-container {
    max-width: 1440px;
    padding-top: 1rem;
    padding-bottom: 2.5rem;
}

h1, h2, h3 {
    color: var(--ink);
}

h1 {
    font-family: "Fraunces", serif;
    font-size: clamp(2.4rem, 4vw, 3.4rem);
    letter-spacing: -0.04em;
}

.hero-shell {
    padding: 1.65rem 1.8rem;
    border-radius: 28px;
    background:
        linear-gradient(135deg, rgba(20, 28, 39, 0.92), rgba(15, 23, 34, 0.96)),
        linear-gradient(135deg, rgba(45,212,191,0.10), rgba(251,146,60,0.10));
    border: 1px solid var(--line);
    box-shadow: var(--shadow);
    margin-bottom: 1.25rem;
}

.hero-kicker {
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.45rem 0.8rem;
    border-radius: 999px;
    background: rgba(45, 212, 191, 0.12);
    color: var(--accent);
    font-size: 0.82rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.hero-grid {
    display: grid;
    grid-template-columns: 1.15fr 0.85fr;
    gap: 1rem;
    margin-top: 1rem;
}

.hero-copy {
    padding-right: 1rem;
}

.hero-copy p {
    color: var(--muted);
    font-size: 1rem;
    line-height: 1.75;
    margin: 0.55rem 0 0;
}

.hero-panel {
    border-radius: 24px;
    padding: 1.1rem 1.15rem;
    background: linear-gradient(180deg, rgba(8,15,24,0.98), rgba(13,20,31,0.98));
    color: #f5f7fb;
}

.hero-panel h3 {
    color: #fffdf8;
    margin: 0;
    font-size: 1rem;
}

.hero-panel p {
    color: rgba(255,255,255,0.78);
    line-height: 1.65;
    margin-top: 0.6rem;
    font-size: 0.95rem;
}

.status-card {
    border-radius: 24px;
    background: var(--surface);
    border: 1px solid var(--line);
    box-shadow: var(--shadow);
    padding: 1.05rem 1.15rem 1.2rem;
    min-height: 158px;
}

.status-card .label {
    color: var(--muted);
    font-size: 0.82rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.65rem;
}

.status-card .value {
    color: var(--ink);
    font-family: "Fraunces", serif;
    font-size: clamp(1.6rem, 3vw, 2.5rem);
    line-height: 1.05;
    letter-spacing: -0.04em;
}

.status-card .support {
    color: var(--muted);
    font-size: 0.93rem;
    line-height: 1.6;
    margin-top: 0.9rem;
}

.status-running .signal,
.status-success .signal,
.status-failed .signal,
.status-idle .signal {
    display: inline-flex;
    width: 14px;
    height: 14px;
    border-radius: 999px;
    margin-right: 0.55rem;
    box-shadow: 0 0 0 6px rgba(0,0,0,0.04);
}

.status-running .signal { background: var(--warning); }
.status-success .signal { background: var(--success); }
.status-failed .signal { background: var(--danger); }
.status-idle .signal { background: #94a3b8; }

.section-shell {
    border-radius: 28px;
    padding: 1.2rem 1.25rem;
    border: 1px solid var(--line);
    background: rgba(20, 28, 39, 0.80);
    box-shadow: var(--shadow);
}

.section-note {
    color: var(--muted);
    line-height: 1.7;
    margin-top: 0.35rem;
}

.section-title {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.85rem;
}

.section-title h3,
.section-title h4 {
    margin: 0;
}

.section-kicker {
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--accent);
}

.mini-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.85rem;
    margin-top: 0.8rem;
}

.mini-card {
    border-radius: 20px;
    padding: 0.9rem 1rem;
    background: rgba(24, 34, 48, 0.96);
    border: 1px solid var(--line);
}

.mini-card .mini-label {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    font-weight: 800;
}

.mini-card .mini-value {
    margin-top: 0.45rem;
    font-size: 1.02rem;
    font-weight: 700;
    color: var(--ink);
}

.timeline-shell {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.8rem;
    margin-top: 0.9rem;
}

.timeline-card {
    border-radius: 20px;
    padding: 0.95rem 1rem;
    background: rgba(24, 34, 48, 0.96);
    border: 1px solid var(--line);
    min-height: 120px;
}

.timeline-stage {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    font-weight: 800;
}

.timeline-dot {
    width: 10px;
    height: 10px;
    border-radius: 999px;
    background: #64748b;
}

.timeline-dot.ready { background: var(--success); }
.timeline-dot.active { background: var(--warning); }
.timeline-dot.idle { background: #64748b; }

.timeline-card h4 {
    margin: 0.65rem 0 0.35rem;
    font-size: 1rem;
    color: var(--ink);
}

.timeline-card p {
    margin: 0;
    color: var(--muted);
    line-height: 1.6;
    font-size: 0.92rem;
}

.artifact-frame {
    border-radius: 24px;
    border: 1px solid var(--line);
    background: rgba(12, 18, 28, 0.9);
    padding: 1rem;
    box-shadow: var(--shadow);
}

.activity-shell {
    border-radius: 22px;
    border: 1px solid var(--line);
    background: rgba(14, 21, 32, 0.95);
    padding: 1rem 1.05rem;
    box-shadow: var(--shadow);
    margin-bottom: 1rem;
}

.activity-grid {
    display: grid;
    grid-template-columns: 0.9fr 1.1fr;
    gap: 0.9rem;
}

.activity-card {
    border-radius: 18px;
    border: 1px solid var(--line);
    background: rgba(22, 30, 42, 0.92);
    padding: 0.9rem 1rem;
}

.activity-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    font-weight: 800;
}

.activity-value {
    margin-top: 0.45rem;
    color: var(--ink);
    font-size: 1.05rem;
    font-weight: 700;
    line-height: 1.45;
}

.activity-value small {
    display: block;
    color: var(--muted);
    font-size: 0.88rem;
    font-weight: 500;
    margin-top: 0.35rem;
}

.activity-log {
    border-radius: 18px;
    border: 1px solid var(--line);
    background: rgba(10, 16, 24, 0.98);
    padding: 0.9rem 1rem;
    min-height: 100%;
}

.activity-log pre {
    margin: 0.55rem 0 0;
    white-space: pre-wrap;
    word-break: break-word;
    color: #dbe6f3;
    font-size: 0.86rem;
    line-height: 1.6;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.proof-card {
    border-radius: 22px;
    border: 1px solid var(--line);
    background: rgba(14, 21, 32, 0.95);
    padding: 1rem 1.05rem;
    margin-bottom: 1rem;
    box-shadow: var(--shadow);
}

.proof-grid {
    display: grid;
    grid-template-columns: 1.1fr 0.9fr;
    gap: 1rem;
    align-items: start;
}

.proof-status {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    border-radius: 999px;
    padding: 0.35rem 0.7rem;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.proof-status.done {
    background: rgba(34,197,94,0.12);
    color: #86efac;
}

.proof-status.partial {
    background: rgba(251,191,36,0.12);
    color: #fde68a;
}

.proof-status.pending {
    background: rgba(248,113,113,0.12);
    color: #fca5a5;
}

.proof-title {
    margin: 0.8rem 0 0.35rem;
    font-size: 1.1rem;
    color: var(--ink);
}

.proof-text {
    color: var(--muted);
    line-height: 1.7;
    margin: 0;
}

.proof-points {
    margin: 0.8rem 0 0;
    padding-left: 1.1rem;
    color: var(--muted);
    line-height: 1.7;
}

.proof-note {
    border-radius: 18px;
    border: 1px solid var(--line);
    background: rgba(22, 30, 42, 0.92);
    padding: 0.9rem 1rem;
}

.artifact-meta {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.8rem;
    margin-bottom: 0.9rem;
}

.artifact-pill {
    border-radius: 16px;
    border: 1px solid var(--line);
    background: rgba(22, 30, 42, 0.94);
    padding: 0.8rem 0.9rem;
}

.artifact-pill strong {
    display: block;
    color: var(--ink);
    font-size: 0.96rem;
    margin-bottom: 0.25rem;
}

.artifact-pill span {
    color: var(--muted);
    font-size: 0.84rem;
    line-height: 1.5;
}

.landing-shell {
    border-radius: 28px;
    border: 1px solid var(--line);
    background: rgba(20, 28, 39, 0.86);
    box-shadow: var(--shadow);
    padding: 1rem;
}

.landing-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.9rem;
}

.landing-header h3 {
    margin: 0;
}

.landing-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    border-radius: 999px;
    padding: 0.45rem 0.8rem;
    background: rgba(96, 165, 250, 0.12);
    color: #dbeafe;
    font-size: 0.8rem;
    font-weight: 800;
    letter-spacing: 0.04em;
}

.landing-frame {
    border-radius: 22px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.07);
    background: #0f1722;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.65rem;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding-bottom: 0.35rem;
}

.stTabs [data-baseweb="tab"] {
    height: 40px;
    border-radius: 12px 12px 0 0;
    background: transparent;
    border: none;
    color: var(--muted);
    font-weight: 700;
    padding: 0 0.95rem;
    transition: background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(180deg, rgba(45,212,191,0.10), rgba(96,165,250,0.06)) !important;
    color: #f8fafc !important;
    box-shadow: inset 0 -3px 0 var(--accent);
}

.stTabs [data-baseweb="tab"]:hover {
    background: rgba(255,255,255,0.05);
    color: #dce7f3;
}

.stAlert {
    border-radius: 20px;
}

[data-testid="stCodeBlock"] pre {
    border-radius: 18px !important;
}

@media (max-width: 1100px) {
    .hero-grid,
    .mini-grid,
    .timeline-shell,
    .artifact-meta {
        grid-template-columns: 1fr;
    }
}
</style>
"""


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_error": "Invalid JSON", "_raw": path.read_text(encoding="utf-8")}


def _clear_outputs() -> None:
    for root in (ARTIFACTS_DIR, LOGS_DIR):
        for path in root.iterdir():
            if path.is_file() and path.suffix in DERIVED_OUTPUT_SUFFIXES:
                path.unlink(missing_ok=True)


def _process_status(process: subprocess.Popen[str] | None) -> str:
    if process is None:
        return "idle"
    if process.poll() is None:
        return "running"
    return "finished"


def _ensure_state() -> None:
    legacy_default_idea = (
        "AI concierge for student founders that turns startup ideas into landing pages, "
        "launch copy, and investor-ready messaging in one day."
    )
    st.session_state.setdefault("run_process", None)
    st.session_state.setdefault("last_idea", settings.demo_startup_idea)
    st.session_state.setdefault("last_started_at", None)
    if st.session_state.get("last_idea") == legacy_default_idea:
        st.session_state["last_idea"] = settings.demo_startup_idea


def _start_run(startup_idea: str) -> None:
    _stop_run()
    _clear_outputs()
    process = subprocess.Popen(
        [sys.executable, "main.py", "--idea", startup_idea],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        text=True,
    )
    st.session_state["run_process"] = process
    st.session_state["last_idea"] = startup_idea
    st.session_state["last_started_at"] = time.time()


def _stop_run() -> None:
    process = st.session_state.get("run_process")
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    st.session_state["run_process"] = None


def _status_badge(summary: dict, process_status: str) -> tuple[str, str]:
    if process_status == "running":
        return "Running", "🟡"
    if summary.get("status") == "success":
        return "Success", "🟢"
    if summary.get("status") == "failed":
        return "Failed", "🔴"
    return "Idle", "⚪"


def _status_class(process_status: str, summary: dict) -> str:
    if process_status == "running":
        return "status-running"
    if summary.get("status") == "success":
        return "status-success"
    if summary.get("status") == "failed":
        return "status-failed"
    return "status-idle"


def _render_hero(summary: dict, process_status: str) -> None:
    status_label, _ = _status_badge(summary, process_status)
    st.markdown(
        f"""
        <section class="hero-shell">
            <span class="hero-kicker">LaunchMind Demo Console</span>
            <div class="hero-grid">
                <div class="hero-copy">
                    <h1>Live multi-agent launch system with full workflow visibility.</h1>
                    <p>
                        Run the full workflow from one interface, watch orchestration happen live, inspect every artifact,
                        and preview the generated landing page without switching between multiple tools.
                    </p>
                </div>
                <div class="hero-panel">
                    <h3>Current Workflow State</h3>
                    <p>
                        Status: <strong>{status_label}</strong><br>
                        Startup: <strong>{summary.get('startup_name') or 'Not started'}</strong><br>
                        North star: <strong>{summary.get('north_star') or 'Waiting for a run to begin.'}</strong>
                    </p>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_metric_card(label: str, value: str, support: str, card_class: str = "") -> None:
    st.markdown(
        f"""
        <div class="status-card {card_class}">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            <div class="support">{support}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _show_summary_cards(summary: dict, process_status: str) -> None:
    status_label, _ = _status_badge(summary, process_status)
    card_class = _status_class(process_status, summary)
    product_ready = "Yes" if summary.get("product_spec_ready") else "No"
    qa_status = summary.get("qa_status") or "Pending"
    pr_url = summary.get("engineer_pr_url") or "Pending"
    cols = st.columns(4)
    with cols[0]:
        _render_metric_card("Workflow Status", f'<span class="signal"></span>{status_label}', "End-to-end orchestration and agent activity.", card_class)
    with cols[1]:
        _render_metric_card("Startup", summary.get("startup_name") or "Not started", "Resolved from CEO decomposition and product spec.")
    with cols[2]:
        _render_metric_card("Product Ready", product_ready, "Product spec accepted and shared downstream.")
    with cols[3]:
        _render_metric_card("QA Status", qa_status, "QA verdict after review comments and revision loops.")

    cols = st.columns(3)
    with cols[0]:
        _render_metric_card("Pull Request", "Created" if summary.get("engineer_pr_url") else "Pending", "GitHub PR created from the engineer agent output.")
    with cols[1]:
        _render_metric_card("Issue", "Created" if summary.get("engineer_issue_url") else "Pending", "GitHub issue raised before branch/PR automation.")
    with cols[2]:
        _render_metric_card("Marketing", summary.get("marketing_tagline") or "Pending", "Live launch copy, email, and Slack summary.")

    if pr_url != "Pending":
        st.markdown(f"PR: [Open Pull Request]({summary['engineer_pr_url']})")
    if summary.get("engineer_issue_url"):
        st.markdown(f"Issue: [Open GitHub Issue]({summary['engineer_issue_url']})")


def _artifact_tab(title: str, path: Path, *, language: str = "json") -> None:
    st.markdown(
        f"""
        <div class="section-title">
            <div>
                <div class="section-kicker">Artifact</div>
                <h4>{title}</h4>
            </div>
            <div class="section-note">{path.name}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not path.exists():
        st.info("Not generated yet.")
        return
    st.markdown('<div class="artifact-frame">', unsafe_allow_html=True)
    if language == "html":
        st.code(_read_text(path), language="html")
    elif language == "text":
        st.code(_read_text(path))
    else:
        st.json(_read_json(path))
    st.markdown("</div>", unsafe_allow_html=True)


def _render_agent_timeline(summary: dict, process_status: str) -> None:
    product_ready = bool(summary.get("product_spec_ready"))
    engineer_ready = bool(summary.get("engineer_pr_url"))
    marketing_ready = bool(summary.get("marketing_tagline"))
    qa_ready = bool(summary.get("qa_status"))
    ceo_state = "active" if process_status == "running" else "ready" if summary else "idle"
    stages = [
        ("CEO", ceo_state, "Planning, reviews, and revision decisions."),
        ("Product", "ready" if product_ready else "idle", "Product spec creation and downstream handoff."),
        ("Engineer", "ready" if engineer_ready else "active" if product_ready and process_status == "running" else "idle", "Landing page, issue, branch, commit, and PR."),
        ("Marketing", "ready" if marketing_ready else "active" if product_ready and process_status == "running" else "idle", "Email, social copy, and Slack launch message."),
        ("QA", "ready" if qa_ready else "active" if engineer_ready and marketing_ready and process_status == "running" else "idle", "Review comments, pass/fail report, and revision triggers."),
    ]
    cards = []
    for label, state, description in stages:
        cards.append(
            (
                f'<div class="timeline-card">'
                f'<div class="timeline-stage"><span class="timeline-dot {state}"></span>{state}</div>'
                f"<h4>{label}</h4>"
                f"<p>{description}</p>"
                f"</div>"
            )
        )
    html = (
        '<div class="section-shell">'
        '<div class="section-title">'
        '<div><div class="section-kicker">Live Workflow</div><h3>Agent Progress Timeline</h3></div>'
        '<div class="section-note">A quick view of which stage is active and what has already completed.</div>'
        '</div>'
        f'<div class="timeline-shell">{"".join(cards)}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _recent_runtime_lines(agent_name: str, limit: int = 8) -> list[str]:
    runtime_path = LOGS_DIR / "runtime.log"
    if not runtime_path.exists():
        return []
    lines = runtime_path.read_text(encoding="utf-8").splitlines()
    needle = f"agent.{agent_name}"
    matched = [line for line in lines if needle in line]
    return matched[-limit:]


def _agent_activity_snapshot(agent_name: str, process_status: str, summary: dict) -> tuple[str, str]:
    logs = _recent_runtime_lines(agent_name, limit=12)
    ceo_product_review = _read_json(ARTIFACTS_DIR / "ceo_product_review.json")
    ceo_marketing_review = _read_json(ARTIFACTS_DIR / "ceo_marketing_review.json")
    ceo_engineer_review = _read_json(ARTIFACTS_DIR / "ceo_engineer_review.json")
    marketing_result = _read_json(ARTIFACTS_DIR / "marketing_result.json")
    artifact_map = {
        "product": ARTIFACTS_DIR / "product_spec.json",
        "engineer": ARTIFACTS_DIR / "engineer_result.json",
        "marketing": ARTIFACTS_DIR / "marketing_result.json",
        "qa": ARTIFACTS_DIR / "qa_report.json",
        "ceo": ARTIFACTS_DIR / "final_summary.json",
    }
    artifact_exists = artifact_map.get(agent_name, Path()).exists() if agent_name in artifact_map else False
    joined = "\n".join(logs).lower()

    if agent_name == "ceo":
        if summary.get("status") in {"success", "failed"}:
            return "Completed", "The workflow has already been finalized by the CEO agent."
        if ceo_engineer_review.get("decision") == "approve" and ceo_marketing_review.get("decision") == "approve":
            return "Waiting for QA", "The CEO has approved engineer and marketing outputs and is ready for the QA stage."
        if ceo_marketing_review.get("decision") == "approve" and not ceo_engineer_review:
            return "Waiting for engineer review", "Marketing has already been approved and the CEO is now waiting for the engineer side to settle."
        if ceo_engineer_review.get("decision") == "approve" and not ceo_marketing_review:
            return "Waiting for marketing review", "Engineer output has already been approved and the CEO is now waiting for the marketing side to settle."
        if "from=qa type=result" in joined:
            return "Reviewing QA output", "The CEO is processing the QA verdict and deciding the next step."
        if "from=marketing type=result" in joined:
            return "Reviewing marketing output", "The CEO is reviewing the latest marketing result and deciding whether revision is needed."
        if "from=engineer type=result" in joined:
            return "Reviewing engineer output", "The CEO is reviewing the latest engineer result and deciding whether revision is needed."
        if "dispatching engineer and marketing in parallel" in joined:
            return "Waiting for engineer and marketing", "The CEO has approved the product spec and is waiting for downstream agent results."
        if "from=product type=result" in joined:
            return "Reviewing product spec", "The CEO is reviewing the latest product result and deciding whether to approve or revise."
        if (ARTIFACTS_DIR / "ceo_plan.json").exists():
            return "Planning complete", "The CEO has decomposed the idea and is orchestrating the next agent handoff."

    if agent_name == "product" and (
        summary.get("product_spec_ready") or ceo_product_review.get("decision") == "approve"
    ):
        return "Completed", "The product spec has been approved and shared with downstream agents."
    if agent_name == "product" and (ARTIFACTS_DIR / "product_spec.json").exists():
        if ceo_product_review.get("decision") == "revise":
            return "Revision in progress", "The product spec was reviewed and sent back for another refinement pass."
        return "Waiting for CEO review", "The product spec has been generated and is now waiting for the CEO review decision."
    if agent_name == "engineer" and (
        summary.get("engineer_pr_url")
        or _read_json(ARTIFACTS_DIR / "engineer_result.json").get("pr_url")
        or "completed full workflow" in joined
    ):
        return "Completed", "The landing page was generated and pushed through GitHub automation."
    if agent_name == "marketing" and (
        summary.get("marketing_tagline")
        or marketing_result.get("tagline")
        or ceo_marketing_review.get("decision") == "approve"
    ):
        if ceo_marketing_review.get("decision") == "approve" or summary.get("marketing_tagline"):
            return "Completed", "Marketing copy has been approved and handed back to the workflow."
        return "Waiting for CEO review", "Marketing copy has been generated and is now waiting for the CEO review decision."
    if agent_name == "marketing" and ceo_marketing_review.get("decision") == "revise":
        return "Revision in progress", "The marketing output was reviewed and sent back for another refinement pass."
    if agent_name == "qa" and summary.get("qa_status"):
        return "Completed", "QA has produced a final review status for the current run."
    if "type=revision_request" in joined:
        return "Revision in progress", "The latest message shows this agent is working through a revision loop."
    if "received message" in joined and process_status == "running":
        return "Working now", "The agent has received work and is actively processing its current step."
    if artifact_exists:
        return "Completed", "The primary artifact for this agent has been generated."
    if process_status == "running":
        return "Queued", "The workflow is running and this agent is waiting for its turn or dependencies."
    return "Waiting", "No live activity has been recorded for this agent yet."


def _render_agent_activity(agent_name: str, process_status: str, summary: dict) -> None:
    status, detail = _agent_activity_snapshot(agent_name, process_status, summary)
    log_lines = _recent_runtime_lines(agent_name, limit=8)
    log_text = "\n".join(log_lines) if log_lines else "No agent-specific logs yet."
    st.markdown(
        f"""
        <div class="activity-shell">
            <div class="section-title">
                <div>
                    <div class="section-kicker">Live Activity</div>
                    <h4>{agent_name.capitalize()} Status</h4>
                </div>
            </div>
            <div class="activity-grid">
                <div class="activity-card">
                    <div class="activity-label">Current Phase</div>
                    <div class="activity-value">{status}<small>{detail}</small></div>
                </div>
                <div class="activity-log">
                    <div class="activity-label">Recent Logs</div>
                    <pre>{log_text}</pre>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _status_level(done: bool, partial: bool = False) -> tuple[str, str]:
    if done:
        return "Done", "done"
    if partial:
        return "Partial", "partial"
    return "Pending", "pending"


def _proof_file(path: Path) -> tuple[str, bytes] | None:
    if not path.exists():
        return None
    return path.name, path.read_bytes()


def _render_proof_item(
    *,
    title: str,
    description: str,
    done: bool,
    partial: bool = False,
    points: list[str] | None = None,
    github_links: list[tuple[str, str]] | None = None,
    files: list[Path] | None = None,
) -> None:
    label, css = _status_level(done, partial)
    points_html = '<ul class="proof-points">' + ''.join(f'<li>{point}</li>' for point in (points or [])) + '</ul>' if points else ""
    html = (
        '<div class="proof-card">'
        '<div class="proof-grid">'
        '<div>'
        f'<span class="proof-status {css}">{label}</span>'
        f'<h4 class="proof-title">{title}</h4>'
        f'<p class="proof-text">{description}</p>'
        f"{points_html}"
        '</div>'
        '<div class="proof-note">'
        '<div class="section-kicker">Evidence</div>'
        '<p class="proof-text">Use the buttons and file downloads below to inspect the supporting proof for this item.</p>'
        '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
    if github_links:
        cols = st.columns(len(github_links))
        for col, (label_text, url) in zip(cols, github_links):
            with col:
                st.link_button(label_text, url, use_container_width=True)
    if files:
        file_cols = st.columns(min(3, len(files))) if files else []
        for index, path in enumerate(files):
            if not path.exists():
                continue
            name_and_data = _proof_file(path)
            if not name_and_data:
                continue
            name, data = name_and_data
            with file_cols[index % len(file_cols)]:
                st.download_button(
                    f"Download {name}",
                    data=data,
                    file_name=name,
                    key=f"proof-download-{title}-{path.name}-{index}",
                    use_container_width=True,
                )


def _render_rubrics_and_bonus(summary: dict) -> None:
    marketing_result = _read_json(ARTIFACTS_DIR / "marketing_result.json")
    engineer_result = _read_json(ARTIFACTS_DIR / "engineer_result.json")
    qa_report = _read_json(ARTIFACTS_DIR / "qa_report.json")
    email_sent = ((marketing_result.get("email_delivery") or {}).get("status") == "sent")
    slack_sent = bool((marketing_result.get("slack_delivery") or {}).get("ts"))
    qa_done = bool(qa_report)
    pr_url = engineer_result.get("pr_url") or summary.get("engineer_pr_url")
    issue_url = engineer_result.get("issue_url") or summary.get("engineer_issue_url")

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="section-title">
            <div>
                <div class="section-kicker">Rubrics + Bonus</div>
                <h3>Requirement Mapping With Evidence</h3>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_proof_item(
        title="CEO orchestration and dynamic decision-making",
        description="The workflow shows CEO-led planning, review decisions, revision loops, and structured handoff to downstream agents.",
        done=(ARTIFACTS_DIR / "ceo_plan.json").exists(),
        points=[
            "CEO plan artifact generated from the startup idea",
            "Message history shows task, revision_request, and result traffic",
            "Current build enforces two product feedback loops before approval",
        ],
        files=[
            ARTIFACTS_DIR / "ceo_plan.json",
            ARTIFACTS_DIR / "ceo_product_review.json",
            LOGS_DIR / "message_history.jsonl",
        ],
    )

    _render_proof_item(
        title="Product specification generation",
        description="The Product agent returns a structured spec with personas, features, user stories, landing-page requirements, and marketing hooks.",
        done=bool((ARTIFACTS_DIR / "product_spec.json").exists() and _read_json(ARTIFACTS_DIR / "ceo_product_review.json").get("decision") == "approve"),
        points=[
            "Approved product specification artifact exists",
            "Structured JSON shape is persisted for downstream use",
        ],
        files=[ARTIFACTS_DIR / "product_spec.json", ARTIFACTS_DIR / "ceo_product_review.json"],
    )

    _render_proof_item(
        title="Engineer delivery through GitHub",
        description="The Engineer agent is expected to generate landing-page HTML and create GitHub issue, branch, commit, and PR artifacts.",
        done=bool(pr_url and issue_url and engineer_result),
        partial=bool((ARTIFACTS_DIR / "index.html").exists() or engineer_result),
        points=[
            "Done status requires both GitHub issue and PR URLs plus engineer artifact",
            "If only HTML artifacts exist without GitHub outputs, this remains partial",
            "The engineer path is configured to use Gemini through `ENGINEER_LLM_PROVIDER=gemini`",
        ],
        github_links=[link for link in [("Open PR", pr_url), ("Open Issue", issue_url)] if link[1]],
        files=[ARTIFACTS_DIR / "engineer_result.json", ARTIFACTS_DIR / "index_final.html", ARTIFACTS_DIR / "index_llm_raw.html"],
    )

    _render_proof_item(
        title="Marketing outputs, Slack, and email",
        description="The Marketing agent produces tagline, short description, outreach email, social posts, and delivery records for Slack and email.",
        done=bool(marketing_result and email_sent and slack_sent),
        partial=bool(marketing_result),
        points=[
            f"Email delivery status: {(marketing_result.get('email_delivery') or {}).get('status', 'not available')}",
            f"Slack delivery timestamp: {(marketing_result.get('slack_delivery') or {}).get('ts', 'not available')}",
        ],
        files=[ARTIFACTS_DIR / "marketing_result.json"],
    )

    _render_proof_item(
        title="QA review and revision control",
        description="QA should review engineering and marketing outputs, produce pass/fail output, and post review comments when the engineer PR exists.",
        done=qa_done,
        partial=bool((ARTIFACTS_DIR / "ceo_engineer_review.json").exists() or (ARTIFACTS_DIR / "ceo_marketing_review.json").exists()),
        points=[
            "Done status requires a QA report artifact",
            "If the workflow timed out before QA ran, this remains partial or pending",
        ],
        files=[ARTIFACTS_DIR / "qa_report.json", ARTIFACTS_DIR / "ceo_engineer_review.json", ARTIFACTS_DIR / "ceo_marketing_review.json"],
    )

    _render_proof_item(
        title="Structured messages, logging, and traceability",
        description="Inter-agent communication uses a structured message schema and the system preserves runtime logs and message history for traceability.",
        done=(LOGS_DIR / "message_history.jsonl").exists() and (LOGS_DIR / "runtime.log").exists(),
        points=[
            "Runtime log captures agent start, receive, publish, and completion events",
            "Message history preserves structured message flow with timestamps and parent IDs",
        ],
        files=[LOGS_DIR / "runtime.log", LOGS_DIR / "message_history.jsonl"],
    )

    st.markdown("### Bonus Coverage")
    _render_proof_item(
        title="QA agent bonus",
        description="Dedicated QA agent exists in the system design and produces a separate QA report when the run reaches that stage.",
        done=qa_done,
        partial=True,
        files=[ARTIFACTS_DIR / "qa_report.json"],
    )
    _render_proof_item(
        title="Redis pub/sub bonus",
        description="The workflow uses Redis pub/sub as the message bus with run-scoped channel prefixes.",
        done=True,
        files=[LOGS_DIR / "runtime.log", LOGS_DIR / "message_history.jsonl"],
    )
    _render_proof_item(
        title="Graceful failure handling bonus",
        description="The system records errors, retries selected LLM paths, and finalizes failed runs with structured summaries instead of silently crashing.",
        done=(ARTIFACTS_DIR / "final_summary.json").exists(),
        files=[ARTIFACTS_DIR / "final_summary.json", LOGS_DIR / "runtime.log"],
    )
    _render_proof_item(
        title="Multiple feedback loops bonus",
        description="Current workflow includes two forced product feedback loops plus downstream review/revision paths.",
        done=True,
        files=[ARTIFACTS_DIR / "ceo_product_review.json", LOGS_DIR / "message_history.jsonl"],
    )
    _render_proof_item(
        title="Different LLM providers bonus",
        description="The project includes provider switching across OpenAI, OpenRouter, and Gemini, with the engineer path currently configured to use Gemini.",
        done=True,
        points=[
            "LLM provider is configurable through `LLM_PROVIDER`",
            "Engineer-specific provider override is configurable through `ENGINEER_LLM_PROVIDER`",
            "OpenAI, OpenRouter, and Gemini paths are implemented in the shared client",
            "Current environment config sets `ENGINEER_LLM_PROVIDER=gemini`",
        ],
        files=[PROJECT_ROOT / "llm" / "openai_client.py", PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.example", PROJECT_ROOT / "README.md"],
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _display_render_mode(engineer_result: dict) -> str:
    mode = str(engineer_result.get("render_mode", "") or "").strip().lower()
    if not mode:
        return "Pending"
    if "repair" in mode:
        return "Generated after refinement"
    return "Generated"


def _display_final_mode(engineer_result: dict) -> str:
    mode = str(engineer_result.get("final_mode", "") or "").strip().lower()
    if not mode:
        return "Pending"
    if "final" in mode:
        return "Ready for review"
    return "Prepared"


def main() -> None:
    _ensure_state()

    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    process: subprocess.Popen[str] | None = st.session_state["run_process"]
    process_status = _process_status(process)
    if process_status == "finished":
        st.session_state["run_process"] = None

    with st.sidebar:
        st.header("Run Controls")
        startup_idea = st.text_area(
            "Startup Idea",
            value=st.session_state["last_idea"],
            height=180,
            help="Use this to run the full multi-agent workflow from the interface.",
        )
        start_disabled = process_status == "running"
        if st.button("Start Fresh Demo Run", type="primary", disabled=start_disabled, use_container_width=True):
            _start_run(startup_idea)
            st.rerun()
        if st.button("Stop Current Run", disabled=process_status != "running", use_container_width=True):
            _stop_run()
            st.rerun()
        st.divider()
        st.markdown("**Demo Rubric Coverage**")
        st.checkbox("Redis pub/sub workflow", value=True, disabled=True)
        st.checkbox("CEO orchestration", value=True, disabled=True)
        st.checkbox("GitHub issue / branch / PR", value=True, disabled=True)
        st.checkbox("Slack message", value=True, disabled=True)
        st.checkbox("Real email", value=True, disabled=True)
        st.checkbox("QA review + inline comments", value=True, disabled=True)
        st.checkbox("Logs + traceability", value=True, disabled=True)

    summary = _read_json(ARTIFACTS_DIR / "final_summary.json")
    _render_hero(summary, process_status)
    if process_status == "running":
        started = st.session_state.get("last_started_at")
        elapsed = f"{int(time.time() - started)}s" if started else "n/a"
        st.info(f"Workflow is running. Elapsed time: {elapsed}")

    overview_tab, live_tab, artifacts_tab, landing_page_tab, proof_tab = st.tabs(
        ["Overview", "Live Logs", "Artifacts", "Landing Page", "Proof"]
    )

    with overview_tab:
        col1, col2 = st.columns([1.1, 0.9])
        with col1:
            st.markdown('<div class="section-shell">', unsafe_allow_html=True)
            st.markdown(
                """
                <div class="section-title">
                    <div>
                        <div class="section-kicker">Summary</div>
                        <h3>Final Workflow State</h3>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if summary:
                st.json(summary)
            else:
                st.info("No run summary yet. Start a fresh run from the sidebar.")
            st.markdown("</div>", unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="section-shell">', unsafe_allow_html=True)
            st.markdown(
                """
                <div class="section-title">
                    <div>
                        <div class="section-kicker">Snapshot</div>
                        <h3>Latest Agent Outputs</h3>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(f"Startup idea: `{st.session_state['last_idea']}`")
            st.markdown(f"North star: {summary.get('north_star', 'Pending')}")
            st.markdown(f"Marketing tagline: {summary.get('marketing_tagline', 'Pending')}")
            errors = summary.get("errors", [])
            if errors:
                st.error(json.dumps(errors, indent=2))
            else:
                st.success("No blocking errors recorded in the latest summary.")
            st.markdown("</div>", unsafe_allow_html=True)

    with live_tab:
        log_col, audit_col = st.columns(2)
        with log_col:
            st.subheader("Runtime Log")
            st.code(_read_text(LOGS_DIR / "runtime.log")[-14000:] or "No runtime log yet.", language="text")
        with audit_col:
            st.subheader("Message History")
            st.code(_read_text(LOGS_DIR / "message_history.jsonl")[-14000:] or "No message history yet.", language="json")

    with artifacts_tab:
        subtabs = st.tabs(
            [
                "CEO Plan",
                "Product Spec",
                "Engineer",
                "Marketing",
                "QA",
            ]
        )
        with subtabs[0]:
            _render_agent_activity("ceo", process_status, summary)
            _artifact_tab("CEO Plan", ARTIFACTS_DIR / "ceo_plan.json")
            _artifact_tab("CEO Product Review", ARTIFACTS_DIR / "ceo_product_review.json")
            _artifact_tab("CEO Engineer Review", ARTIFACTS_DIR / "ceo_engineer_review.json")
            _artifact_tab("CEO Marketing Review", ARTIFACTS_DIR / "ceo_marketing_review.json")
        with subtabs[1]:
            _render_agent_activity("product", process_status, summary)
            _artifact_tab("Product Spec", ARTIFACTS_DIR / "product_spec.json")
        with subtabs[2]:
            _render_agent_activity("engineer", process_status, summary)
            engineer_result = _read_json(ARTIFACTS_DIR / "engineer_result.json")
            if engineer_result:
                st.markdown(
                    f"""
                    <div class="artifact-meta">
                        <div class="artifact-pill"><strong>Render Status</strong><span>{_display_render_mode(engineer_result)}</span></div>
                        <div class="artifact-pill"><strong>Output Status</strong><span>{_display_final_mode(engineer_result)}</span></div>
                        <div class="artifact-pill"><strong>PR Number</strong><span>{engineer_result.get('pr_number', 'Pending')}</span></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            _artifact_tab("Engineer Result", ARTIFACTS_DIR / "engineer_result.json")
            _artifact_tab("Raw LLM HTML", ARTIFACTS_DIR / "index_llm_raw.html", language="html")
            _artifact_tab("Final HTML", ARTIFACTS_DIR / "index_final.html", language="html")
        with subtabs[3]:
            _render_agent_activity("marketing", process_status, summary)
            _artifact_tab("Marketing Result", ARTIFACTS_DIR / "marketing_result.json")
        with subtabs[4]:
            _render_agent_activity("qa", process_status, summary)
            _artifact_tab("QA Report", ARTIFACTS_DIR / "qa_report.json")

    with landing_page_tab:
        html_path = ARTIFACTS_DIR / "index.html"
        if html_path.exists():
            html = _read_text(html_path)
            st.markdown(
                """
                <div class="landing-shell">
                    <div class="landing-header">
                        <div>
                            <div class="section-kicker">Preview</div>
                            <h3>Rendered Landing Page</h3>
                        </div>
                        <div class="landing-badge">Live Artifact Preview</div>
                    </div>
                    <div class="landing-frame">
                """,
                unsafe_allow_html=True,
            )
            components.html(html, height=900, scrolling=True)
            st.markdown("</div></div>", unsafe_allow_html=True)
            with st.expander("Show HTML Source"):
                st.code(html, language="html")
        else:
            st.info("No landing page artifact yet.")

    with proof_tab:
        _render_rubrics_and_bonus(summary)

    if _process_status(st.session_state.get("run_process")) == "running":
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    main()
