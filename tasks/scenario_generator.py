import os
import json
import random
from typing import Optional
from tasks.definitions import TaskDefinition, TASKS


_SCENARIO_TEMPLATES = [
    {
        "bug_types": ["memory_leak"],
        "difficulty": "easy",
        "max_steps": 10,
        "metrics_profile": {
            "cpu_percent": 48.0,
            "memory_percent": 87.0,
            "latency_ms": 2100.0,
            "error_rate": 0.14,
            "disk_io_mbps": 6.0,
        },
        "system_state_summary": "CRITICAL: Service memory usage climbing. GC thrashing detected.",
    },
    {
        "bug_types": ["db_timeout", "api_cascade"],
        "difficulty": "medium",
        "max_steps": 15,
        "metrics_profile": {
            "cpu_percent": 58.0,
            "memory_percent": 52.0,
            "latency_ms": 28000.0,
            "error_rate": 0.61,
            "disk_io_mbps": 75.0,
        },
        "system_state_summary": "DEGRADED: DB pool saturation causing downstream cascade.",
    },
    {
        "bug_types": ["disk_failure", "data_corruption"],
        "difficulty": "hard",
        "max_steps": 20,
        "metrics_profile": {
            "cpu_percent": 40.0,
            "memory_percent": 51.0,
            "latency_ms": 310.0,
            "error_rate": 0.04,
            "disk_io_mbps": 118.0,
        },
        "system_state_summary": "DEGRADED (partial visibility): Disk I/O anomalies with WAL integrity failures.",
    },
]

_BUG_LOG_TEMPLATES = {
    "memory_leak": [
        "[{ts}] api-server: WARNING  Heap usage climbing — {val}% utilized",
        "[{ts}] api-server: ERROR    OOM killer triggered — process {pid} terminated",
        "[{ts}] api-server: CRITICAL GC overhead limit exceeded — response degraded",
    ],
    "db_timeout": [
        "[{ts}] db-proxy: ERROR   Connection pool exhausted (max=20, waiting={val})",
        "[{ts}] db-proxy: WARN    Query latency exceeding threshold: {val}ms",
        "[{ts}] db-proxy: ERROR   Deadlock detected on table sessions — rolled back",
    ],
    "api_cascade": [
        "[{ts}] api-gateway: ERROR   Circuit breaker OPEN — upstream returning 503",
        "[{ts}] api-gateway: CRITICAL {val}% requests failing — cascade in progress",
        "[{ts}] api-gateway: WARN    Retry storm detected — {val} retries/sec",
    ],
    "disk_failure": [
        "[{ts}] storage-node: ERROR   Sector read failure on /dev/sdb1 — {val} bad sectors",
        "[{ts}] storage-node: WARN    Write latency degraded: {val}ms",
        "[{ts}] storage-node: ERROR   SMART diagnostic warning — disk health at {val}%",
    ],
    "data_corruption": [
        "[{ts}] db-primary: ERROR   WAL checksum mismatch at offset {val}",
        "[{ts}] db-primary: WARN    Page integrity check failed — {val} pages affected",
        "[{ts}] db-primary: ERROR   Replication stream corrupted — standby desync",
    ],
}

_NOISE_LOGS = [
    "[{ts}] auth-service: INFO    JWT validation passed — user {pid}",
    "[{ts}] cache-layer:  INFO    Cache hit rate: {val}%",
    "[{ts}] metrics-svc:  INFO    Heartbeat OK — all watchers nominal",
    "[{ts}] load-balancer: INFO   Health check passed — 3/3 upstreams alive",
    "[{ts}] cron-service: INFO    Scheduled job completed in {val}ms",
]

_TIMESTAMPS = [
    "2025-04-08 10:01:03",
    "2025-04-08 10:01:15",
    "2025-04-08 10:01:30",
    "2025-04-08 10:01:45",
    "2025-04-08 10:02:00",
    "2025-04-08 10:02:15",
    "2025-04-08 10:02:30",
    "2025-04-08 10:02:45",
]


def _render(template: str, idx: int) -> str:
    return template.format(
        ts=_TIMESTAMPS[idx % len(_TIMESTAMPS)],
        val=random.randint(50, 99),
        pid=random.randint(1000, 9999),
    )


def _build_grader_for_bugs(bug_types: list):
    def grader(task_state: dict) -> float:
        score = 0.0001
        diagnosed = task_state.get("diagnosed_bugs", [])
        fixed = task_state.get("fixed_bugs", [])
        per_bug_diag = 0.20 / max(len(bug_types), 1)
        per_bug_fix = 0.50 / max(len(bug_types), 1)
        for b in bug_types:
            if b in diagnosed:
                score += per_bug_diag
            if b in fixed:
                score += per_bug_fix
        if set(bug_types).issubset(set(fixed)):
            if task_state.get("steps_taken", 99) <= max(len(bug_types) * 4, 5):
                score += 0.10
        return min(max(round(score, 4), 0.0001), 0.9999)
    return grader


def generate_scenario_from_description(description: str) -> Optional[TaskDefinition]:
    try:
        from openai import OpenAI
        api_key = os.getenv("HF_TOKEN")
        api_base = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
        model = os.getenv("MODEL_NAME", "mistralai/Mistral-7B-Instruct-v0.2")

        if not api_key:
            return _generate_rule_based(description)

        client = OpenAI(base_url=api_base, api_key=api_key)

        system_prompt = (
            "You are a DevOps infrastructure simulator. Given a natural language incident description, "
            "extract structured JSON with exactly these fields:\n"
            "{\n"
            '  "bug_types": [<list from: memory_leak, db_timeout, api_cascade, disk_failure, data_corruption>],\n'
            '  "system_state_summary": "<one line CRITICAL/DEGRADED/WARNING summary>",\n'
            '  "difficulty": "<easy|medium|hard>"\n'
            "}\n"
            "Return ONLY the JSON object. No markdown, no explanation."
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": description},
            ],
            temperature=0.1,
            max_tokens=200,
            timeout=15,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)

        bug_types = parsed.get("bug_types", ["memory_leak"])
        valid_bugs = {"memory_leak", "db_timeout", "api_cascade", "disk_failure", "data_corruption"}
        bug_types = [b for b in bug_types if b in valid_bugs]
        if not bug_types:
            bug_types = ["memory_leak"]

        difficulty = parsed.get("difficulty", "medium")
        system_state = parsed.get("system_state_summary", "DEGRADED: Incident in progress.")
        max_steps = {"easy": 10, "medium": 15, "hard": 20}.get(difficulty, 15)

        logs = _generate_logs_for_bugs(bug_types)
        metrics = _generate_metrics_for_bugs(bug_types)

        task_id = f"custom_{'+'.join(bug_types)}"
        return TaskDefinition(
            task_id=task_id,
            difficulty=difficulty,
            description=description,
            bug_types=bug_types,
            max_steps=max_steps,
            initial_logs=logs,
            initial_metrics=metrics,
            system_state_summary=system_state,
            grader=_build_grader_for_bugs(bug_types),
            hint=None,
        )
    except Exception:
        return _generate_rule_based(description)


def _generate_rule_based(description: str) -> TaskDefinition:
    desc_lower = description.lower()
    bug_types = []

    if any(k in desc_lower for k in ["memory", "heap", "oom", "leak", "ram"]):
        bug_types.append("memory_leak")
    if any(k in desc_lower for k in ["database", "db", "timeout", "connection", "pool", "query"]):
        bug_types.append("db_timeout")
    if any(k in desc_lower for k in ["api", "cascade", "circuit", "503", "gateway", "upstream"]):
        bug_types.append("api_cascade")
    if any(k in desc_lower for k in ["disk", "io", "storage", "sector", "ssd", "drive"]):
        bug_types.append("disk_failure")
    if any(k in desc_lower for k in ["corrupt", "wal", "checksum", "integrity", "data"]):
        bug_types.append("data_corruption")

    if not bug_types:
        template = random.choice(_SCENARIO_TEMPLATES)
        bug_types = template["bug_types"]

    bug_types = bug_types[:2]

    difficulty = "easy" if len(bug_types) == 1 else ("medium" if len(bug_types) == 2 else "hard")
    max_steps = {"easy": 10, "medium": 15, "hard": 20}[difficulty]
    logs = _generate_logs_for_bugs(bug_types)
    metrics = _generate_metrics_for_bugs(bug_types)

    bug_labels = " + ".join(b.replace("_", " ") for b in bug_types)
    system_state = f"DEGRADED: Custom incident — {bug_labels} detected."

    task_id = f"custom_{'+'.join(bug_types)}"
    return TaskDefinition(
        task_id=task_id,
        difficulty=difficulty,
        description=description,
        bug_types=bug_types,
        max_steps=max_steps,
        initial_logs=logs,
        initial_metrics=metrics,
        system_state_summary=system_state,
        grader=_build_grader_for_bugs(bug_types),
        hint=None,
    )


def _generate_logs_for_bugs(bug_types: list) -> list:
    logs = []
    idx = 0
    for bug in bug_types:
        templates = _BUG_LOG_TEMPLATES.get(bug, [])
        for t in templates[:2]:
            logs.append(_render(t, idx))
            idx += 1
    noise_count = max(0, 8 - len(logs))
    for i in range(noise_count):
        logs.append(_render(random.choice(_NOISE_LOGS), idx + i))
    return logs[:8]


def _generate_metrics_for_bugs(bug_types: list) -> dict:
    base = {
        "cpu_percent": 45.0,
        "memory_percent": 50.0,
        "latency_ms": 300.0,
        "error_rate": 0.02,
        "disk_io_mbps": 10.0,
    }
    if "memory_leak" in bug_types:
        base["memory_percent"] = 89.0
        base["latency_ms"] = max(base["latency_ms"], 1800.0)
        base["error_rate"] = max(base["error_rate"], 0.12)
    if "db_timeout" in bug_types:
        base["latency_ms"] = max(base["latency_ms"], 28000.0)
        base["error_rate"] = max(base["error_rate"], 0.55)
        base["cpu_percent"] = max(base["cpu_percent"], 60.0)
    if "api_cascade" in bug_types:
        base["error_rate"] = max(base["error_rate"], 0.65)
        base["latency_ms"] = max(base["latency_ms"], 15000.0)
    if "disk_failure" in bug_types:
        base["disk_io_mbps"] = max(base["disk_io_mbps"], 110.0)
        base["error_rate"] = max(base["error_rate"], 0.04)
    if "data_corruption" in bug_types:
        base["error_rate"] = max(base["error_rate"], 0.06)
    return base