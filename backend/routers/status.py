from fastapi import APIRouter, HTTPException
from backend.shared import state

router = APIRouter()

@router.get("/")
def get_status():
    """Get status of all machines"""
    if not state.controller:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    data = {}
    for mid, m in state.controller.machines.items():
        # Extract relevant data from machine state
        # Note: We need to access the logic worker's state if possible, 
        # or rely on what's available in the controller's machine dict.
        
        logic_worker = m.get('logic_worker')
        machine_state = {}
        
        if logic_worker and logic_worker.is_alive():
            # This is a bit hacky: accessing internal state of a process. 
            # Ideally, logic worker should push state to a shared value/queue.
            # For now, we might only get what's in the controller's scope or 
            # if we change logic_worker to use a Manager().dict() for state.
            
            # fallback: use what we have in controller (alarm_active)
            machine_state = {
                "alarm_active": m.get('alarm_active', False),
                "last_stop_ts": m.get('last_stop_ts', 0),
            }
        else:
             machine_state = {
                "alarm_active": m.get('alarm_active', False),
                "error": "Logic worker not running"
            }
            
        data[mid] = machine_state
        
    return data
