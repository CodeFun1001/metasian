import os
import sys
import json
import textwrap
from typing import Any, Dict, List, Optional
import requests
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

API_BASE_URL: str = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME: str = os.getenv("MODEL_NAME", "mistralai/Mistral-7B-Instruct-v0.2")
API_KEY: str = os.getenv("HF_TOKEN")
ENV_BASE_URL: str = os.getenv("ENV_BASE_URL", "http://localhost:7860")

MAX_STEPS_OVERRIDE: int = 12
TEMPERATURE: float = 0.2
MAX_TOKENS: int = 256

TASK_IDS = [
    "easy_memory_leak",
    "medium_db_cascade",
    "hard_disk_corruption",
]

SYSTEM_PROMPT = textwrap.dedent("""
You are an expert DevOps engineer debugging a production system.
You will be given:
  - system_state: high-level health summary
  - logs: recent log lines
  - metrics: CPU, memory, latency, error_rate, disk_io
  - available_actions: what you can do

Your goal: diagnose the root cause and apply the correct fix.

You MUST respond with ONLY valid JSON — no markdown, no explanation:
{
  "action_type": "<one of: read_logs|check_metrics|diagnose|restart_service|deploy_fix|rollback>",
  "parameters": { ... }
}

Parameter guide:
  read_logs:       {"service": "<service_name>"}
  check_metrics:   {}
  diagnose:        {"bug_type": "<suspected_bug>"}  -- bug types: memory_leak, db_timeout, api_cascade, disk_failure, data_corruption
  restart_service: {"service": "<service_name>"}
  deploy_fix:      {"fix_type": "<bug_type>", "service": "<service_name>"}
  rollback:        {"service": "<service_name>", "to_version": "<version>"}

Strategy:
1. Read logs first to gather evidence
2. Check metrics to confirm
3. Diagnose the bug(s) you observe
4. Deploy the fix for each diagnosed bug
5. Rollback only if data_corruption is suspected
""").strip()

def log_start(task: str, model: str) -> None:
    print(f"[START] task={task} env=metasian model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    err = error if error else "null"
    print(
        f"[STEP] step={step} action={action} reward={reward:.4f} "
        f"done={str(done).lower()} error={err}",
        flush=True,
    )

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.4f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} "
        f"score={score:.4f} rewards={rewards_str}",
        flush=True,
    )

def env_reset(task_id: str) -> Dict[str, Any]:
    resp = requests.post(
        f"{ENV_BASE_URL}/reset",
        json={"task_id": task_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

def env_step(action_type: str, parameters: dict) -> Dict[str, Any]:
    resp = requests.post(
        f"{ENV_BASE_URL}/step",
        json={"action_type": action_type, "parameters": parameters},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

def env_grade() -> float:
    resp = requests.get(f"{ENV_BASE_URL}/grade", timeout=10)
    resp.raise_for_status()
    return resp.json().get("score", 0.0001)

def build_user_prompt(obs: dict, step: int, history: List[str]) -> str:
    metrics = obs.get("metrics", {})
    logs = "\n".join(obs.get("logs", []))
    recent = "\n".join(history[-3:]) if history else "None"
    hint = obs.get("hint") or ""
    hint_block = f"\nHINT: {hint}" if hint else ""

    return textwrap.dedent(f"""
    === Step {step} ==={hint_block}
    SYSTEM STATE: {obs.get('system_state', 'Unknown')}

    METRICS:
      CPU:     {metrics.get('cpu_percent', '?')}%
      Memory:  {metrics.get('memory_percent', '?')}%
      Latency: {metrics.get('latency_ms', '?')} ms
      Errors:  {metrics.get('error_rate', '?')} (0-1 scale)
      Disk I/O:{metrics.get('disk_io_mbps', '?')} MB/s

    RECENT LOGS:
    {logs}

    PREVIOUS ACTIONS:
    {recent}

    Respond with JSON action only.
    """).strip()


def get_agent_action(client: OpenAI, obs: dict, step: int, history: List[str]) -> Dict[str, Any]:
    user_prompt = build_user_prompt(obs, step, history)
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            timeout=30,
        )
        raw = (completion.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        return parsed
    except json.JSONDecodeError as e:
        print(f"[DEBUG] JSON parse error: {e} | raw={raw!r}", flush=True)
        return {"action_type": "read_logs", "parameters": {"service": "all"}}
    except Exception as e:
        print(f"[DEBUG] LLM call failed: {e}", flush=True)
        return {"action_type": "check_metrics", "parameters": {}}

def run_task(client: OpenAI, task_id: str) -> float:
    log_start(task=task_id, model=MODEL_NAME)

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0001
    success = False
    history: List[str] = []
    error_msg: Optional[str] = None

    try:
        obs = env_reset(task_id)
        done = False

        for step in range(1, MAX_STEPS_OVERRIDE + 1):
            if done:
                break

            action_dict = get_agent_action(client, obs, step, history)
            action_type = action_dict.get("action_type", "read_logs")
            parameters = action_dict.get("parameters", {})
            action_str = f"{action_type}({json.dumps(parameters, separators=(',', ':'))})"

            try:
                result = env_step(action_type, parameters)
                reward_val = result.get("reward", {}).get("value", 0.0001)
                done = result.get("done", False)
                obs = result.get("observation", obs)
                error_msg = None
            except requests.HTTPError as e:
                reward_val = 0.0001
                error_msg = str(e)[:80]
                done = True

            rewards.append(reward_val)
            steps_taken = step
            history.append(f"Step {step}: {action_str} -> reward={reward_val:.4f}")

            log_step(
                step=step,
                action=action_str,
                reward=reward_val,
                done=done,
                error=error_msg,
            )

        score = env_grade()
        success = score >= 0.5

    except Exception as e:
        error_msg = str(e)
        print(f"[DEBUG] Task '{task_id}' failed: {e}", flush=True)

    finally:
        log_end(
            success=success,
            steps=steps_taken,
            score=score,
            rewards=rewards,
        )

    return min(max(score, 0.0001), 0.9999)


def main() -> None:
    if not API_KEY:
        print(
            "[ERROR] HF_TOKEN environment variable not set.",
            flush=True,
        )
        sys.exit(1)

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    all_scores: Dict[str, float] = {}

    for task_id in TASK_IDS:
        print(f"\n{'='*60}", flush=True)
        print(f"Running task: {task_id}", flush=True)
        print(f"{'='*60}", flush=True)
        score = run_task(client, task_id)
        all_scores[task_id] = score

    print("\n" + "=" * 60, flush=True)
    print("BASELINE RESULTS SUMMARY", flush=True)
    print("=" * 60, flush=True)
    for tid, sc in all_scores.items():
        print(f"  {tid:<30} score={sc:.4f}", flush=True)
    avg = sum(all_scores.values()) / len(all_scores)
    print(f"\n  Average score: {avg:.4f}", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()