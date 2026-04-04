from pydantic import BaseModel
from typing import List, Optional

class LogObservation(BaseModel):
    logs: List[str]
    status: str

class LogAction(BaseModel):
    action: str  # e.g., "search", "fix", "submit"
    details: Optional[str] = None

class Reward(BaseModel):
    value: float # 0.0 to 1.0