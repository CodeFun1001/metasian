import sys
import os
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from models.schemas import Action, Observation, Reward
from env.engine import get_env
from tasks.definitions import TASKS
from tasks.scenario_generator import generate_scenario_from_description

app = FastAPI(
    title="METASIAN — DevOps Debugging Environment",
    description="OpenEnv-compatible RL environment where an AI agent acts as a DevOps engineer diagnosing and fixing production system failures. Implements reset()/step()/state() per OpenEnv spec.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

env = get_env()

class ResetRequest(BaseModel):
    task_id: Optional[str] = "easy_memory_leak"
    scenario_description: Optional[str] = None

class StepResponse(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: Dict[str, Any]

@app.get("/")
def root():
    return {
        "name": "METASIAN DevOps Debugging Environment",
        "version": "1.0.0",
        "spec": "OpenEnv 1.0",
        "tasks": list(TASKS.keys()),
        "endpoints": ["/reset", "/step", "/state", "/grade", "/tasks", "/health"],
    }

@app.post("/reset", response_model=Observation)
def reset(body: ResetRequest = ResetRequest()):
    try:
        if body.scenario_description and body.scenario_description.strip():
            custom_task = generate_scenario_from_description(body.scenario_description.strip())
            if custom_task is None:
                raise HTTPException(status_code=422, detail="Failed to generate scenario from description.")
            obs = env.reset(task_id=custom_task.task_id, custom_task=custom_task)
            return obs

        task_id = body.task_id or "easy_memory_leak"
        if task_id not in TASKS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown task_id '{task_id}'. Valid: {list(TASKS.keys())}",
            )
        obs = env.reset(task_id=task_id)
        return obs
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/step", response_model=StepResponse)
def step(action: Action):
    try:
        obs, reward, done, info = env.step(action)
        return StepResponse(observation=obs, reward=reward, done=done, info=info)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/state")
def state():
    return env.state()

@app.get("/grade")
def grade():
    score = env.grade()
    internal = env.state()
    return {
        "score": score,
        "task_id": internal.get("task_id"),
        "diagnosed_bugs": internal.get("diagnosed_bugs", []),
        "fixed_bugs": internal.get("fixed_bugs", []),
        "steps_taken": internal.get("steps_taken"),
        "max_steps": internal.get("max_steps"),
    }

@app.get("/metrics/history")
def metrics_history():
    return {"history": env.metric_history()}

@app.get("/tasks")
def list_tasks():
    return [
        {
            "task_id": t.task_id,
            "difficulty": t.difficulty,
            "description": t.description,
            "bug_types": t.bug_types,
            "max_steps": t.max_steps,
        }
        for t in TASKS.values()
    ]

@app.get("/health")
def health():
    return {"status": "ok", "env": "metasian", "version": "1.0.0"}

def _start_ui():
    time.sleep(2)
    try:
        from ui.dashboard import launch
        launch(port=7860, share=True)
    except Exception as e:
        print(f"[UI ERROR] {e}", flush=True)

def main():
    import uvicorn
    if os.getenv("ENABLE_UI", "false").lower() == "true":
        threading.Thread(target=_start_ui, daemon=True).start()
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860, reload=False)

if __name__ == "__main__":
    main()