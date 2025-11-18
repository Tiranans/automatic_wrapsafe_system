from multiprocessing import Process, Queue
from queue import Empty
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, Callable
from datetime import datetime
import time
import logging
import os
from pathlib import Path
import base64
from utils.logger import setup_logger

logger = setup_logger('MachineLogic')

@dataclass
class MachineState:
    """Current state of machine"""
    machine_id: str
    
    # YOLO Detection status
    person_detected: bool = False
    person_count: int = 0
    detection_timestamp: float = 0.0
    
  
    last_captured_frame: Optional[bytes] = None  # JPEG bytes
    last_captured_timestamp: Optional[str] = None
    last_captured_path: Optional[str] = None
    
    # Modbus DO status (outputs we control)
    do_values: Dict[int, bool] = field(default_factory=dict)
    
    # Modbus DI status (inputs from machine)
    di_values: Dict[int, bool] = field(default_factory=dict)
    
    # Machine status
    is_running: bool = False
    is_ready: bool = False
    has_error: bool = False
    film_ok: bool = False
    roll_ok: bool = False
    
    # Auto-control
    auto_stop_active: bool = False
    last_auto_stop_time: float = 0.0


class MachineLogicWorker(Process):
    
    def __init__(
        self,
        machine_id: str,
        yolo_result_queue: Queue,
        modbus_di_status_queue: Queue,
        modbus_do_status_queue: Queue,
        modbus_do_command_queue: Queue,
        event_queue: Queue,
        config: Dict[str, Any],
        command_queue: Queue = None
    ):
        super().__init__()
        
        self.machine_id = machine_id
        
        # Input queues
        self.yolo_result_queue = yolo_result_queue
        self.modbus_di_status_queue = modbus_di_status_queue
        self.modbus_do_status_queue = modbus_do_status_queue
        
        # Output queues
        self.modbus_do_command_queue = modbus_do_command_queue
        self.event_queue = event_queue
        
        # Control queue
        self.command_queue = command_queue or Queue()
        
        # Configuration
        self.config = config
        self.auto_stop_enabled = config.get('auto_stop_enabled', True)
        self.auto_stop_cooldown = config.get('auto_stop_cooldown', 3.0)
        self.auto_reset_on_clear = config.get('auto_reset_on_clear', False)
        

        self.capture_enabled = config.get('capture_enabled', True)
        self.capture_dir = config.get('capture_dir', 'data/captures')
        self.max_captures = config.get('max_captures_per_machine', 100)
        self.capture_on_detection = config.get('capture_on_detection', True)
        
      
        self._init_capture_dir()
        
        # State
        self.state = MachineState(machine_id=machine_id)
        self.running = False
        
        # Event callbacks
        self.on_person_detected: Optional[Callable] = None
        self.on_person_cleared: Optional[Callable] = None
        self.on_machine_started: Optional[Callable] = None
        self.on_machine_stopped: Optional[Callable] = None
        self.on_error_detected: Optional[Callable] = None
    
    def _init_capture_dir(self):
        """Initialize capture directory"""
        try:
            capture_path = Path(self.capture_dir) / f"machine_{self.machine_id}"
            capture_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"[{self.machine_id}] Capture directory: {capture_path}")
        except Exception as e:
            logger.error(f"[{self.machine_id}] Failed to create capture dir: {e}")
    
    def run(self):
        """Main worker loop"""
        logger.info(f"[{self.machine_id}] Machine Logic Worker started - PID={self.pid}")
        self.running = True
        
        while self.running:
            try:
                self._process_commands()
                self._update_yolo_status()
                self._update_di_status()
                self._update_do_status()
                self._execute_logic()
                
                time.sleep(0.05)  # 50ms = 20Hz
                
            except Exception as e:
                logger.exception(f"[{self.machine_id}] Logic loop error: {e}")
                time.sleep(1)
        
        logger.info(f"[{self.machine_id}] Machine Logic Worker stopped")
    
    def _process_commands(self):
        """Process control commands"""
        try:
            while not self.command_queue.empty():
                cmd = self.command_queue.get_nowait()
                
                if cmd == "STOP":
                    self.running = False
                    return
                
                if isinstance(cmd, dict):
                    cmd_type = cmd.get('type')
                    
                    if cmd_type == 'ENABLE_AUTO_STOP':
                        self.auto_stop_enabled = True
                        logger.info(f"[{self.machine_id}] Auto-stop enabled")
                    
                    elif cmd_type == 'DISABLE_AUTO_STOP':
                        self.auto_stop_enabled = False
                        logger.info(f"[{self.machine_id}] Auto-stop disabled")
                    
                    elif cmd_type == 'WRITE_DO':
                        addr = cmd.get('addr')
                        value = cmd.get('value')
                        self._write_modbus_do(addr, value)
                    
                  
                    elif cmd_type == 'CAPTURE_FRAME':
                        self._manual_capture()
        
        except Exception as e:
            logger.error(f"[{self.machine_id}] Command processing error: {e}")
    
    
    def _update_yolo_status(self):
        """Update status from YOLO detection"""
        try:
            while not self.yolo_result_queue.empty():
                result = self.yolo_result_queue.get_nowait()
                
                prev_detected = self.state.person_detected
                
                self.state.person_detected = result.get('person_in_roi', False)
                self.state.person_count = result.get('person_count', 0)
                self.state.detection_timestamp = result.get('ts', time.time())
                
           
                if self.state.person_detected and not prev_detected:
                    frame_jpeg = result.get('frame_jpeg')
                    if frame_jpeg and self.capture_on_detection:
                        self._capture_frame(frame_jpeg, result)
                    self._on_person_enter_roi()
                
                elif not self.state.person_detected and prev_detected:
                    self._on_person_exit_roi()
        
        except Exception as e:
            logger.error(f"[{self.machine_id}] YOLO status update error: {e}")
    
    def _update_di_status(self):
        """Update status from Modbus DI"""
        try:
            while not self.modbus_di_status_queue.empty():
                status = self.modbus_di_status_queue.get_nowait()
                
                if not status.get('connected'):
                    continue
                
                values = status.get('values', {})
                self.state.di_values = values
                
                self.state.roll_ok = values.get(0, False)
                self.state.film_ok = values.get(1, False)
                self.state.is_running = values.get(4, False)
                self.state.is_ready = values.get(5, False)
                
                logger.debug(
                    f"[{self.machine_id}] DI Status: "
                    f"Running={self.state.is_running}, "
                    f"Ready={self.state.is_ready}, "
                    f"Film={self.state.film_ok}, "
                    f"Roll={self.state.roll_ok}"
                )
        
        except Exception as e:
            logger.error(f"[{self.machine_id}] DI status update error: {e}")
    
    def _update_do_status(self):
        """Update status from Modbus DO"""
        try:
            while not self.modbus_do_status_queue.empty():
                status = self.modbus_do_status_queue.get_nowait()
                
                if not status.get('connected'):
                    continue
                
                values = status.get('values', {})
                self.state.do_values = values
        
        except Exception as e:
            logger.error(f"[{self.machine_id}] DO status update error: {e}")
    

    def _capture_frame(self, frame_jpeg: bytes, detection_data: dict):

        if not self.capture_enabled:
            return
        
        try:
            # Generate filename with timestamp
            now = datetime.now()
            timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # ถึง millisecond
            filename = f"capture_{timestamp_str}_count{self.state.person_count}.jpg"
            
            # Save path
            capture_path = Path(self.capture_dir) / f"machine_{self.machine_id}"
            filepath = capture_path / filename
            
            # Save image
            with open(filepath, 'wb') as f:
                f.write(frame_jpeg)
            
            # Update state
            self.state.last_captured_frame = frame_jpeg
            self.state.last_captured_timestamp = now.isoformat()
            self.state.last_captured_path = str(filepath)
            
            logger.info(
                f"[{self.machine_id}] 📸 Captured frame: {filename} "
                f"(person_count={self.state.person_count})"
            )
            
            # Log event with image path
            self._log_event('FRAME_CAPTURED', {
                'timestamp': self.state.last_captured_timestamp,
                'person_count': self.state.person_count,
                'filepath': str(filepath),
                'filename': filename,
                'file_size': len(frame_jpeg),
                'detected_keypoints': detection_data.get('detected_keypoints', [])
            })
         
            self._cleanup_old_captures(capture_path)
            
        except Exception as e:
            logger.error(f"[{self.machine_id}] Frame capture error: {e}")
    
    def _manual_capture(self):
        """Manual capture (triggered by command)"""
        logger.info(f"[{self.machine_id}] Manual capture requested")
        # Get latest frame from state
        if self.state.last_captured_frame:
            self._capture_frame(self.state.last_captured_frame, {})
    
    def _cleanup_old_captures(self, capture_path: Path):
        """
        Keep only the latest N captures per machine
        
        Args:
            capture_path: Directory containing captures
        """
        try:
            # Get all capture files
            captures = sorted(
                capture_path.glob("capture_*.jpg"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            # Delete old files if exceeds limit
            if len(captures) > self.max_captures:
                for old_file in captures[self.max_captures:]:
                    old_file.unlink()
                    logger.debug(f"[{self.machine_id}] Deleted old capture: {old_file.name}")
                
                logger.info(
                    f"[{self.machine_id}] Cleanup: kept {self.max_captures} captures, "
                    f"deleted {len(captures) - self.max_captures} old files"
                )
        
        except Exception as e:
            logger.error(f"[{self.machine_id}] Cleanup error: {e}")

    def _execute_logic(self):
        """Execute business logic"""
        pass
        
        # Example logic (uncomment if needed):
        # if self.machine_id == "A":
        #     logger.debug(f"[{self.machine_id}] Executing logic for Machine A")
        #     self._write_modbus_do(1, True)   # กด (ON)
        #     time.sleep(0.3)
        #     self._write_modbus_do(1, False)  # ปล่อย (OFF)
    
    def _trigger_auto_stop(self):
        """Trigger auto-stop sequence"""
        logger.warning(f"[{self.machine_id}]PERSON DETECTED → Auto-stopping")
        
        # Send STOP command
        self._write_modbus_do(1, True)
        time.sleep(0.3)
        self._write_modbus_do(1, False)
        
        self.state.auto_stop_active = True
        self.state.last_auto_stop_time = time.time()
        
        self._log_event('AUTO_STOP', {
            'reason': 'Person detected in ROI',
            'person_count': self.state.person_count,
            'timestamp': datetime.now().isoformat(),
            'captured_frame_path': self.state.last_captured_path 
        })
        
        if self.on_person_detected:
            try:
                self.on_person_detected(self.state)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def _trigger_auto_reset(self):
        """Trigger auto-reset sequence"""
        logger.info(f"[{self.machine_id}] Person cleared → Auto-resetting")
        
        # Send RESET command
        self._write_modbus_do(2, True)
        time.sleep(0.3)
        self._write_modbus_do(2, False)
        
        self.state.auto_stop_active = False
        
        self._log_event('AUTO_RESET', {
            'reason': 'Person cleared from ROI',
            'timestamp': datetime.now().isoformat()
        })
        
        if self.on_person_cleared:
            try:
                self.on_person_cleared(self.state)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def _trigger_error_alarm(self):
        """Trigger error alarm"""
        if not self.state.has_error:
            logger.error(f"[{self.machine_id}] ERROR: Film or Roll problem")
            
            self.state.has_error = True
            
            self._log_event('ERROR_DETECTED', {
                'film_ok': self.state.film_ok,
                'roll_ok': self.state.roll_ok,
                'timestamp': datetime.now().isoformat()
            })
            
            if self.on_error_detected:
                try:
                    self.on_error_detected(self.state)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
    
    def _on_person_enter_roi(self):
        """Handle person entering ROI"""
        logger.info(f"[{self.machine_id}] 👤 Person entered ROI")
        self._log_event('PERSON_ENTER_ROI', {
            'person_count': self.state.person_count,
            'timestamp': datetime.now().isoformat(),
            'captured_frame_path': self.state.last_captured_path  
        })
    
    def _on_person_exit_roi(self):
        """Handle person exiting ROI"""
        logger.info(f"[{self.machine_id}] Person exited ROI")
        self._log_event('PERSON_EXIT_ROI', {
            'timestamp': datetime.now().isoformat()
        })

    
    def _write_modbus_do(self, addr: int, value: bool):
        """Send write command to Modbus DO"""
        try:
            cmd = {
                'cmd': 'WRITE_COIL',
                'addr': addr,
                'value': bool(value)
            }
            self.modbus_do_command_queue.put_nowait(cmd)
            logger.debug(f"[{self.machine_id}] Modbus WRITE: addr={addr}, value={value}")
        except Exception as e:
            logger.error(f"[{self.machine_id}] Modbus write error: {e}")
    
    def _log_event(self, event_type: str, data: Dict[str, Any]):
        """Log event to database"""
        try:
            event = {
                'machine_id': self.machine_id,
                'event_type': event_type,
                'data': data,
                'timestamp': time.time()
            }
            
            if self.event_queue:
                self.event_queue.put_nowait(event)
                logger.debug(f"[{self.machine_id}] Event logged: {event_type}")
        except Exception as e:
            logger.error(f"[{self.machine_id}] Event logging error: {e}")
    
    def get_state(self) -> MachineState:
        """Get current machine state"""
        return self.state