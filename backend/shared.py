"""
Shared state for FastAPI to access AppController data.
This module acts as a bridge between the main application loop and the API.
"""
from typing import Optional, Any

class SharedState:
    def __init__(self):
        self.controller: Optional[Any] = None

state = SharedState()
