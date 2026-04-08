import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, Optional

from models.schemas import Action, Observation, Reward
from env.engine import get_env
from tasks.definitions import TASKS

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
    task_id = body.task_id or "easy_memory_leak"
    if task_id not in TASKS:
        raise HTTPException(status_code=400, detail=f"Unknown task_id '{task_id}'. Valid: {list(TASKS.keys())}")
    try:
        obs = env.reset(task_id=task_id)
        return obs
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