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
            
            # Attempt to get detailed state from the logic worker if it has a get_state method
            try:
                # Assuming logic_worker has a method to get its current state object
                # This state object is expected to have attributes like is_auto_mode, mode_changed_time, etc.
                worker_state = logic_worker.get_state() 
                machine_state = {
                    "alarm_active": worker_state.auto_stop_active, # Use worker's state for accuracy
                    "last_stop_ts": worker_state.last_auto_stop_time, # Use worker's state for accuracy
                    "mode": {
                        "is_auto": worker_state.is_auto_mode,
                        "mode_name": "AUTO" if worker_state.is_auto_mode else "MANUAL",
                        "changed_at": worker_state.mode_changed_time
                    }
                }
            except AttributeError:
                # Fallback if logic_worker doesn't have get_state or required attributes
                machine_state = {
                    "alarm_active": m.get('alarm_active', False),
                    "last_stop_ts": m.get('last_stop_ts', 0),
                    "mode": {
                        "is_auto": False, # Default or unknown
                        "mode_name": "UNKNOWN",
                        "changed_at": 0
                    },
                    "warning": "Could not retrieve detailed state from logic worker"
                }
        else:
             machine_state = {
                "alarm_active": m.get('alarm_active', False),
                "error": "Logic worker not running",
                "mode": { # Provide a default mode status even if worker is not running
                    "is_auto": False,
                    "mode_name": "UNKNOWN",
                    "changed_at": 0
                }
            }
            
        data[mid] = machine_state
        
    return data
