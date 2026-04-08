import sys
import os
import json
import time
import requests
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import gradio as gr

ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860")

_TASK_OPTIONS = [
    "easy_memory_leak",
    "medium_db_cascade",
    "hard_disk_corruption",
]

_BUG_TYPES = [
    "memory_leak",
    "db_timeout",
    "api_cascade",
    "disk_failure",
    "data_corruption",
]

_DEMO_STRATEGIES: dict = {
    "easy_memory_leak": [
        ("read_logs", {"service": "api-server"}),
        ("check_metrics", {}),
        ("diagnose", {"bug_type": "memory_leak"}),
        ("deploy_fix", {"fix_type": "memory_leak", "service": "api-server"}),
    ],
    "medium_db_cascade": [
        ("read_logs", {"service": "db-proxy"}),
        ("check_metrics", {}),
        ("diagnose", {"bug_type": "db_timeout"}),
        ("read_logs", {"service": "api-gateway"}),
        ("diagnose", {"bug_type": "api_cascade"}),
        ("deploy_fix", {"fix_type": "db_timeout", "service": "db-proxy"}),
        ("deploy_fix", {"fix_type": "api_cascade", "service": "api-gateway"}),
    ],
    "hard_disk_corruption": [
        ("read_logs", {"service": "storage-node"}),
        ("check_metrics", {}),
        ("read_logs", {"service": "db-primary"}),
        ("diagnose", {"bug_type": "disk_failure"}),
        ("diagnose", {"bug_type": "data_corruption"}),
        ("deploy_fix", {"fix_type": "disk_failure", "service": "storage-node"}),
        ("rollback", {"service": "db-primary", "to_version": "stable"}),
        ("deploy_fix", {"fix_type": "data_corruption", "service": "db-primary"}),
    ],
}

_CSS = """
body, .gradio-container {
    background: #0d1117 !important;
    color: #e6edf3 !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
}
.gr-button-primary {
    background: linear-gradient(135deg, #238636, #2ea043) !important;
    border: none !important;
    color: white !important;
    font-weight: 700 !important;
    border-radius: 6px !important;
}
.gr-button-secondary {
    background: #21262d !important;
    border: 1px solid #30363d !important;
    color: #e6edf3 !important;
    border-radius: 6px !important;
}
.gr-panel, .gr-box {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
}
label {
    color: #8b949e !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
}
.gr-textbox textarea, .gr-textbox input {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    color: #e6edf3 !important;
    font-family: 'JetBrains Mono', monospace !important;
    border-radius: 6px !important;
}
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


def _format_metrics(metrics: dict) -> str:
    if not metrics:
        return "— no data —"
    cpu = metrics.get("cpu_percent", 0)
    mem = metrics.get("memory_percent", 0)
    lat = metrics.get("latency_ms", 0)
    err = metrics.get("error_rate", 0)
    disk = metrics.get("disk_io_mbps", 0)

    def bar(val, max_val=100, width=20):
        filled = int((val / max_val) * width)
        filled = min(filled, width)
        return "█" * filled + "░" * (width - filled)

    lines = [
        f"  CPU     {bar(cpu)}  {cpu:.1f}%",
        f"  Memory  {bar(mem)}  {mem:.1f}%",
        f"  Errors  {bar(err * 100)}  {err:.3f}",
        f"  Latency {bar(min(lat / 600, 100))}  {lat:.0f}ms",
        f"  Disk IO {bar(min(disk / 2, 100))}  {disk:.1f} MB/s",
    ]
    return "\n".join(lines)


def _format_logs(logs: list) -> str:
    if not logs:
        return "— no logs —"
    colored = []
    for line in logs:
        if "CRITICAL" in line or "ERROR" in line:
            colored.append(f"[!!] {line}")
        elif "WARN" in line:
            colored.append(f"[!]  {line}")
        elif "INFO" in line or "ENV" in line:
            colored.append(f"[i]  {line}")
        else:
            colored.append(f"     {line}")
    return "\n".join(colored)


def _score_bar(score: float) -> str:
    width = 30
    filled = int(score * width)
    bar = "▓" * filled + "░" * (width - filled)
    grade = "S" if score >= 0.9 else "A" if score >= 0.7 else "B" if score >= 0.5 else "C" if score >= 0.3 else "F"
    return f"  [{bar}]  {score:.4f}  Grade: {grade}"


def run_demo_agent(task_id: str, scenario_desc: str):
    log_lines = []
    metrics_text = ""
    logs_text = ""
    state_text = ""
    score_text = ""

    obs = _api_reset(task_id, scenario_desc)
    if "error" in obs:
        yield (
            f"ERROR: {obs['error']}",
            "—", "—",
            "Reset failed.",
            "0.0001",
        )
        return

    effective_task = obs.get("system_state", task_id)
    metrics_text = _format_metrics(obs.get("metrics", {}))
    logs_text = _format_logs(obs.get("logs", []))
    hint = obs.get("hint") or ""
    state_text = f"TASK INITIALIZED\n{effective_task}"
    if hint:
        state_text += f"\nHINT: {hint}"
    score_text = _score_bar(0.0001)
    log_lines.append(f"[INIT] Environment reset. Task: {task_id}")

    yield (
        "\n".join(log_lines),
        metrics_text,
        logs_text,
        state_text,
        score_text,
    )

    strategy_key = task_id if not (scenario_desc and scenario_desc.strip()) else None
    actions = _DEMO_STRATEGIES.get(strategy_key or "", _DEMO_STRATEGIES["easy_memory_leak"])

    if scenario_desc and scenario_desc.strip():
        state = _api_state()
        bug_types = state.get("bug_types", ["memory_leak"])
        actions = []
        actions.append(("read_logs", {"service": "all"}))
        actions.append(("check_metrics", {}))
        for b in bug_types:
            actions.append(("diagnose", {"bug_type": b}))
        for b in bug_types:
            if b == "data_corruption":
                actions.append(("rollback", {"service": "db-primary", "to_version": "stable"}))
            actions.append(("deploy_fix", {"fix_type": b, "service": "target-service"}))

    for step_num, (action_type, params) in enumerate(actions, 1):
        time.sleep(0.6)
        result = _api_step(action_type, params)
        if "error" in result:
            log_lines.append(f"[STEP {step_num}] ERROR: {result['error']}")
            yield ("\n".join(log_lines), metrics_text, logs_text, state_text, score_text)
            break

        reward = result.get("reward", {})
        reward_val = reward.get("value", 0)
        reason = reward.get("reason", "")
        done = result.get("done", False)
        info = result.get("info", {})
        new_obs = result.get("observation", {})

        metrics_text = _format_metrics(new_obs.get("metrics", {}))
        logs_text = _format_logs(new_obs.get("logs", []))

        diag = info.get("diagnosed_bugs", [])
        fixed = info.get("fixed_bugs", [])
        remaining = info.get("steps_remaining", 0)

        state_text = (
            f"Step {step_num} — {action_type.upper()}\n"
            f"Params: {json.dumps(params)}\n"
            f"Reward: {reward_val:.4f}  |  Reason: {reason}\n"
            f"Diagnosed: {diag}\n"
            f"Fixed: {fixed}\n"
            f"Steps remaining: {remaining}"
        )

        log_lines.append(
            f"[STEP {step_num:2d}] {action_type}({json.dumps(params, separators=(',', ':'))}) "
            f"→ reward={reward_val:.4f}  done={str(done).lower()}"
        )

        grade_data = _api_grade()
        current_score = grade_data.get("score", 0.0001)
        score_text = _score_bar(current_score)

        yield (
            "\n".join(log_lines),
            metrics_text,
            logs_text,
            state_text,
            score_text,
        )

        if done:
            break

    time.sleep(0.3)
    grade_data = _api_grade()
    final_score = grade_data.get("score", 0.0001)
    success = final_score >= 0.5
    diagnosed = grade_data.get("diagnosed_bugs", [])
    fixed_bugs = grade_data.get("fixed_bugs", [])

    log_lines.append("")
    log_lines.append("=" * 55)
    log_lines.append(f"  EPISODE COMPLETE")
    log_lines.append(f"  Score:    {final_score:.4f}")
    log_lines.append(f"  Success:  {'YES' if success else 'NO'}")
    log_lines.append(f"  Diagnosed: {diagnosed}")
    log_lines.append(f"  Fixed:     {fixed_bugs}")
    log_lines.append("=" * 55)

    state_text = (
        f"EPISODE COMPLETE\n"
        f"Final Score: {final_score:.4f}\n"
        f"Success: {'YES ✓' if success else 'NO ✗'}\n"
        f"Bugs Diagnosed: {diagnosed}\n"
        f"Bugs Fixed: {fixed_bugs}"
    )
    score_text = _score_bar(final_score)

    yield (
        "\n".join(log_lines),
        metrics_text,
        logs_text,
        state_text,
        score_text,
    )


def manual_step(action_type: str, bug_type: str, service: str):
    params = {}
    if action_type == "diagnose" and bug_type:
        params["bug_type"] = bug_type
    elif action_type in ("deploy_fix",) and bug_type:
        params["fix_type"] = bug_type
        if service:
            params["service"] = service
    elif action_type in ("read_logs", "restart_service", "rollback") and service:
        params["service"] = service
    elif action_type == "rollback":
        params["service"] = service or "db-primary"
        params["to_version"] = "stable"

    result = _api_step(action_type, params)
    if "error" in result:
        return f"ERROR: {result['error']}", "—", "—", "—"

    reward = result.get("reward", {})
    obs = result.get("observation", {})
    info = result.get("info", {})
    done = result.get("done", False)

    step_summary = (
        f"Action: {action_type}  Params: {params}\n"
        f"Reward: {reward.get('value', 0):.4f}  Reason: {reward.get('reason', '')}\n"
        f"Diagnosed: {info.get('diagnosed_bugs', [])}\n"
        f"Fixed: {info.get('fixed_bugs', [])}\n"
        f"Done: {done}  Steps remaining: {info.get('steps_remaining', 0)}"
    )

    grade_data = _api_grade()
    score = grade_data.get("score", 0.0001)

    return (
        step_summary,
        _format_metrics(obs.get("metrics", {})),
        _format_logs(obs.get("logs", [])),
        _score_bar(score),
    )


def reset_manual(task_id: str, scenario: str):
    obs = _api_reset(task_id, scenario)
    if "error" in obs:
        return f"ERROR: {obs['error']}", "—", "—", "—"
    hint = obs.get("hint") or ""
    state = f"Reset complete.\n{obs.get('system_state', '')}"
    if hint:
        state += f"\nHINT: {hint}"
    return (
        state,
        _format_metrics(obs.get("metrics", {})),
        _format_logs(obs.get("logs", [])),
        _score_bar(0.0001),
    )


def build_ui():
    with gr.Blocks(css=_CSS, title="METASIAN — DevOps AI", theme=gr.themes.Base()) as demo:
        gr.Markdown(
            """
# 🔧 METASIAN — Autonomous DevOps Debugging Environment
> AI agent plays senior DevOps engineer | OpenEnv-compatible | India's Biggest Mega AI Hackathon
            """
        )

        with gr.Tabs():
            with gr.TabItem("🤖 Auto Agent Demo"):
                with gr.Row():
                    with gr.Column(scale=1):
                        task_dropdown = gr.Dropdown(
                            choices=_TASK_OPTIONS,
                            value="easy_memory_leak",
                            label="Predefined Task",
                        )
                        scenario_box = gr.Textbox(
                            label="Custom Scenario (optional — overrides task dropdown)",
                            placeholder="e.g. 'Our database is timing out and the API is returning 503 errors'",
                            lines=3,
                        )
                        run_btn = gr.Button("▶ Run Agent", variant="primary")

                    with gr.Column(scale=2):
                        score_out = gr.Textbox(label="Score", lines=2, interactive=False)
                        state_out = gr.Textbox(label="Episode State", lines=6, interactive=False)

                with gr.Row():
                    with gr.Column():
                        metrics_out = gr.Textbox(label="System Metrics", lines=7, interactive=False)
                    with gr.Column():
                        logs_out = gr.Textbox(label="System Logs", lines=7, interactive=False)

                agent_log = gr.Textbox(label="Agent Action Log", lines=12, interactive=False)

                run_btn.click(
                    fn=run_demo_agent,
                    inputs=[task_dropdown, scenario_box],
                    outputs=[agent_log, metrics_out, logs_out, state_out, score_out],
                )

            with gr.TabItem("🎮 Manual Control"):
                with gr.Row():
                    with gr.Column(scale=1):
                        m_task = gr.Dropdown(choices=_TASK_OPTIONS, value="easy_memory_leak", label="Task")
                        m_scenario = gr.Textbox(label="Custom Scenario (optional)", lines=2)
                        m_reset_btn = gr.Button("Reset Environment", variant="secondary")

                    with gr.Column(scale=1):
                        m_action = gr.Dropdown(
                            choices=list(["read_logs", "check_metrics", "diagnose", "restart_service", "deploy_fix", "rollback"]),
                            value="read_logs",
                            label="Action Type",
                        )
                        m_bug = gr.Dropdown(choices=_BUG_TYPES, label="Bug Type (for diagnose/deploy_fix)")
                        m_service = gr.Textbox(label="Service Name (for read_logs/restart/rollback)", value="api-server")
                        m_step_btn = gr.Button("Execute Action", variant="primary")

                m_state_out = gr.Textbox(label="Step Result", lines=6, interactive=False)
                with gr.Row():
                    m_metrics_out = gr.Textbox(label="Metrics", lines=7, interactive=False)
                    m_logs_out = gr.Textbox(label="Logs", lines=7, interactive=False)
                m_score_out = gr.Textbox(label="Score", lines=2, interactive=False)

                m_reset_btn.click(
                    fn=reset_manual,
                    inputs=[m_task, m_scenario],
                    outputs=[m_state_out, m_metrics_out, m_logs_out, m_score_out],
                )
                m_step_btn.click(
                    fn=manual_step,
                    inputs=[m_action, m_bug, m_service],
                    outputs=[m_state_out, m_metrics_out, m_logs_out, m_score_out],
                )

            with gr.TabItem("📚 Environment Info"):
                gr.Markdown("""
## Action Space

| Action | Parameters | Description |
|--------|-----------|-------------|
| `read_logs` | `service` | Fetch fresh log lines |
| `check_metrics` | — | Refresh system metrics |
| `diagnose` | `bug_type` | Identify root cause |
| `restart_service` | `service` | Temporary relief |
| `deploy_fix` | `fix_type`, `service` | Apply targeted fix |
| `rollback` | `service`, `to_version` | Rollback to stable state |

## Bug Types
- `memory_leak` — heap exhaustion in api-server
- `db_timeout` — connection pool exhaustion
- `api_cascade` — circuit breaker open, 503 cascade
- `disk_failure` — sector I/O errors on storage node
- `data_corruption` — WAL checksum failures in db-primary

## Reward Signal
| Event | Reward |
|-------|--------|
| Correct diagnosis | +0.20–0.30 |
| Correct fix (post-diagnosis) | +0.30–0.50 |
| Correct fix (blind) | +0.20 |
| Restart (temp relief) | +0.15 |
| Log read / metric check | +0.05 |
| Wrong diagnosis | −0.20 |
| Irrelevant fix | −0.30 |
| Repeated action | −0.10×n |

## Grading
All scores are strictly in **(0.0001, 0.9999)**. The `/grade` endpoint runs the task's holistic grader.
                """)

    return demo

def launch(port: int = 7861, share: bool = True):
    ui = build_ui()
    ui.launch(
        server_name="127.0.0.1",
        server_port=port,
        share=True,
        show_error=True
    )

if __name__ == "__main__":
    launch()