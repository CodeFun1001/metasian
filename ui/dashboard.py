import sys
import os
import json
import time
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import gradio as gr

ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860")

_TASK_OPTIONS = [
    "easy_memory_leak",
    "medium_db_cascade",
    "hard_disk_corruption",
]

_TASK_META = {
    "easy_memory_leak":     {"label": "Easy · Memory Leak",         "icon": "🟢", "bugs": ["memory_leak"]},
    "medium_db_cascade":    {"label": "Medium · DB Cascade",        "icon": "🟡", "bugs": ["db_timeout", "api_cascade"]},
    "hard_disk_corruption": {"label": "Hard · Disk Corruption",     "icon": "🔴", "bugs": ["disk_failure", "data_corruption"]},
}

_BUG_TYPES = [
    "memory_leak",
    "db_timeout",
    "api_cascade",
    "disk_failure",
    "data_corruption",
]

_DEMO_STRATEGIES = {
    "easy_memory_leak": [
        ("read_logs",   {"service": "api-server"}),
        ("check_metrics", {}),
        ("diagnose",    {"bug_type": "memory_leak"}),
        ("deploy_fix",  {"fix_type": "memory_leak", "service": "api-server"}),
    ],
    "medium_db_cascade": [
        ("read_logs",   {"service": "db-proxy"}),
        ("check_metrics", {}),
        ("diagnose",    {"bug_type": "db_timeout"}),
        ("read_logs",   {"service": "api-gateway"}),
        ("diagnose",    {"bug_type": "api_cascade"}),
        ("deploy_fix",  {"fix_type": "db_timeout",   "service": "db-proxy"}),
        ("deploy_fix",  {"fix_type": "api_cascade",  "service": "api-gateway"}),
    ],
    "hard_disk_corruption": [
        ("read_logs",   {"service": "storage-node"}),
        ("check_metrics", {}),
        ("read_logs",   {"service": "db-primary"}),
        ("diagnose",    {"bug_type": "disk_failure"}),
        ("diagnose",    {"bug_type": "data_corruption"}),
        ("deploy_fix",  {"fix_type": "disk_failure",    "service": "storage-node"}),
        ("rollback",    {"service": "db-primary",       "to_version": "stable"}),
        ("deploy_fix",  {"fix_type": "data_corruption", "service": "db-primary"}),
    ],
}

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap');

:root {
    --bg-base:       #080c14;
    --bg-surface:    #0d1422;
    --bg-card:       #111827;
    --bg-card-alt:   #131d30;
    --border:        #1e2d45;
    --border-bright: #2a3f5f;
    --accent-blue:   #3b82f6;
    --accent-cyan:   #06b6d4;
    --accent-purple: #8b5cf6;
    --accent-green:  #10b981;
    --accent-amber:  #f59e0b;
    --accent-red:    #ef4444;
    --text-primary:  #e2e8f0;
    --text-secondary:#94a3b8;
    --text-muted:    #475569;
    --glow-blue:     0 0 20px rgba(59,130,246,0.15);
    --glow-green:    0 0 20px rgba(16,185,129,0.15);
    --radius-sm:     6px;
    --radius-md:     10px;
    --radius-lg:     14px;
    --mono: 'IBM Plex Mono', 'Fira Code', monospace;
    --sans: 'Space Grotesk', 'Inter', sans-serif;
}

/* ── GLOBAL RESET ── */
*, *::before, *::after { box-sizing: border-box; }

body,
.gradio-container,
.gradio-container > .main,
gradio-app {
    background: var(--bg-base) !important;
    color: var(--text-primary) !important;
    font-family: var(--sans) !important;
    min-height: 100vh;
}

/* kill default gradio chrome */
.gradio-container { padding: 0 !important; max-width: 100% !important; }
footer { display: none !important; }

/* ── HEADER ── */
.ms-header {
    background: linear-gradient(135deg, #080c14 0%, #0d1422 50%, #0a1020 100%);
    border-bottom: 1px solid var(--border);
    padding: 20px 32px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: relative;
    overflow: hidden;
}
.ms-header::before {
    content: '';
    position: absolute;
    top: -60px; left: -60px;
    width: 300px; height: 300px;
    background: radial-gradient(circle, rgba(59,130,246,0.08) 0%, transparent 70%);
    pointer-events: none;
}
.ms-header::after {
    content: '';
    position: absolute;
    bottom: -40px; right: 80px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(139,92,246,0.06) 0%, transparent 70%);
    pointer-events: none;
}
.ms-logo {
    display: flex;
    align-items: center;
    gap: 14px;
}
.ms-logo-icon {
    width: 40px; height: 40px;
    background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
    border-radius: var(--radius-md);
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
    box-shadow: 0 4px 16px rgba(59,130,246,0.3);
    flex-shrink: 0;
}
.ms-logo-text h1 {
    font-family: var(--sans);
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);
    margin: 0;
    letter-spacing: -0.3px;
}
.ms-logo-text p {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-muted);
    margin: 0;
    letter-spacing: 0.5px;
}
.ms-badges {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.ms-badge {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 20px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.ms-badge-blue  { background: rgba(59,130,246,0.12);  border: 1px solid rgba(59,130,246,0.3);  color: #60a5fa; }
.ms-badge-green { background: rgba(16,185,129,0.12);  border: 1px solid rgba(16,185,129,0.3);  color: #34d399; }
.ms-badge-purple{ background: rgba(139,92,246,0.12);  border: 1px solid rgba(139,92,246,0.3);  color: #a78bfa; }
.ms-live-dot {
    display: inline-block;
    width: 7px; height: 7px;
    background: var(--accent-green);
    border-radius: 50%;
    margin-right: 5px;
    animation: pulse-dot 2s ease-in-out infinite;
}
@keyframes pulse-dot {
    0%,100% { opacity: 1; transform: scale(1); }
    50%      { opacity: 0.5; transform: scale(0.85); }
}

/* ── TABS ── */
.tabs { background: transparent !important; }
.tab-nav {
    background: var(--bg-surface) !important;
    border-bottom: 1px solid var(--border) !important;
    padding: 0 32px !important;
    gap: 0 !important;
}
.tab-nav button {
    font-family: var(--sans) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: var(--text-muted) !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    padding: 14px 18px !important;
    margin: 0 !important;
    border-radius: 0 !important;
    transition: color 0.2s, border-color 0.2s !important;
}
.tab-nav button:hover {
    color: var(--text-secondary) !important;
    background: rgba(255,255,255,0.03) !important;
}
.tab-nav button.selected {
    color: var(--accent-blue) !important;
    border-bottom-color: var(--accent-blue) !important;
    background: transparent !important;
}

/* ── LAYOUT ── */
.ms-layout { padding: 24px 28px; gap: 20px; }
.ms-sidebar { gap: 14px; }

/* ── CARDS ── */
.ms-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 18px 20px;
    transition: border-color 0.2s;
}
.ms-card:hover { border-color: var(--border-bright); }
.ms-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
}
.ms-card-title {
    font-family: var(--sans);
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 0;
}
.ms-card-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--accent-blue);
    flex-shrink: 0;
}

/* ── SCORE DISPLAY ── */
.ms-score-ring {
    text-align: center;
    padding: 16px 0 8px;
}
.ms-score-value {
    font-family: var(--mono);
    font-size: 48px;
    font-weight: 600;
    line-height: 1;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.ms-score-grade {
    font-family: var(--sans);
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 4px;
    letter-spacing: 1px;
    text-transform: uppercase;
}
.ms-score-bar-wrap {
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    margin: 10px 0 6px;
    overflow: hidden;
}
.ms-score-bar-fill {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple));
    transition: width 0.6s cubic-bezier(0.4,0,0.2,1);
}

/* ── METRIC PILLS ── */
.ms-metric-row {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.ms-metric-item {
    display: flex;
    align-items: center;
    gap: 10px;
}
.ms-metric-label {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-muted);
    width: 56px;
    flex-shrink: 0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.ms-metric-bar-wrap {
    flex: 1;
    height: 5px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
}
.ms-metric-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.4s ease;
}
.ms-metric-val {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-secondary);
    width: 62px;
    text-align: right;
    flex-shrink: 0;
}
.bar-normal  { background: linear-gradient(90deg, #10b981, #34d399); }
.bar-warn    { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.bar-crit    { background: linear-gradient(90deg, #ef4444, #f87171); }
.bar-blue    { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.bar-purple  { background: linear-gradient(90deg, #8b5cf6, #a78bfa); }

/* ── LOG STREAM ── */
.ms-log-wrap {
    font-family: var(--mono);
    font-size: 11.5px;
    line-height: 1.7;
    color: var(--text-secondary);
    max-height: 260px;
    overflow-y: auto;
    padding: 4px 0;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
}
.ms-log-wrap::-webkit-scrollbar { width: 4px; }
.ms-log-wrap::-webkit-scrollbar-track { background: transparent; }
.ms-log-wrap::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 2px; }
.log-crit  { color: #fca5a5; }
.log-error { color: #f87171; }
.log-warn  { color: #fcd34d; }
.log-info  { color: #6ee7b7; }
.log-env   { color: #93c5fd; }
.log-plain { color: var(--text-secondary); }

/* ── STATUS BADGE ── */
.ms-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}
.status-init    { background:rgba(59,130,246,0.12);  border:1px solid rgba(59,130,246,0.25);  color:#60a5fa; }
.status-running { background:rgba(245,158,11,0.12);  border:1px solid rgba(245,158,11,0.25);  color:#fcd34d; }
.status-success { background:rgba(16,185,129,0.12);  border:1px solid rgba(16,185,129,0.25);  color:#34d399; }
.status-fail    { background:rgba(239,68,68,0.12);   border:1px solid rgba(239,68,68,0.25);   color:#fca5a5; }
.status-idle    { background:rgba(71,85,105,0.15);   border:1px solid rgba(71,85,105,0.3);    color:#94a3b8; }

/* ── BUG CHIPS ── */
.ms-bug-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.ms-chip {
    font-family: var(--mono);
    font-size: 10px;
    padding: 3px 9px;
    border-radius: 4px;
    font-weight: 500;
}
.chip-diag   { background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.25); color:#fcd34d; }
.chip-fixed  { background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.25); color:#34d399; }
.chip-remain { background:rgba(239,68,68,0.10); border:1px solid rgba(239,68,68,0.2);  color:#fca5a5; }

/* ── AGENT LOG ── */
.ms-agentlog {
    font-family: var(--mono);
    font-size: 11px;
    line-height: 1.8;
    color: var(--text-secondary);
    max-height: 200px;
    overflow-y: auto;
    padding: 4px 0;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
}
.ms-agentlog::-webkit-scrollbar { width: 4px; }
.ms-agentlog::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 2px; }
.al-step    { color: var(--text-muted); }
.al-action  { color: #93c5fd; }
.al-reward  { color: #6ee7b7; }
.al-err     { color: #fca5a5; }
.al-sep     { color: var(--border-bright); }
.al-success { color: #34d399; font-weight: 600; }
.al-fail    { color: #f87171; font-weight: 600; }

/* ── FORM CONTROLS ── */
.gr-form, .gr-panel, .gr-box, .form {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    gap: 0 !important;
}

label, .label-wrap span {
    font-family: var(--sans) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.8px !important;
    margin-bottom: 6px !important;
}

.gr-dropdown, select,
textarea, input[type="text"] {
    background: var(--bg-base) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
    font-family: var(--mono) !important;
    font-size: 12px !important;
    padding: 8px 12px !important;
    transition: border-color 0.2s !important;
}
.gr-dropdown:focus, select:focus,
textarea:focus, input:focus {
    border-color: var(--accent-blue) !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.1) !important;
}

/* ── BUTTONS ── */
button.primary,
.gr-button-primary,
button[variant="primary"] {
    background: linear-gradient(135deg, #2563eb, #7c3aed) !important;
    border: none !important;
    color: #fff !important;
    font-family: var(--sans) !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 10px 22px !important;
    border-radius: var(--radius-sm) !important;
    cursor: pointer !important;
    letter-spacing: 0.3px !important;
    box-shadow: 0 4px 14px rgba(59,130,246,0.25) !important;
    transition: transform 0.15s, box-shadow 0.15s, opacity 0.15s !important;
    width: 100% !important;
}
button.primary:hover,
.gr-button-primary:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(59,130,246,0.35) !important;
}
button.primary:active,
.gr-button-primary:active {
    transform: translateY(0) !important;
}

button.secondary,
.gr-button-secondary,
button[variant="secondary"] {
    background: var(--bg-card-alt) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-secondary) !important;
    font-family: var(--sans) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 9px 18px !important;
    border-radius: var(--radius-sm) !important;
    transition: border-color 0.2s, background 0.2s !important;
    width: 100% !important;
}
button.secondary:hover,
.gr-button-secondary:hover {
    border-color: var(--accent-blue) !important;
    background: rgba(59,130,246,0.05) !important;
}

/* ── TEXTBOXES (hide default gradio textareas used as display) ── */
.gr-textbox { background: transparent !important; }
.gr-textbox textarea {
    background: var(--bg-base) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-family: var(--mono) !important;
    font-size: 11.5px !important;
    line-height: 1.7 !important;
    padding: 12px 14px !important;
    resize: none !important;
}

/* ── INFO CARDS ── */
.ms-info-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
}
.ms-info-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 16px;
}
.ms-info-card h3 {
    font-family: var(--sans);
    font-size: 12px;
    font-weight: 600;
    color: var(--accent-blue);
    margin: 0 0 10px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}
.ms-info-card p, .ms-info-card li {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-secondary);
    line-height: 1.7;
    margin: 2px 0;
}
.ms-info-card ul { padding-left: 16px; margin: 0; }
.ms-reward-table { width: 100%; border-collapse: collapse; }
.ms-reward-table th {
    font-family: var(--sans);
    font-size: 10px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
    text-align: left;
}
.ms-reward-table td {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-secondary);
    padding: 7px 8px;
    border-bottom: 1px solid rgba(30,45,69,0.5);
}
.ms-reward-table tr:last-child td { border-bottom: none; }
.rw-pos { color: #34d399; }
.rw-neg { color: #f87171; }

/* ── TASK SELECTOR PILLS ── */
.ms-task-pills { display: flex; flex-direction: column; gap: 8px; }
.ms-task-pill {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--bg-card-alt);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 10px 14px;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
    text-align: left;
    width: 100%;
}
.ms-task-pill:hover {
    border-color: var(--accent-blue);
    background: rgba(59,130,246,0.05);
}
.ms-task-pill-icon { font-size: 18px; flex-shrink: 0; }
.ms-task-pill-body {}
.ms-task-pill-name {
    font-family: var(--sans);
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    display: block;
}
.ms-task-pill-bugs {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-muted);
    display: block;
    margin-top: 1px;
}

/* hide gradio's own label for HTML components */
.gr-html label { display: none !important; }

/* divider */
.ms-divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 14px 0;
}

/* ── STAT BOXES ── */
.ms-stats-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 10px;
    margin-bottom: 14px;
}
.ms-stat {
    background: var(--bg-card-alt);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    text-align: center;
}
.ms-stat-val {
    font-family: var(--mono);
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary);
    display: block;
    line-height: 1;
}
.ms-stat-key {
    font-family: var(--sans);
    font-size: 9px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-top: 4px;
    display: block;
}

/* ── SCROLLBAR global ── */
* {
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
}
*::-webkit-scrollbar { width: 5px; height: 5px; }
*::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 3px; }
"""

def _api_reset(task_id: str, scenario_desc: str):
    payload = {}
    if scenario_desc and scenario_desc.strip():
        payload["scenario_description"] = scenario_desc.strip()
    else:
        payload["task_id"] = task_id
    try:
        r = requests.post(f"{ENV_BASE_URL}/reset", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def _api_step(action_type: str, parameters: dict):
    try:
        r = requests.post(
            f"{ENV_BASE_URL}/step",
            json={"action_type": action_type, "parameters": parameters},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def _api_grade():
    try:
        r = requests.get(f"{ENV_BASE_URL}/grade", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def _api_state():
    try:
        r = requests.get(f"{ENV_BASE_URL}/state", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def _render_score_html(score: float) -> str:
    pct = score * 100
    w = f"{pct:.1f}%"
    if score >= 0.9:
        grade, gcolor = "S",  "#34d399"
    elif score >= 0.7:
        grade, gcolor = "A",  "#60a5fa"
    elif score >= 0.5:
        grade, gcolor = "B",  "#a78bfa"
    elif score >= 0.3:
        grade, gcolor = "C",  "#fcd34d"
    else:
        grade, gcolor = "F",  "#f87171"

    bar_color = (
        "linear-gradient(90deg,#10b981,#34d399)" if score >= 0.7 else
        "linear-gradient(90deg,#f59e0b,#fbbf24)" if score >= 0.4 else
        "linear-gradient(90deg,#ef4444,#f87171)"
    )

    return f"""
    <div class="ms-card" style="text-align:center; padding:20px 16px;">
    <div class="ms-card-header" style="justify-content:center; border-bottom:none; margin-bottom:8px; padding-bottom:0;">
        <span class="ms-card-dot"></span>
        <span class="ms-card-title">Episode Score</span>
    </div>
    <div class="ms-score-value">{score:.4f}</div>
    <div class="ms-score-grade" style="color:{gcolor}; margin-top:6px;">Grade {grade} &nbsp;·&nbsp; {pct:.1f}%</div>
    <div class="ms-score-bar-wrap" style="margin:12px 0 4px;">
        <div class="ms-score-bar-fill" style="width:{w}; background:{bar_color};"></div>
    </div>
    </div>
    """

def _render_metrics_html(metrics: dict) -> str:
    if not metrics:
        return '<div class="ms-card"><p style="color:var(--text-muted);font-family:var(--mono);font-size:11px;">No data yet</p></div>'

    cpu  = metrics.get("cpu_percent",    0)
    mem  = metrics.get("memory_percent", 0)
    lat  = metrics.get("latency_ms",     0)
    err  = metrics.get("error_rate",     0)
    disk = metrics.get("disk_io_mbps",   0)

    def _bar_class(val, warn=60, crit=85):
        return "bar-crit" if val >= crit else "bar-warn" if val >= warn else "bar-normal"

    def _row(label, val_pct, display, color_class, width_pct=None):
        w = width_pct if width_pct is not None else val_pct
        w = max(0, min(100, w))
        return f"""
    <div class="ms-metric-item">
    <span class="ms-metric-label">{label}</span>
    <div class="ms-metric-bar-wrap">
        <div class="ms-metric-bar-fill {color_class}" style="width:{w:.1f}%"></div>
    </div>
    <span class="ms-metric-val">{display}</span>
    </div>"""

    lat_pct  = min(lat / 600, 100)
    err_pct  = err * 100
    disk_pct = min(disk / 2.0, 100)

    rows = (
        _row("CPU",    cpu,          f"{cpu:.1f}%",      _bar_class(cpu)) +
        _row("MEMORY", mem,          f"{mem:.1f}%",      _bar_class(mem, 70, 88)) +
        _row("LATENCY",lat_pct,      f"{lat:.0f}ms",     _bar_class(lat_pct, 40, 75)) +
        _row("ERRORS", err_pct,      f"{err:.3f}",       _bar_class(err_pct, 15, 40)) +
        _row("DISK IO",disk_pct,     f"{disk:.1f} MB/s", "bar-blue", disk_pct)
    )

    return f"""
    <div class="ms-card">
    <div class="ms-card-header">
        <span class="ms-card-dot" style="background:var(--accent-cyan)"></span>
        <span class="ms-card-title">System Metrics</span>
    </div>
    <div class="ms-metric-row">{rows}</div>
    </div>"""


def _render_logs_html(logs: list) -> str:
    if not logs:
        return '<div class="ms-card"><p style="color:var(--text-muted);font-family:var(--mono);font-size:11px;">No logs yet</p></div>'

    lines = []
    for line in logs:
        if "CRITICAL" in line:
            cls, prefix = "log-crit",  "CRIT"
        elif "ERROR" in line:
            cls, prefix = "log-error", "ERR "
        elif "WARN" in line:
            cls, prefix = "log-warn",  "WARN"
        elif "[ENV]" in line:
            cls, prefix = "log-env",   "ENV "
        elif "INFO" in line:
            cls, prefix = "log-info",  "INFO"
        else:
            cls, prefix = "log-plain", "    "
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f'<div class="{cls}"><span style="opacity:0.45">[{prefix}]</span> {safe}</div>')

    content = "\n".join(lines)
    return f"""
    <div class="ms-card">
    <div class="ms-card-header">
        <span class="ms-card-dot" style="background:var(--accent-amber)"></span>
        <span class="ms-card-title">Log Stream</span>
        <span style="margin-left:auto;font-family:var(--mono);font-size:9px;color:var(--text-muted);">{len(logs)} lines</span>
    </div>
    <div class="ms-log-wrap">{content}</div>
    </div>"""

def _render_state_html(state_text: str, status: str = "idle") -> str:
    status_map = {
        "idle":    ("IDLE",    "status-idle"),
        "init":    ("READY",   "status-init"),
        "running": ("RUNNING", "status-running"),
        "success": ("SUCCESS", "status-success"),
        "fail":    ("FAILED",  "status-fail"),
    }
    label, cls = status_map.get(status, ("IDLE", "status-idle"))
    dot = '<span class="ms-live-dot"></span>' if status == "running" else ""
    safe = state_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = safe.split("\n")
    formatted = "\n".join(
        f'<div style="line-height:1.7;font-family:var(--mono);font-size:11.5px;color:var(--text-secondary);">{l}</div>'
        for l in lines if l.strip()
    )
    return f"""
    <div class="ms-card">
    <div class="ms-card-header">
        <span class="ms-card-dot" style="background:var(--accent-purple)"></span>
        <span class="ms-card-title">Episode State</span>
        <span class="ms-status {cls}" style="margin-left:auto;">{dot}{label}</span>
    </div>
    <div style="padding: 4px 0;">{formatted}</div>
    </div>"""

def _render_agentlog_html(lines: list) -> str:
    if not lines:
        return '<div class="ms-card"><p style="color:var(--text-muted);font-family:var(--mono);font-size:11px;">Waiting for agent…</p></div>'

    html_lines = []
    for line in lines:
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if line.startswith("[INIT]"):
            html_lines.append(f'<div class="al-action">{safe}</div>')
        elif line.startswith("[STEP"):
            parts = safe.split("→")
            action_part = parts[0] if parts else safe
            reward_part = "→" + parts[1] if len(parts) > 1 else ""
            html_lines.append(
                f'<div><span class="al-step">{action_part}</span>'
                f'<span class="al-reward">{reward_part}</span></div>'
            )
        elif "ERROR" in line:
            html_lines.append(f'<div class="al-err">{safe}</div>')
        elif "====" in line:
            html_lines.append(f'<div class="al-sep">{"─" * 55}</div>')
        elif "SUCCESS" in line or "YES" in line:
            html_lines.append(f'<div class="al-success">{safe}</div>')
        elif "FAIL" in line or "NO" in line:
            html_lines.append(f'<div class="al-fail">{safe}</div>')
        else:
            html_lines.append(f'<div style="color:var(--text-secondary);font-family:var(--mono);font-size:11px;">{safe}</div>')

    content = "\n".join(html_lines)
    return f"""
    <div class="ms-card">
    <div class="ms-card-header">
        <span class="ms-card-dot" style="background:var(--accent-green)"></span>
        <span class="ms-card-title">Agent Action Log</span>
        <span style="margin-left:auto;font-family:var(--mono);font-size:9px;color:var(--text-muted);">{len(lines)} events</span>
    </div>
    <div class="ms-agentlog" id="agent-log-scroll">{content}</div>
    </div>
    <script>
    (function() {{
        var el = document.getElementById('agent-log-scroll');
        if (el) el.scrollTop = el.scrollHeight;
    }})();
    </script>"""

def _render_bugs_html(diagnosed: list, fixed: list, bug_types: list) -> str:
    chips = []
    for b in bug_types:
        if b in fixed:
            chips.append(f'<span class="ms-chip chip-fixed">✓ {b}</span>')
        elif b in diagnosed:
            chips.append(f'<span class="ms-chip chip-diag">◎ {b}</span>')
        else:
            chips.append(f'<span class="ms-chip chip-remain">? {b}</span>')
    content = "".join(chips) or "<span style='font-size:11px;color:var(--text-muted);font-family:var(--mono);'>Not started</span>"
    return f"""
    <div class="ms-card" style="padding:14px 18px;">
    <div class="ms-card-header" style="margin-bottom:10px;">
        <span class="ms-card-dot" style="background:var(--accent-amber)"></span>
        <span class="ms-card-title">Bug Status</span>
    </div>
    <div class="ms-bug-chips">{content}</div>
    </div>"""

EMPTY_SCORE   = _render_score_html(0.0001)
EMPTY_METRICS = _render_metrics_html({})
EMPTY_LOGS    = _render_logs_html([])
EMPTY_STATE   = _render_state_html("Waiting for reset…", "idle")
EMPTY_AGENT   = _render_agentlog_html([])
EMPTY_BUGS    = _render_bugs_html([], [], [])


def run_demo_agent(task_id: str, scenario_desc: str):
    log_lines = []

    obs = _api_reset(task_id, scenario_desc)
    if "error" in obs:
        yield (
            _render_state_html(f"ERROR: {obs['error']}", "fail"),
            EMPTY_METRICS, EMPTY_LOGS,
            _render_agentlog_html([f"[ERROR] {obs['error']}"]),
            _render_score_html(0.0001),
            EMPTY_BUGS,
        )
        return

    effective_task = obs.get("system_state", task_id)
    hint = obs.get("hint") or ""
    state_msg = f"Task initialized\n{effective_task}"
    if hint:
        state_msg += f"\n\nHINT: {hint}"

    log_lines.append(f"[INIT] Environment reset — task: {task_id}")

    yield (
        _render_state_html(state_msg, "init"),
        _render_metrics_html(obs.get("metrics", {})),
        _render_logs_html(obs.get("logs", [])),
        _render_agentlog_html(log_lines),
        _render_score_html(0.0001),
        EMPTY_BUGS,
    )

    # pick strategy
    if scenario_desc and scenario_desc.strip():
        state = _api_state()
        bug_types = state.get("bug_types", ["memory_leak"])
        actions = [("read_logs", {"service": "all"}), ("check_metrics", {})]
        for b in bug_types:
            actions.append(("diagnose", {"bug_type": b}))
        for b in bug_types:
            if b == "data_corruption":
                actions.append(("rollback", {"service": "db-primary", "to_version": "stable"}))
            actions.append(("deploy_fix", {"fix_type": b, "service": "target-service"}))
    else:
        bug_types = _TASK_META.get(task_id, {}).get("bugs", ["memory_leak"])
        actions = _DEMO_STRATEGIES.get(task_id, _DEMO_STRATEGIES["easy_memory_leak"])

    for step_num, (action_type, params) in enumerate(actions, 1):
        time.sleep(0.55)

        result = _api_step(action_type, params)
        if "error" in result:
            log_lines.append(f"[STEP {step_num:02d}] ERROR: {result['error']}")
            yield (
                _render_state_html(f"Step {step_num} error: {result['error']}", "fail"),
                EMPTY_METRICS, EMPTY_LOGS,
                _render_agentlog_html(log_lines),
                _render_score_html(0.0001),
                EMPTY_BUGS,
            )
            break

        reward  = result.get("reward", {})
        rv      = reward.get("value", 0)
        reason  = reward.get("reason", "")
        done    = result.get("done", False)
        info    = result.get("info", {})
        new_obs = result.get("observation", obs)
        diag    = info.get("diagnosed_bugs", [])
        fixed   = info.get("fixed_bugs", [])
        rem     = info.get("steps_remaining", 0)

        state_msg = (
            f"Step {step_num}  ·  {action_type.upper()}\n"
            f"Params:    {json.dumps(params)}\n"
            f"Reward:    {rv:.4f}\n"
            f"Reason:    {reason}\n"
            f"Diagnosed: {diag}\n"
            f"Fixed:     {fixed}\n"
            f"Remaining: {rem} steps"
        )

        log_lines.append(
            f"[STEP {step_num:02d}] {action_type}({json.dumps(params, separators=(',',':'))}) "
            f"→ reward={rv:.4f}  done={str(done).lower()}"
        )

        grade_data    = _api_grade()
        current_score = grade_data.get("score", 0.0001)

        yield (
            _render_state_html(state_msg, "running"),
            _render_metrics_html(new_obs.get("metrics", {})),
            _render_logs_html(new_obs.get("logs", [])),
            _render_agentlog_html(log_lines),
            _render_score_html(current_score),
            _render_bugs_html(diag, fixed, bug_types),
        )

        if done:
            break

    time.sleep(0.3)
    grade_data  = _api_grade()
    final_score = grade_data.get("score", 0.0001)
    success     = final_score >= 0.5
    diag        = grade_data.get("diagnosed_bugs", [])
    fixed_bugs  = grade_data.get("fixed_bugs", [])

    log_lines.append("")
    log_lines.append("=" * 55)
    log_lines.append(f"  EPISODE COMPLETE — Score: {final_score:.4f}")
    log_lines.append(f"  {'SUCCESS ✓' if success else 'FAILED ✗'}")
    log_lines.append(f"  Diagnosed: {diag}   Fixed: {fixed_bugs}")
    log_lines.append("=" * 55)

    final_state = (
        f"Episode complete\n"
        f"Final Score:  {final_score:.4f}\n"
        f"Result:       {'SUCCESS ✓' if success else 'FAILED ✗'}\n"
        f"Diagnosed:    {diag}\n"
        f"Fixed:        {fixed_bugs}"
    )

    yield (
        _render_state_html(final_state, "success" if success else "fail"),
        _render_metrics_html(new_obs.get("metrics", {})),
        _render_logs_html(new_obs.get("logs", [])),
        _render_agentlog_html(log_lines),
        _render_score_html(final_score),
        _render_bugs_html(diag, fixed_bugs, bug_types),
    )

def manual_step(action_type: str, bug_type: str, service: str):
    params = {}
    if action_type == "diagnose" and bug_type:
        params["bug_type"] = bug_type
    elif action_type == "deploy_fix" and bug_type:
        params["fix_type"] = bug_type
        if service:
            params["service"] = service
    elif action_type in ("read_logs", "restart_service", "rollback") and service:
        params["service"] = service
    if action_type == "rollback":
        params.setdefault("service", "db-primary")
        params["to_version"] = "stable"

    result = _api_step(action_type, params)
    if "error" in result:
        return (
            _render_state_html(f"ERROR: {result['error']}", "fail"),
            EMPTY_METRICS, EMPTY_LOGS, EMPTY_BUGS,
            _render_score_html(0.0001),
        )

    reward  = result.get("reward", {})
    obs     = result.get("observation", {})
    info    = result.get("info", {})
    done    = result.get("done", False)
    diag    = info.get("diagnosed_bugs", [])
    fixed   = info.get("fixed_bugs", [])

    state_msg = (
        f"Action:   {action_type}\n"
        f"Params:   {json.dumps(params)}\n"
        f"Reward:   {reward.get('value', 0):.4f}\n"
        f"Reason:   {reward.get('reason', '')}\n"
        f"Diagnosed: {diag}\n"
        f"Fixed:    {fixed}\n"
        f"Done:     {done}   Remaining: {info.get('steps_remaining', 0)}"
    )

    grade_data  = _api_grade()
    score       = grade_data.get("score", 0.0001)
    all_bugs    = _api_state().get("bug_types", [])

    return (
        _render_state_html(state_msg, "success" if done and score >= 0.5 else "running"),
        _render_metrics_html(obs.get("metrics", {})),
        _render_logs_html(obs.get("logs", [])),
        _render_bugs_html(diag, fixed, all_bugs),
        _render_score_html(score),
    )

def reset_manual(task_id: str, scenario: str):
    obs = _api_reset(task_id, scenario)
    if "error" in obs:
        return (
            _render_state_html(f"ERROR: {obs['error']}", "fail"),
            EMPTY_METRICS, EMPTY_LOGS, EMPTY_BUGS,
            _render_score_html(0.0001),
        )
    hint = obs.get("hint") or ""
    state = f"Environment reset\n{obs.get('system_state', '')}"
    if hint:
        state += f"\n\nHINT: {hint}"
    bugs = _api_state().get("bug_types", [])
    return (
        _render_state_html(state, "init"),
        _render_metrics_html(obs.get("metrics", {})),
        _render_logs_html(obs.get("logs", [])),
        _render_bugs_html([], [], bugs),
        _render_score_html(0.0001),
    )

def build_ui():
    with gr.Blocks(css=_CSS, title="METASIAN — DevOps AI Environment", theme=gr.themes.Base()) as demo:

        gr.HTML("""
        <div class="ms-header">
        <div class="ms-logo">
            <div class="ms-logo-icon">🔧</div>
            <div class="ms-logo-text">
            <h1>METASIAN</h1>
            <p>AUTONOMOUS DEVOPS DEBUGGING ENVIRONMENT</p>
            </div>
        </div>
        <div class="ms-badges">
            <span class="ms-badge ms-badge-green"><span class="ms-live-dot"></span>LIVE</span>
            <span class="ms-badge ms-badge-blue">OpenEnv v1.0</span>
            <span class="ms-badge ms-badge-purple">RL Environment</span>
        </div>
        </div>
        """)

        with gr.Tabs():

            with gr.TabItem("🤖  Auto Agent"):
                with gr.Row(elem_classes=["ms-layout"]):

                    with gr.Column(scale=1, min_width=280, elem_classes=["ms-sidebar"]):
                        gr.HTML("""
                        <div class="ms-card">
                        <div class="ms-card-header">
                            <span class="ms-card-dot"></span>
                            <span class="ms-card-title">Select Task</span>
                        </div>
                        """)
                        task_dd = gr.Dropdown(
                            choices=_TASK_OPTIONS,
                            value="easy_memory_leak",
                            label="Predefined Task",
                            container=True,
                        )
                        gr.HTML('<hr class="ms-divider">')
                        scenario_box = gr.Textbox(
                            label="Custom Scenario  (overrides task selector)",
                            placeholder="e.g. 'Our database is timing out and API returning 503 errors…'",
                            lines=3,
                        )
                        gr.HTML("</div>")

                        run_btn = gr.Button("▶  Run Agent", variant="primary", size="lg")

                        gr.HTML("""
                        <div class="ms-card" style="margin-top:6px;">
                        <div class="ms-card-header">
                            <span class="ms-card-dot" style="background:var(--accent-purple)"></span>
                            <span class="ms-card-title">Tasks</span>
                        </div>
                        <div style="display:flex;flex-direction:column;gap:8px;">
                            <div class="ms-task-pill">
                            <span class="ms-task-pill-icon">🟢</span>
                            <div class="ms-task-pill-body">
                                <span class="ms-task-pill-name">Easy · Memory Leak</span>
                                <span class="ms-task-pill-bugs">memory_leak · max 10 steps</span>
                            </div>
                            </div>
                            <div class="ms-task-pill">
                            <span class="ms-task-pill-icon">🟡</span>
                            <div class="ms-task-pill-body">
                                <span class="ms-task-pill-name">Medium · DB Cascade</span>
                                <span class="ms-task-pill-bugs">db_timeout + api_cascade · max 15 steps</span>
                            </div>
                            </div>
                            <div class="ms-task-pill">
                            <span class="ms-task-pill-icon">🔴</span>
                            <div class="ms-task-pill-body">
                                <span class="ms-task-pill-name">Hard · Disk Corruption</span>
                                <span class="ms-task-pill-bugs">disk_failure + data_corruption · max 20 steps</span>
                            </div>
                            </div>
                        </div>
                        </div>
                        """)

                    with gr.Column(scale=3):
                        with gr.Row():
                            with gr.Column(scale=1, min_width=200):
                                score_out = gr.HTML(value=EMPTY_SCORE)
                            with gr.Column(scale=2):
                                state_out = gr.HTML(value=EMPTY_STATE)

                        bugs_out = gr.HTML(value=EMPTY_BUGS)

                        with gr.Row():
                            with gr.Column(scale=1):
                                metrics_out = gr.HTML(value=EMPTY_METRICS)
                            with gr.Column(scale=1):
                                logs_out = gr.HTML(value=EMPTY_LOGS)

                        agent_log = gr.HTML(value=EMPTY_AGENT)

                run_btn.click(
                    fn=run_demo_agent,
                    inputs=[task_dd, scenario_box],
                    outputs=[state_out, metrics_out, logs_out, agent_log, score_out, bugs_out],
                )

            with gr.TabItem("🎮  Manual Control"):
                with gr.Row(elem_classes=["ms-layout"]):

                    # LEFT: controls
                    with gr.Column(scale=1, min_width=280, elem_classes=["ms-sidebar"]):
                        gr.HTML("""
                        <div class="ms-card">
                        <div class="ms-card-header">
                            <span class="ms-card-dot" style="background:var(--accent-purple)"></span>
                            <span class="ms-card-title">Initialize Environment</span>
                        </div>
                        """)
                        m_task     = gr.Dropdown(choices=_TASK_OPTIONS, value="easy_memory_leak", label="Task")
                        m_scenario = gr.Textbox(label="Custom Scenario (optional)", lines=2)
                        m_reset_btn = gr.Button("↺  Reset Environment", variant="secondary")
                        gr.HTML("</div>")

                        gr.HTML("""
                        <div class="ms-card" style="margin-top:6px;">
                        <div class="ms-card-header">
                            <span class="ms-card-dot" style="background:var(--accent-cyan)"></span>
                            <span class="ms-card-title">Execute Action</span>
                        </div>
                        """)
                        m_action  = gr.Dropdown(
                            choices=["read_logs","check_metrics","diagnose","restart_service","deploy_fix","rollback"],
                            value="read_logs",
                            label="Action Type",
                        )
                        m_bug     = gr.Dropdown(choices=_BUG_TYPES, label="Bug / Fix Type")
                        m_service = gr.Textbox(label="Service Name", value="api-server")
                        m_step_btn = gr.Button("⚡  Execute Action", variant="primary")
                        gr.HTML("</div>")

                    # RIGHT: display
                    with gr.Column(scale=3):
                        with gr.Row():
                            with gr.Column(scale=1, min_width=200):
                                m_score_out = gr.HTML(value=EMPTY_SCORE)
                            with gr.Column(scale=2):
                                m_state_out = gr.HTML(value=EMPTY_STATE)

                        m_bugs_out = gr.HTML(value=EMPTY_BUGS)

                        with gr.Row():
                            with gr.Column(scale=1):
                                m_metrics_out = gr.HTML(value=EMPTY_METRICS)
                            with gr.Column(scale=1):
                                m_logs_out = gr.HTML(value=EMPTY_LOGS)

                m_reset_btn.click(
                    fn=reset_manual,
                    inputs=[m_task, m_scenario],
                    outputs=[m_state_out, m_metrics_out, m_logs_out, m_bugs_out, m_score_out],
                )
                m_step_btn.click(
                    fn=manual_step,
                    inputs=[m_action, m_bug, m_service],
                    outputs=[m_state_out, m_metrics_out, m_logs_out, m_bugs_out, m_score_out],
                )

            with gr.TabItem("📚  Environment"):
                gr.HTML("""
            <div style="padding:24px 28px; max-width:1100px;">

            <div style="margin-bottom:20px;">
                <h2 style="font-family:var(--sans);font-size:22px;font-weight:700;color:var(--text-primary);margin:0 0 6px;">
                METASIAN — Environment Reference
                </h2>
                <p style="font-family:var(--mono);font-size:12px;color:var(--text-muted);margin:0;">
                OpenEnv-compatible · FastAPI backend · Dense reward signal · Anti-cheat monitoring
                </p>
            </div>

            <div class="ms-info-grid" style="margin-bottom:16px;">

                <div class="ms-info-card">
                <h3>Action Space</h3>
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                    <td style="font-family:var(--mono);font-size:11px;color:#60a5fa;padding:5px 8px 5px 0;border-bottom:1px solid var(--border);">read_logs</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-muted);border-bottom:1px solid var(--border);">service: str</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-secondary);border-bottom:1px solid var(--border);">Fetch fresh log lines</td>
                    </tr>
                    <tr>
                    <td style="font-family:var(--mono);font-size:11px;color:#60a5fa;padding:5px 8px 5px 0;border-bottom:1px solid var(--border);">check_metrics</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-muted);border-bottom:1px solid var(--border);">—</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-secondary);border-bottom:1px solid var(--border);">Refresh metric snapshot</td>
                    </tr>
                    <tr>
                    <td style="font-family:var(--mono);font-size:11px;color:#60a5fa;padding:5px 8px 5px 0;border-bottom:1px solid var(--border);">diagnose</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-muted);border-bottom:1px solid var(--border);">bug_type: str</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-secondary);border-bottom:1px solid var(--border);">Identify root cause</td>
                    </tr>
                    <tr>
                    <td style="font-family:var(--mono);font-size:11px;color:#60a5fa;padding:5px 8px 5px 0;border-bottom:1px solid var(--border);">restart_service</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-muted);border-bottom:1px solid var(--border);">service: str</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-secondary);border-bottom:1px solid var(--border);">Temp relief (root persists)</td>
                    </tr>
                    <tr>
                    <td style="font-family:var(--mono);font-size:11px;color:#60a5fa;padding:5px 8px 5px 0;border-bottom:1px solid var(--border);">deploy_fix</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-muted);border-bottom:1px solid var(--border);">fix_type, service</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-secondary);border-bottom:1px solid var(--border);">Apply targeted fix</td>
                    </tr>
                    <tr>
                    <td style="font-family:var(--mono);font-size:11px;color:#60a5fa;padding:5px 8px 5px 0;">rollback</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-muted);">service, to_version</td>
                    <td style="font-family:var(--mono);font-size:10px;color:var(--text-secondary);">Rollback to stable state</td>
                    </tr>
                </table>
                </div>

                <div class="ms-info-card">
                <h3>Reward Signal</h3>
                <table class="ms-reward-table">
                    <tr><th>Event</th><th>Reward</th></tr>
                    <tr><td>Correct diagnosis</td><td class="rw-pos">+0.20–0.30</td></tr>
                    <tr><td>Correct fix (post-diagnosis)</td><td class="rw-pos">+0.30–0.50</td></tr>
                    <tr><td>Correct fix (blind)</td><td class="rw-pos">+0.20</td></tr>
                    <tr><td>Restart service</td><td class="rw-pos">+0.15</td></tr>
                    <tr><td>Read logs / check metrics</td><td class="rw-pos">+0.05</td></tr>
                    <tr><td>Wrong diagnosis</td><td class="rw-neg">−0.20</td></tr>
                    <tr><td>Irrelevant fix</td><td class="rw-neg">−0.30</td></tr>
                    <tr><td>Repeated action ×n</td><td class="rw-neg">−0.10 × n</td></tr>
                </table>
                </div>

                <div class="ms-info-card">
                <h3>Bug Types</h3>
                <ul>
                    <li><span style="color:#60a5fa;">memory_leak</span> — heap exhaustion in api-server</li>
                    <li><span style="color:#60a5fa;">db_timeout</span> — connection pool exhaustion</li>
                    <li><span style="color:#60a5fa;">api_cascade</span> — circuit breaker open (503s)</li>
                    <li><span style="color:#60a5fa;">disk_failure</span> — sector I/O errors on storage</li>
                    <li><span style="color:#60a5fa;">data_corruption</span> — WAL checksum failures</li>
                </ul>
                <h3 style="margin-top:14px;">Anti-Cheat</h3>
                <ul>
                    <li>Max 4 deploy attempts before penalty</li>
                    <li>Excessive log reads penalised after 5×</li>
                    <li>Blind-fix attempts tracked separately</li>
                </ul>
                </div>

                <div class="ms-info-card">
                <h3>Task Overview</h3>
                <table class="ms-reward-table">
                    <tr><th>Task</th><th>Bugs</th><th>Steps</th><th>Baseline</th></tr>
                    <tr>
                    <td><span style="color:#34d399;">●</span> Easy</td>
                    <td>1</td><td>10</td>
                    <td class="rw-pos">~0.80</td>
                    </tr>
                    <tr>
                    <td><span style="color:#fcd34d;">●</span> Medium</td>
                    <td>2</td><td>15</td>
                    <td style="color:#fcd34d;">~0.55</td>
                    </tr>
                    <tr>
                    <td><span style="color:#f87171;">●</span> Hard</td>
                    <td>2</td><td>20</td>
                    <td class="rw-neg">~0.25</td>
                    </tr>
                </table>
                <h3 style="margin-top:14px;">Grading Range</h3>
                <p>All scores clamped to <span style="color:#60a5fa;">(0.0001, 0.9999)</span>.<br>
                Success threshold: <span style="color:#34d399;">≥ 0.50</span>.</p>
                </div>

            </div>

            <div class="ms-info-card" style="margin-top:0;">
                <h3>Observation Schema</h3>
                <p style="font-family:var(--mono);font-size:11px;color:var(--text-secondary);line-height:1.9;">
                <span style="color:#a78bfa;">system_state</span>: str — high-level health summary &nbsp;·&nbsp;
                <span style="color:#a78bfa;">logs</span>: List[str] — last 8 log lines &nbsp;·&nbsp;
                <span style="color:#a78bfa;">metrics</span>: {cpu_percent, memory_percent, latency_ms, error_rate, disk_io_mbps} &nbsp;·&nbsp;
                <span style="color:#a78bfa;">step_count</span>: int &nbsp;·&nbsp;
                <span style="color:#a78bfa;">available_actions</span>: List[str] &nbsp;·&nbsp;
                <span style="color:#a78bfa;">hint</span>: Optional[str]
                </p>
            </div>

            </div>
            """)

    return demo

def launch(port: int = 7861, share: bool = True):
    ui = build_ui()
    ui.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=share,
        show_error=True,
    )

if __name__ == "__main__":
    launch()