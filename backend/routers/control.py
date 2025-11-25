from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.shared import state

router = APIRouter()

class ControlCommand(BaseModel):
    command: str  # START, STOP, RESET

@router.post("/{machine_id}")
def control_machine(machine_id: str, cmd: ControlCommand):
    """Send control command to machine"""
    if not state.controller:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    if machine_id not in ["A", "B"]:
        raise HTTPException(status_code=404, detail="Machine not found")
        
    command = cmd.command.upper()
    
    if command == "START":
        state.controller.start_machine(machine_id)
    elif command == "STOP":
        state.controller.stop_machine(machine_id)
    elif command == "RESET":
        state.controller.reset_machine(machine_id)
    else:
        raise HTTPException(status_code=400, detail="Invalid command")
        
    return {"status": "ok", "machine": machine_id, "command": command}
