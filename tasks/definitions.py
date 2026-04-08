from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

@dataclass
class TaskDefinition:
    task_id: str
    difficulty: str
    description: str
    bug_types: List[str]
    max_steps: int
    initial_logs: List[str]
    initial_metrics: Dict[str, float]
    system_state_summary: str
    grader: Callable
    hint: Optional[str] = None

def grade_easy(task_state: dict) -> float:
    score = 0.0
    if task_state.get("correct_diagnosis_made"):
        score += 0.30
    if task_state.get("correct_fix_applied"):
        score += 0.50
        if task_state.get("steps_taken", 99) <= 5:
            score += 0.20
    elif task_state.get("partial_fix_applied"):
        score += 0.20
    return min(round(score, 4), 1.0)


EASY_TASK = TaskDefinition(
    task_id="easy_memory_leak",
    difficulty="easy",
    description=(
        "A single microservice (api-server) is consuming memory rapidly. "
        "The agent must read logs, diagnose the memory leak, and deploy the "
        "correct fix within 10 steps."
    ),
    bug_types=["memory_leak"],
    max_steps=10,
    initial_logs=[
        "[2025-04-08 10:01:03] api-server: WARNING  Memory usage at 74%",
        "[2025-04-08 10:01:15] api-server: ERROR    Heap allocation failed — OOM approaching",
        "[2025-04-08 10:01:30] api-server: ERROR    Response latency spike: 1842ms",
        "[2025-04-08 10:01:45] api-server: CRITICAL Memory usage at 91% — GC pressure high",
        "[2025-04-08 10:02:00] api-server: ERROR    Out of memory: Kill process 3821",
    ],
    initial_metrics={
        "cpu_percent": 45.0,
        "memory_percent": 91.0,
        "latency_ms": 1842.0,
        "error_rate": 0.12,
        "disk_io_mbps": 5.2,
    },
    system_state_summary=(
        "CRITICAL: api-server memory exhaustion. High latency detected. "
        "CPU nominally stable. Suspected memory leak in heap allocation path."
    ),
    hint="Check api-server logs. Memory is climbing rapidly — look for leak patterns.",
    grader=grade_easy,
)

def grade_medium(task_state: dict) -> float:
    score = 0.0
    diagnosed = task_state.get("diagnosed_bugs", [])
    fixed = task_state.get("fixed_bugs", [])

    if "db_timeout" in diagnosed:
        score += 0.20
    if "api_cascade" in diagnosed:
        score += 0.15
    if "db_timeout" in fixed:
        score += 0.30
    if "api_cascade" in fixed:
        score += 0.25
    if "db_timeout" in fixed and "api_cascade" in fixed:
        if task_state.get("steps_taken", 99) <= 8:
            score += 0.10
    return min(round(score, 4), 1.0)


MEDIUM_TASK = TaskDefinition(
    task_id="medium_db_cascade",
    difficulty="medium",
    description=(
        "Database connection pool is exhausted (db_timeout), causing downstream "
        "API services to cascade-fail. Logs are noisy with red herrings. "
        "Agent must identify both bugs and apply targeted fixes."
    ),
    bug_types=["db_timeout", "api_cascade"],
    max_steps=15,
    initial_logs=[
        "[2025-04-08 11:00:01] auth-service: INFO    Login attempt from 192.168.1.42",
        "[2025-04-08 11:00:03] db-proxy:     ERROR   Connection pool exhausted (max=20, waiting=47)",
        "[2025-04-08 11:00:04] api-gateway:  WARN    Upstream timeout after 30s — retrying",
        "[2025-04-08 11:00:05] cache-layer:  INFO    Cache hit rate: 82%",
        "[2025-04-08 11:00:06] api-gateway:  ERROR   Circuit breaker OPEN — failing fast",
        "[2025-04-08 11:00:07] db-proxy:     ERROR   Query timeout: SELECT * FROM sessions (45s)",
        "[2025-04-08 11:00:09] metrics-svc:  WARN    Disk I/O elevated: 89 MB/s",
        "[2025-04-08 11:00:10] api-gateway:  CRITICAL 503 Service Unavailable — cascade failure",
    ],
    initial_metrics={
        "cpu_percent": 62.0,
        "memory_percent": 55.0,
        "latency_ms": 31400.0,
        "error_rate": 0.67,
        "disk_io_mbps": 89.0,
    },
    system_state_summary=(
        "DEGRADED: Database connection pool exhausted. API gateway in circuit-breaker open state. "
        "Downstream services returning 503. Disk I/O elevated but may be unrelated noise."
    ),
    hint=None,
    grader=grade_medium,
)

def grade_hard(task_state: dict) -> float:
    score = 0.0
    diagnosed = task_state.get("diagnosed_bugs", [])
    fixed = task_state.get("fixed_bugs", [])
    history = task_state.get("action_history", [])

    if "disk_failure" in diagnosed:
        score += 0.20
    if "data_corruption" in diagnosed:
        score += 0.20
    if "disk_failure" in fixed:
        score += 0.25
    if "data_corruption" in fixed:
        if fixed.index("data_corruption") < fixed.index("disk_failure") if "disk_failure" in fixed else False:
            score -= 0.15
        else:
            score += 0.25
    if "rollback" in history:
        score += 0.10
    return min(max(round(score, 4), 0.0), 1.0)


HARD_TASK = TaskDefinition(
    task_id="hard_disk_corruption",
    difficulty="hard",
    description=(
        "A storage node is experiencing intermittent disk I/O errors that began 2 hours ago. "
        "Silent data corruption on write paths is corrupting database checkpoints. "
        "Logs are sparse and symptoms appear only every few steps. "
        "Partial observability: metrics lag by 2 steps. "
        "Agent must diagnose, fix disk_failure first, then address data_corruption, "
        "and optionally rollback corrupted writes."
    ),
    bug_types=["disk_failure", "data_corruption"],
    max_steps=20,
    initial_logs=[
        "[2025-04-08 08:30:01] storage-node: INFO    Checkpoint flush completed (3.2s)",
        "[2025-04-08 08:30:45] storage-node: WARN    Slow write detected: 4.1s (threshold 2s)",
        "[2025-04-08 09:12:03] db-primary:   INFO    Replication lag: 120ms",
        "[2025-04-08 09:45:17] storage-node: ERROR   I/O error on /dev/sdb1: sector 0x3A7F bad",
        "[2025-04-08 09:45:19] db-primary:   WARN    Checkpoint CRC mismatch — retrying",
        # Misleading entries
        "[2025-04-08 10:01:00] api-server:   INFO    Request rate normal: 842 req/s",
        "[2025-04-08 10:01:05] cache-layer:  INFO    Eviction rate nominal",
        # Delayed symptom
        "[2025-04-08 10:15:44] db-primary:   ERROR   Corrupt page detected in WAL segment 00000003",
    ],
    initial_metrics={
        "cpu_percent": 38.0,
        "memory_percent": 49.0,
        "latency_ms": 280.0,
        "error_rate": 0.03,
        "disk_io_mbps": 112.0,
    },
    system_state_summary=(
        "DEGRADED (partial visibility): Storage node reporting intermittent I/O errors. "
        "DB checkpoint integrity uncertain. Metrics are lagged — system may look healthier than it is."
    ),
    hint=None,
    grader=grade_hard,
)

TASKS: Dict[str, TaskDefinition] = {
    EASY_TASK.task_id: EASY_TASK,
    MEDIUM_TASK.task_id: MEDIUM_TASK,
    HARD_TASK.task_id: HARD_TASK,
}