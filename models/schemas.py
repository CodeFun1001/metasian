from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SystemMetrics(BaseModel):
    cpu_percent: float = Field(..., description="CPU usage 0–100")
    memory_percent: float = Field(..., description="Memory usage 0–100")
    latency_ms: float = Field(..., description="API response latency in ms")
    error_rate: float = Field(..., description="Requests returning 5xx, 0.0–1.0")
    disk_io_mbps: float = Field(default=0.0, description="Disk I/O throughput MB/s")


class Observation(BaseModel):
    system_state: str = Field(..., description="High-level system health summary")
    logs: List[str] = Field(..., description="Recent log lines from the system")
    metrics: SystemMetrics
    step_count: int = Field(..., description="How many steps taken so far")
    available_actions: List[str] = Field(
        default_factory=list,
        description="Valid action types in this state"
    )
    hint: Optional[str] = Field(
        default=None,
        description="Optional context hint (empty in hard tasks)"
    )


class Action(BaseModel):
    action_type: str = Field(
        ...,
        description=(
            "One of: read_logs, check_metrics, restart_service, "
            "deploy_fix, diagnose, rollback"
        )
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Action-specific parameters. E.g. "
            "{'service': 'api-server'} or {'fix_type': 'memory_leak'}"
        )
    )


class Reward(BaseModel):
    value: float = Field(..., ge=0.0001, le=0.9999, description="Normalized reward in (0, 1)")
    raw: float = Field(..., description="Pre-clamp raw reward (can be negative)")
    reason: str = Field(..., description="Human-readable explanation of this reward signal")


class TaskState(BaseModel):
    task_id: str
    bug_types: List[str]
    diagnosed_bugs: List[str] = Field(default_factory=list)
    fixed_bugs: List[str] = Field(default_factory=list)
    steps_taken: int = 0
    max_steps: int = 15
    done: bool = False
    action_history: List[str] = Field(default_factory=list)
    cumulative_raw_reward: float = 0.0

    # Internal tracking for grader
    correct_diagnosis_made: bool = False
    correct_fix_applied: bool = False
    partial_fix_applied: bool = False