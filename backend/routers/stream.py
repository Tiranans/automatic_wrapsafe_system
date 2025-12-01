from fastapi import APIRouter, Response, HTTPException
from fastapi.responses import StreamingResponse
import time
from backend.shared import state

router = APIRouter()

async def generate_mjpeg(machine_id: str):
    """Generator for MJPEG stream"""
    while True:
        if not state.controller:
            time.sleep(1)
            continue
            
        # Get latest frame from controller
        # We assume controller has a 'latest_frames' dict
        frame_bytes = state.controller.latest_frames.get(machine_id)
        
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        await time.sleep(0.05) # ~25 FPS cap

@router.get("/{machine_id}")
def video_feed(machine_id: str):
    """Video streaming route. Put this in the src attribute of an img tag."""
    if machine_id not in ["A", "B"]:
        raise HTTPException(status_code=404, detail="Machine not found")
        
    return StreamingResponse(
        generate_mjpeg(machine_id), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
