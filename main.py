from fastapi import FastAPI
from env import LogObservation, LogAction, Reward

app = FastAPI()

@app.post("/reset")
async def reset():
    # This starts the task
    return LogObservation(logs=["System started. Error found in line 42."], status="READY")

@app.post("/step")
async def step(action: LogAction):
    # This processes what the AI decided to do
    reward = 0.5 if action.action == "fix" else 0.0
    done = True if action.action == "submit" else False
    
    return {
        "observation": LogObservation(logs=["Action processed."], status="RUNNING"),
        "reward": Reward(value=reward),
        "done": done,
        "info": {}
    }