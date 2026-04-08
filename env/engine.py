import copy
from typing import Any, Dict, List, Optional, Tuple

from models.schemas import Action, Observation, Reward, SystemMetrics, TaskState
from tasks.definitions import TASKS, TaskDefinition

VALID_ACTIONS = {
    "read_logs",
    "check_metrics",
    "restart_service",
    "deploy_fix",
    "diagnose",
    "rollback",
}

ACTION_BASE_REWARD: Dict[str, float] = {
    "read_logs": 0.05,
    "check_metrics": 0.05,
    "diagnose": 0.10,
    "restart_service": 0.05,
    "deploy_fix": 0.10,
    "rollback": 0.05,
}

REPEAT_PENALTY = -0.10

class MetasianEnv:

    def __init__(self) -> None:
        self._task: Optional[TaskDefinition] = None
        self._state: Optional[TaskState] = None
        self._log_buffer: List[str] = []
        self._metrics_snapshot: Dict[str, float] = {}

    def reset(self, task_id: str = "easy_memory_leak") -> Observation:
        if task_id not in TASKS:
            raise ValueError(
                f"Unknown task '{task_id}'. Available: {list(TASKS.keys())}"
            )
        self._task = TASKS[task_id]
        self._state = TaskState(
            task_id=task_id,
            bug_types=list(self._task.bug_types),
            max_steps=self._task.max_steps,
        )
        self._log_buffer = list(self._task.initial_logs)
        self._metrics_snapshot = copy.deepcopy(self._task.initial_metrics)
        return self._make_observation()

    def step(self, action: Action) -> Tuple[Observation, Reward, bool, Dict[str, Any]]:
        if self._state is None or self._task is None:
            raise RuntimeError("Environment not initialized — call reset() first.")
        if self._state.done:
            raise RuntimeError("Episode already finished — call reset() to start a new one.")

        self._state.steps_taken += 1
        raw_reward, reason = self._apply_action(action)

        action_sig = f"{action.action_type}:{sorted(action.parameters.items())}"
        repeats = self._state.action_history.count(action_sig)
        if repeats >= 1:
            raw_reward += REPEAT_PENALTY * repeats
            reason += f" (repeat penalty ×{repeats}: {REPEAT_PENALTY * repeats:.2f})"

        self._state.action_history.append(action_sig)
        self._state.cumulative_raw_reward += raw_reward

        all_fixed = set(self._state.fixed_bugs) == set(self._state.bug_types)
        out_of_steps = self._state.steps_taken >= self._state.max_steps
        self._state.done = all_fixed or out_of_steps

        normalized = min(max(raw_reward, 0.0001), 0.9999)
        reward = Reward(value=normalized, raw=raw_reward, reason=reason)

        obs = self._make_observation()
        info = {
            "diagnosed_bugs": self._state.diagnosed_bugs,
            "fixed_bugs": self._state.fixed_bugs,
            "all_bugs_fixed": all_fixed,
            "steps_remaining": self._state.max_steps - self._state.steps_taken,
        }
        return obs, reward, self._state.done, info

    def state(self) -> Dict[str, Any]:
        if self._state is None:
            return {"status": "not_initialized"}
        return {
            "task_id": self._state.task_id,
            "bug_types": self._state.bug_types,
            "diagnosed_bugs": self._state.diagnosed_bugs,
            "fixed_bugs": self._state.fixed_bugs,
            "steps_taken": self._state.steps_taken,
            "max_steps": self._state.max_steps,
            "done": self._state.done,
            "cumulative_raw_reward": round(self._state.cumulative_raw_reward, 4),
            "action_history": self._state.action_history,
        }

    def grade(self) -> float:
        if self._state is None or self._task is None:
            return 0.0001
        state_dict = {
            "task_id": self._state.task_id,
            "diagnosed_bugs": list(self._state.diagnosed_bugs),
            "fixed_bugs": list(self._state.fixed_bugs),
            "steps_taken": self._state.steps_taken,
            "action_history": list(self._state.action_history),
            "correct_diagnosis_made": self._state.correct_diagnosis_made,
            "correct_fix_applied": self._state.correct_fix_applied,
            "partial_fix_applied": self._state.partial_fix_applied,
        }
        score = self._task.grader(state_dict)

        return max(0.0001, min(score, 0.9999))

    def _apply_action(self, action: Action) -> Tuple[float, str]:
        atype = action.action_type.lower().strip()
        params = action.parameters or {}

        if atype not in VALID_ACTIONS:
            return -0.20, f"Invalid action type '{atype}'"

        if atype == "read_logs":
            return self._act_read_logs(params)
        elif atype == "check_metrics":
            return self._act_check_metrics(params)
        elif atype == "diagnose":
            return self._act_diagnose(params)
        elif atype == "restart_service":
            return self._act_restart_service(params)
        elif atype == "deploy_fix":
            return self._act_deploy_fix(params)
        elif atype == "rollback":
            return self._act_rollback(params)

        return 0.01, "No-op"

    def _act_read_logs(self, params: dict) -> Tuple[float, str]:
        service = params.get("service", "all")
        new_log = self._generate_log_entry()
        self._log_buffer.append(new_log)
        reward = ACTION_BASE_REWARD["read_logs"]
        return reward, f"Fetched logs for '{service}' — {len(self._log_buffer)} lines in buffer"

    def _act_check_metrics(self, params: dict) -> Tuple[float, str]:
        self._simulate_metric_degradation()
        reward = ACTION_BASE_REWARD["check_metrics"]
        return reward, "Metrics snapshot collected"

    def _act_diagnose(self, params: dict) -> Tuple[float, str]:
        suspected = params.get("bug_type", "").lower().strip()
        if not suspected:
            return -0.10, "diagnose requires 'bug_type' parameter"

        remaining = [b for b in self._state.bug_types if b not in self._state.diagnosed_bugs]

        if suspected in remaining:
            self._state.diagnosed_bugs.append(suspected)
            self._state.correct_diagnosis_made = True
            reward = 0.30 if len(self._state.bug_types) == 1 else 0.20
            return reward, f"Correct diagnosis: '{suspected}'"
        elif suspected in self._state.diagnosed_bugs:
            return -0.10, f"'{suspected}' already diagnosed — no new info"
        else:
            return -0.20, f"Incorrect diagnosis: '{suspected}' is not present in this scenario"

    def _act_restart_service(self, params: dict) -> Tuple[float, str]:
        service = params.get("service", "")
        if not service:
            return -0.05, "restart_service requires 'service' parameter"

        self._metrics_snapshot["latency_ms"] *= 0.6
        self._metrics_snapshot["error_rate"] = max(
            self._metrics_snapshot["error_rate"] - 0.10, 0.0
        )
        self._state.partial_fix_applied = True
        return 0.15, f"Restarted '{service}' — temporary improvement, root cause persists"

    def _act_deploy_fix(self, params: dict) -> Tuple[float, str]:
        fix_type = params.get("fix_type", "").lower().strip()
        if not fix_type:
            return -0.10, "deploy_fix requires 'fix_type' parameter"

        remaining = [b for b in self._state.bug_types if b not in self._state.fixed_bugs]

        if fix_type in remaining:
            if fix_type in self._state.diagnosed_bugs:
                self._state.fixed_bugs.append(fix_type)
                self._state.correct_fix_applied = True
                self._apply_fix_effects(fix_type)
                reward = 0.50 if len(self._state.bug_types) == 1 else 0.30
                return reward, f"Fix successfully deployed for '{fix_type}'"
            else:
                self._state.fixed_bugs.append(fix_type)
                self._apply_fix_effects(fix_type)
                self._state.partial_fix_applied = True
                return 0.20, f"Fix deployed for '{fix_type}' without prior diagnosis — partial credit"
        elif fix_type in self._state.fixed_bugs:
            return -0.05, f"'{fix_type}' already fixed"
        else:
            return -0.30, f"fix_type '{fix_type}' is not relevant to this scenario"

    def _act_rollback(self, params: dict) -> Tuple[float, str]:
        service = params.get("service", "")
        if "data_corruption" in self._state.bug_types:
            if "data_corruption" not in self._state.fixed_bugs:
                self._metrics_snapshot["error_rate"] = max(
                    self._metrics_snapshot["error_rate"] - 0.05, 0.0
                )
                return 0.10, f"Rollback initiated for '{service}' — data integrity partially restored"
        return 0.01, f"Rollback of '{service}' had no effect in this scenario"

    def _apply_fix_effects(self, fix_type: str) -> None:
        """Update metrics to reflect a successful fix."""
        if fix_type == "memory_leak":
            self._metrics_snapshot["memory_percent"] = 42.0
            self._metrics_snapshot["latency_ms"] = 180.0
            self._metrics_snapshot["error_rate"] = 0.01
            self._log_buffer.append(
                "[ENV] api-server: INFO  Memory stabilized at 42% — heap GC normal"
            )
        elif fix_type == "db_timeout":
            self._metrics_snapshot["latency_ms"] = max(
                self._metrics_snapshot["latency_ms"] - 25000, 300
            )
            self._metrics_snapshot["error_rate"] = max(
                self._metrics_snapshot["error_rate"] - 0.45, 0.05
            )
            self._log_buffer.append(
                "[ENV] db-proxy: INFO  Connection pool expanded — queries processing normally"
            )
        elif fix_type == "api_cascade":
            self._metrics_snapshot["error_rate"] = max(
                self._metrics_snapshot["error_rate"] - 0.15, 0.0
            )
            self._log_buffer.append(
                "[ENV] api-gateway: INFO  Circuit breaker CLOSED — upstream healthy"
            )
        elif fix_type == "disk_failure":
            self._metrics_snapshot["disk_io_mbps"] = 35.0
            self._log_buffer.append(
                "[ENV] storage-node: INFO  I/O errors resolved — disk health nominal"
            )
        elif fix_type == "data_corruption":
            self._log_buffer.append(
                "[ENV] db-primary: INFO  WAL integrity restored — checkpoints valid"
            )

    def _simulate_metric_degradation(self) -> None:
        unfixed = [b for b in self._state.bug_types if b not in self._state.fixed_bugs]
        if "memory_leak" in unfixed:
            self._metrics_snapshot["memory_percent"] = min(
                self._metrics_snapshot["memory_percent"] + 2.0, 99.0
            )
        if "db_timeout" in unfixed:
            self._metrics_snapshot["latency_ms"] = min(
                self._metrics_snapshot["latency_ms"] * 1.05, 60000
            )
        if "disk_failure" in unfixed:
            self._metrics_snapshot["disk_io_mbps"] = min(
                self._metrics_snapshot["disk_io_mbps"] + 3.0, 200.0
            )

    def _generate_log_entry(self) -> str:
        
        step = self._state.steps_taken if self._state else 0
        unfixed = [b for b in self._state.bug_types if b not in self._state.fixed_bugs]

        templates = {
            "memory_leak": [
                f"[ENV] api-server: WARNING  Heap usage now {self._metrics_snapshot.get('memory_percent', 90):.0f}% — GC thrashing",
                f"[ENV] api-server: ERROR    Allocation failed at step {step} — OOM risk",
            ],
            "db_timeout": [
                f"[ENV] db-proxy: ERROR   Connection queue depth: {40 + step * 2} — pool exhausted",
                f"[ENV] api-gateway: WARN   Upstream retry #{step} — circuit breaker threshold approaching",
            ],
            "api_cascade": [
                f"[ENV] api-gateway: ERROR  503 from upstream — {step * 12}% of requests failing",
            ],
            "disk_failure": [
                f"[ENV] storage-node: ERROR  Sector read failure count: {step * 3}",
                f"[ENV] storage-node: WARN   I/O latency: {50 + step * 20}ms on /dev/sdb1",
            ],
            "data_corruption": [
                f"[ENV] db-primary: ERROR   Checksum mismatch in WAL segment {step:08d}",
            ],
        }

        lines = []
        for bug in unfixed:
            if bug in templates:
                lines.extend(templates[bug])

        if not lines:
            lines = [f"[ENV] system: INFO  All monitored services nominal at step {step}"]

        return lines[step % len(lines)]

    def _make_observation(self) -> Observation:
        metrics = SystemMetrics(
            cpu_percent=self._metrics_snapshot.get("cpu_percent", 50.0),
            memory_percent=self._metrics_snapshot.get("memory_percent", 50.0),
            latency_ms=self._metrics_snapshot.get("latency_ms", 200.0),
            error_rate=self._metrics_snapshot.get("error_rate", 0.0),
            disk_io_mbps=self._metrics_snapshot.get("disk_io_mbps", 10.0),
        )
        recent_logs = self._log_buffer[-8:]
        return Observation(
            system_state=self._task.system_state_summary if self._task else "Unknown",
            logs=recent_logs,
            metrics=metrics,
            step_count=self._state.steps_taken if self._state else 0,
            available_actions=list(VALID_ACTIONS),
            hint=self._task.hint if self._task else None,
        )

_env_instance = MetasianEnv()

def get_env() -> MetasianEnv:
    return _env_instance