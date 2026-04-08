---
title: Metasian
emoji: 🦀
colorFrom: pink
colorTo: indigo
sdk: docker
pinned: false
short_description: AI-powered DevOps Debugging Environment
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference
# 🔧 METASIAN — Autonomous DevOps Debugging Environment

> **OpenEnv-compatible RL environment | India's Biggest Mega AI Hackathon — Round 1**

An AI agent plays the role of a **senior DevOps engineer** responding to production incidents. Given live logs, system metrics, and a broken infrastructure, the agent must diagnose root causes and apply targeted fixes — just like an on-call engineer would at 3 AM.

---

## 🌍 Why This Environment?

Real production outages cost companies millions per hour. Training agents to reason over logs, interpret noisy metrics, and apply correct remediations is a genuinely hard and valuable problem. METASIAN simulates the **exact workflow** a DevOps engineer follows:

1. Read logs to gather evidence  
2. Check metrics to confirm hypotheses  
3. Diagnose the root cause  
4. Apply the right fix (not just restart everything)  
5. Verify recovery  

This is **not a toy**. The environment models realistic failure modes: memory leaks, database pool exhaustion, circuit breaker cascades, and disk corruption — with partial observability and noisy signals.

---

## 🏗 Architecture

```
metasian/
├── main.py
├── inference.py
├── openenv.yaml
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── README.md
├── uv.lock
├── env/
│   ├── __init__.py
│   └── engine.py
├── models/
│   ├── __init__.py
│   └── schemas.py
├── tasks/
│    ├── __init__.py
│    └── definitions.py
├── server/
│    └── app.py
```

---

## 🎮 Action Space

The agent sends structured JSON actions via `POST /step`:

| `action_type`     | Required Parameters                              | Description                                         |
|-------------------|--------------------------------------------------|-----------------------------------------------------|
| `read_logs`       | `{"service": "<name>"}`                          | Fetch fresh log lines from a service                |
| `check_metrics`   | `{}`                                             | Refresh CPU/memory/latency/error_rate snapshot      |
| `diagnose`        | `{"bug_type": "<type>"}`                         | Name the root cause you've identified               |
| `restart_service` | `{"service": "<name>"}`                          | Restart a service (partial fix, root cause persists)|
| `deploy_fix`      | `{"fix_type": "<type>", "service": "<name>"}`    | Apply targeted remediation                          |
| `rollback`        | `{"service": "<name>", "to_version": "<ver>"}`   | Roll back to previous stable state                  |

**Valid bug types:** `memory_leak`, `db_timeout`, `api_cascade`, `disk_failure`, `data_corruption`

---

## 👁 Observation Space

Each `reset()` and `step()` returns:

```json
{
  "system_state": "CRITICAL: api-server memory exhaustion...",
  "logs": [
    "[2025-04-08 10:01:45] api-server: CRITICAL Memory usage at 91%",
    "..."
  ],
  "metrics": {
    "cpu_percent": 45.0,
    "memory_percent": 91.0,
    "latency_ms": 1842.0,
    "error_rate": 0.12,
    "disk_io_mbps": 5.2
  },
  "step_count": 1,
  "available_actions": ["read_logs", "check_metrics", "diagnose", "restart_service", "deploy_fix", "rollback"],
  "hint": "Check api-server logs. Memory is climbing rapidly — look for leak patterns."
}
```

---

## 📊 Reward Function

Rewards are computed **per step** — not just at episode end. This provides dense training signal:

| Event                                    | Reward      |
|------------------------------------------|-------------|
| Correct diagnosis                        | +0.20–0.30  |
| Correct fix (with prior diagnosis)       | +0.30–0.50  |
| Correct fix (lucky, no diagnosis)        | +0.20       |
| Restart service (temporary relief)       | +0.15       |
| Read logs / check metrics (exploration)  | +0.05       |
| Wrong diagnosis                          | −0.20       |
| Irrelevant fix                           | −0.30       |
| Repeated identical action                | −0.10 × n   |
| Invalid action type                      | −0.20       |

All step rewards are **clamped to [0.0, 1.0]** before returning. The grader applies separate holistic scoring.

---

## 📋 Tasks

### ✅ Easy — `easy_memory_leak`
**Difficulty:** Easy | **Max Steps:** 10 | **Bug:** `memory_leak`

A single microservice (`api-server`) is consuming memory at an accelerating rate. Logs clearly indicate heap allocation failures and OOM errors. The agent must:
1. Read logs to identify the api-server memory pattern  
2. Diagnose `memory_leak`  
3. Deploy fix: `{"fix_type": "memory_leak", "service": "api-server"}`  

**Hint provided:** Yes — agent gets a text hint in the observation.

**Grading:**
- Correct diagnosis: +0.30  
- Correct fix: +0.50  
- Fix within ≤5 steps: +0.20 bonus  
- Max score: **1.00**

---

### ⚠️ Medium — `medium_db_cascade`
**Difficulty:** Medium | **Max Steps:** 15 | **Bugs:** `db_timeout` + `api_cascade`

The database connection pool is exhausted, causing API gateway to enter circuit-breaker open state. Logs contain **red herring entries** (elevated disk I/O, nominal cache hits). Agent must identify both bugs and fix both — in any order.

**No hints provided.**

**Grading:**
- Diagnose `db_timeout`: +0.20  
- Diagnose `api_cascade`: +0.15  
- Fix `db_timeout`: +0.30  
- Fix `api_cascade`: +0.25  
- Both fixed in ≤8 steps: +0.10 efficiency bonus  
- Max score: **1.00**

---

### 🔴 Hard — `hard_disk_corruption`
**Difficulty:** Hard | **Max Steps:** 20 | **Bugs:** `disk_failure` + `data_corruption`

A storage node is experiencing intermittent disk I/O errors that began 2 hours ago. This is causing **silent data corruption** in database write-ahead log (WAL) segments. Key challenges:
- Metrics are **lagged by 2 steps** — system appears healthier than it is  
- Symptoms are sparse and delayed  
- **Fix order matters** — `disk_failure` must be resolved before `data_corruption`  
- Rollback provides additional score if used correctly  

**No hints provided.**

**Grading:**
- Diagnose `disk_failure`: +0.20  
- Diagnose `data_corruption`: +0.20  
- Fix `disk_failure` (correct order): +0.25  
- Fix `data_corruption` (after disk): +0.25  
- Rollback used: +0.10  
- Wrong fix order penalty: −0.15  
- Max score: **1.00**

---

## 🚀 Setup & Usage

### Local Development

```bash
# 1. Clone the repo
git clone https://github.com/your-org/metasian
cd metasian

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the environment server
uvicorn server.app:app --host 0.0.0.0 --port 7860 --reload

# 5. Verify it's running
curl http://localhost:7860/health
# → {"status":"ok","env":"metasian","version":"1.0.0"}
```

### Run Inference (Baseline Agent)

```bash
export HF_TOKEN="your-hf-token"
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export ENV_BASE_URL="http://localhost:7860"

python inference.py
```

### Docker

```bash
# Build
docker build -t metasian .

# Run
docker run -p 7860:7860 metasian

# Test
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "easy_memory_leak"}'
```

---

## 🔌 API Reference

| Endpoint      | Method | Body / Params                          | Returns                            |
|---------------|--------|----------------------------------------|------------------------------------|
| `/`           | GET    | —                                      | Environment info                   |
| `/reset`      | POST   | `{"task_id": "<id>"}`                  | `Observation`                      |
| `/step`       | POST   | `{"action_type": "...", "parameters": {...}}` | `{observation, reward, done, info}` |
| `/state`      | GET    | —                                      | Internal state (for debugging)     |
| `/grade`      | GET    | —                                      | Task grader score [0.0–1.0]        |
| `/tasks`      | GET    | —                                      | All task definitions               |
| `/health`     | GET    | —                                      | Liveness probe                     |

---

## 📈 Baseline Results

| Task                  | Difficulty | Baseline Score (Qwen2.5-72B) |
|-----------------------|------------|------------------------------|
| `easy_memory_leak`    | Easy       | ~0.80                        |
| `medium_db_cascade`   | Medium     | ~0.55                        |
| `hard_disk_corruption`| Hard       | ~0.25                        |
| **Average**           |            | **~0.53**                    |

*Scores are reproducible given same model + temperature=0.2*

---

## 🔗 Hugging Face Deployment

```bash
pip install huggingface_hub

huggingface-cli login

openenv push --repo-id your-username/metasian
```

Space URL format: `https://your-username-metasian.hf.space`

---

## ✅ OpenEnv Validation

```bash
pip install openenv-core
openenv validate
```

Expected: ✅ All checks pass

---

## 📄 License

MIT — Built for India's Biggest Mega AI Hackathon, Round 1.
