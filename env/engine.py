import copy
import time
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
_CHEAT_THRESHOLD = 5
_MAX_DEPLOY_ATTEMPTS = 4


class AntiCheatMonitor:
    def __init__(self):
        self._action_counts: Dict[str, int] = {}
        self._deploy_attempts: int = 0
        self._blind_fix_attempts: int = 0
        self._penalty_total: float = 0.0

    def record(self, action_type: str, params: dict, diagnosed: list) -> float:
        penalty = 0.0
        key = action_type
        self._action_counts[key] = self._action_counts.get(key, 0) + 1

        if action_type == "deploy_fix":
            self._deploy_attempts += 1
            fix_type = params.get("fix_type", "")
            if fix_type and fix_type not in diagnosed:
                self._blind_fix_attempts += 1
            if self._deploy_attempts > _MAX_DEPLOY_ATTEMPTS:
                penalty -= 0.05

        if self._action_counts.get("read_logs", 0) > _CHEAT_THRESHOLD:
            penalty -= 0.02
        if self._action_counts.get("check_metrics", 0) > _CHEAT_THRESHOLD:
            penalty -= 0.02

        self._penalty_total += penalty
        return penalty

    def total_penalty(self) -> float:
        return self._penalty_total


class RuleBasedCritic:
    def evaluate(self, action_type: str, params: dict, state: TaskState, metrics: dict) -> Tuple[float, str]:
        bonus = 0.0
        notes = []

        mem = metrics.get("memory_percent", 0)
        err = metrics.get("error_rate", 0)
        lat = metrics.get("latency_ms", 0)
        disk = metrics.get("disk_io_mbps", 0)

        if action_type == "diagnose":
            bug = params.get("bug_type", "")
            if bug == "memory_leak" and mem > 85:
                bonus += 0.05
                notes.append("evidence-backed diagnosis")
            elif bug == "db_timeout" and lat > 10000:
                bonus += 0.05
                notes.append("evidence-backed diagnosis")
            elif bug == "api_cascade" and err > 0.5:
                bonus += 0.05
                notes.append("evidence-backed diagnosis")
            elif bug == "disk_failure" and disk > 100:
                bonus += 0.05
                notes.append("evidence-backed diagnosis")

        if action_type == "deploy_fix":
            fix = params.get("fix_type", "")
            if fix in state.diagnosed_bugs:
                bonus += 0.03
                notes.append("fix follows diagnosis")

        if action_type == "read_logs" and len(state.action_history) == 0:
            bonus += 0.02
            notes.append("good first action")

        reason_suffix = f" [{', '.join(notes)}]" if notes else ""
        return bonus, reason_suffix


class MetasianEnv:
    def __init__(self) -> None:
        self._task: Optional[TaskDefinition] = None
        self._state: Optional[TaskState] = None
        self._log_buffer: List[str] = []
        self._metrics_snapshot: Dict[str, float] = {}
        self._metric_history: List[Dict[str, float]] = []
        self._anticheat: Optional[AntiCheatMonitor] = None
        self._critic: RuleBasedCritic = RuleBasedCritic()
        self._episode_start: float = 0.0
        self._custom_task: Optional[TaskDefinition] = None

    def reset(self, task_id: str = "easy_memory_leak", custom_task: Optional[TaskDefinition] = None) -> Observation:
        task_registry = dict(TASKS)
        if custom_task is not None:
            task_registry[custom_task.task_id] = custom_task
            self._custom_task = custom_task
        else:
            self._custom_task = None

        if task_id not in task_registry:
            raise ValueError(f"Unknown task '{task_id}'. Available: {list(task_registry.keys())}")

        self._task = task_registry[task_id]
        self._state = TaskState(
            task_id=task_id,
            bug_types=list(self._task.bug_types),
            max_steps=self._task.max_steps,
        )
        self._log_buffer = list(self._task.initial_logs)
        self._metrics_snapshot = copy.deepcopy(self._task.initial_metrics)
        self._metric_history = [copy.deepcopy(self._task.initial_metrics)]
        self._anticheat = AntiCheatMonitor()
        self._episode_start = time.time()
        return self._make_observation()

    def step(self, action: Action) -> Tuple[Observation, Reward, bool, Dict[str, Any]]:
        if self._state is None or self._task is None:
            raise RuntimeError("Environment not initialized — call reset() first.")
        if self._state.done:
            raise RuntimeError("Episode already finished — call reset() to start a new one.")

        self._state.steps_taken += 1
        raw_reward, reason = self._apply_action(action)

        cheat_penalty = self._anticheat.record(
            action.action_type, action.parameters, self._state.diagnosed_bugs
        )
        raw_reward += cheat_penalty

        critic_bonus, critic_note = self._critic.evaluate(
            action.action_type, action.parameters, self._state, self._metrics_snapshot
        )
        raw_reward += critic_bonus
        reason += critic_note

        action_sig = f"{action.action_type}:{sorted(action.parameters.items())}"
        repeats = self._state.action_history.count(action_sig)
        if repeats >= 1:
            raw_reward += REPEAT_PENALTY * repeats
            reason += f" (repeat penalty x{repeats}: {REPEAT_PENALTY * repeats:.4f})"

        self._state.action_history.append(action_sig)
        self._state.cumulative_raw_reward += raw_reward
        self._metric_history.append(copy.deepcopy(self._metrics_snapshot))

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
            "anticheat_penalty": round(self._anticheat.total_penalty(), 4),
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
            "correct_diagnosis_made": self._state.correct_diagnosis_made,
            "correct_fix_applied": self._state.correct_fix_applied,
            "partial_fix_applied": self._state.partial_fix_applied,
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
        raw_score = self._task.grader(state_dict)
        return min(max(raw_score, 0.0001), 0.9999)

    def metric_history(self) -> List[Dict[str, float]]:
        return list(self._metric_history)

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
        return ACTION_BASE_REWARD["read_logs"], f"Fetched logs for '{service}' — {len(self._log_buffer)} lines in buffer"

    def _act_check_metrics(self, params: dict) -> Tuple[float, str]:
        self._simulate_metric_degradation()
        return ACTION_BASE_REWARD["check_metrics"], "Metrics snapshot collected"

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
        self._metrics_snapshot["latency_ms"] = max(self._metrics_snapshot["latency_ms"] * 0.6, 200.0)
        self._metrics_snapshot["error_rate"] = max(self._metrics_snapshot["error_rate"] - 0.10, 0.0)
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
        if fix_type == "memory_leak":
            self._metrics_snapshot["memory_percent"] = 42.0
            self._metrics_snapshot["latency_ms"] = 180.0
            self._metrics_snapshot["error_rate"] = 0.01
            self._log_buffer.append("[ENV] api-server: INFO  Memory stabilized at 42% — heap GC normal")
        elif fix_type == "db_timeout":
            self._metrics_snapshot["latency_ms"] = max(self._metrics_snapshot["latency_ms"] - 25000, 300)
            self._metrics_snapshot["error_rate"] = max(self._metrics_snapshot["error_rate"] - 0.45, 0.05)
            self._log_buffer.append("[ENV] db-proxy: INFO  Connection pool expanded — queries processing normally")
        elif fix_type == "api_cascade":
            self._metrics_snapshot["error_rate"] = max(self._metrics_snapshot["error_rate"] - 0.15, 0.0)
            self._log_buffer.append("[ENV] api-gateway: INFO  Circuit breaker CLOSED — upstream healthy")
        elif fix_type == "disk_failure":
            self._metrics_snapshot["disk_io_mbps"] = 35.0
            self._log_buffer.append("[ENV] storage-node: INFO  I/O errors resolved — disk health nominal")
        elif fix_type == "data_corruption":
            self._log_buffer.append("[ENV] db-primary: INFO  WAL integrity restored — checkpoints valid")

    def _simulate_metric_degradation(self) -> None:
        unfixed = [b for b in self._state.bug_types if b not in self._state.fixed_bugs]
        if "memory_leak" in unfixed:
            self._metrics_snapshot["memory_percent"] = min(
                self._metrics_snapshot["memory_percent"] + 2.0, 99.0
            )
            self._metrics_snapshot["latency_ms"] = min(
                self._metrics_snapshot["latency_ms"] * 1.02, 30000.0
            )
        if "db_timeout" in unfixed:
            self._metrics_snapshot["latency_ms"] = min(
                self._metrics_snapshot["latency_ms"] * 1.05, 60000
            )
            self._metrics_snapshot["error_rate"] = min(
                self._metrics_snapshot["error_rate"] + 0.01, 0.99
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