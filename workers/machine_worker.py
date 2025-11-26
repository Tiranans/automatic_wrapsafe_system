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
    
    # Capture
    last_captured_frame: Optional[bytes] = None
    last_captured_timestamp: Optional[str] = None
    last_captured_path: Optional[str] = None
    
    # Modbus DO status
    do_values: Dict[int, bool] = field(default_factory=dict)
    
    # Modbus DI status
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
        command_queue: Queue = None,
        di_status_to_yolo_queue: Queue = None
    ):
        super().__init__()
        self.machine_id = machine_id
        self.yolo_result_queue = yolo_result_queue
        self.modbus_di_status_queue = modbus_di_status_queue
        self.modbus_do_status_queue = modbus_do_status_queue
        self.modbus_do_command_queue = modbus_do_command_queue
        self.event_queue = event_queue
        self.config = config
        self.command_queue = command_queue
        self.di_status_to_yolo_queue = di_status_to_yolo_queue
        
        self.state = MachineState(machine_id=machine_id)
        self.running = False
        
        # Safety tracking
        self.last_stop_time = 0
        self.person_entry_time = None
        
        # Production tracking
        self.prev_wrapping_status = False
        self.wrapping_start_time = None
        self.check_roll_status = False
        self.current_log_id = None
        
        # Legacy tracking
        self.prev_green_finish = False
        
        # Load config values
        self.auto_stop_enabled = config.get('AUTO_STOP_ON_PERSON', True)
        self.auto_stop_cooldown = config.get('STOP_COOLDOWN_SEC', 3.0)
        self.auto_reset_on_clear = config.get('AUTO_RESET_ON_CLEAR', False)
        self.capture_enabled = config.get('CAPTURE_ON_DETECTION', True)
        self.capture_dir = config.get('CAPTURE_DIR', 'captures')
        
        # Production capture config
        self.production_capture_enabled = config.get('PRODUCTION_CAPTURE_ENABLED', True)
        self.production_capture_dir = config.get('PRODUCTION_CAPTURE_DIR', 'production_captures')
        self.production_capture_on_start = config.get('PRODUCTION_CAPTURE_ON_START', True)
        self.production_capture_on_finish = config.get('PRODUCTION_CAPTURE_ON_FINISH', True)
        
        # Create capture directories
        if self.capture_enabled:
            Path(self.capture_dir).mkdir(parents=True, exist_ok=True)
        if self.production_capture_enabled:
            Path(self.production_capture_dir).mkdir(parents=True, exist_ok=True)

    def run(self):
        """Main worker loop"""
        logger.info(f"[{self.machine_id}] Logic Worker started")
        self.running = True
        
        while self.running:
            try:
                # Check commands
                if not self.command_queue.empty():
                    cmd = self.command_queue.get_nowait()
                    if cmd == "STOP":
                        self.running = False
                        break
                
                # Process Inputs
                self._process_yolo_results()
                self._process_modbus_status()
                
                # Execute Logic
                self._execute_logic()
                
                time.sleep(0.01)
                
            except Exception as e:
                logger.exception(f"[{self.machine_id}] Logic loop error: {e}")
                time.sleep(1)
        
        logger.info(f"[{self.machine_id}] Logic Worker stopped")

    def _process_yolo_results(self):
        """Process latest YOLO detection results"""
        try:
            while not self.yolo_result_queue.empty():
                result = self.yolo_result_queue.get_nowait()
                
                self.state.person_detected = result.get('person_in_roi', False)
                self.state.person_count = result.get('person_count', 0)
                self.state.detection_timestamp = result.get('ts', time.time())
                
                # Handle capture if available
                if 'frame_jpeg' in result:
                    self.state.last_captured_frame = result['frame_jpeg']
                    
        except Empty:
            pass
        
    def _process_modbus_status(self):
        """Process latest Modbus DI/DO status"""
        # DI
        try:
            while not self.modbus_di_status_queue.empty():
                status = self.modbus_di_status_queue.get_nowait()
                # Extract 'values' dict from status payload
                di_values = status.get('values', {}) if isinstance(status, dict) else status
                self.state.di_values.update(di_values)
                
                # Send DI status to YOLO worker if enabled
                self._send_di_status_to_yolo()
                
        except Empty:
            pass
            
        # DO
        try:
            while not self.modbus_do_status_queue.empty():
                status = self.modbus_do_status_queue.get_nowait()
                # Extract 'values' dict from status payload
                do_values = status.get('values', {}) if isinstance(status, dict) else status
                self.state.do_values.update(do_values)
        except Empty:
            pass
        self._trigger_error_alarm()

    def _update_machine_status(self):
        """Update high-level machine status based on DI/DO"""
        if self.machine_id == 'A':
            machine_ready = self.state.di_values.get(5, False) 
            # print("machine_ready A  >> ",machine_ready)
            
            if machine_ready == True :
            
                self._write_modbus_do(5, True) #    Machine A: addr 5 ON = machine ready, OFF = machine not ready
         
            else:
            
                self._write_modbus_do(5, False) #    Machine A: addr 5 ON = machine ready, OFF = machine not ready

            check_film_ok = self.state.di_values.get(1, False)
            machine_run = self.state.di_values.get(4, False)

            if machine_run == False :
                if check_film_ok == True :
                    pass
                    self._write_modbus_do(8, False) #    Machine A: addr 8 ON = film ok, OFF = film not ok
                else:
                    pass
                    self._write_modbus_do(8, True) #    Machine A: addr 8 ON = film ok, OFF = film not ok
            
        elif self.machine_id == 'B':

            machine_ready = self.state.di_values.get(13, False) 
            if machine_ready == True :
                pass
                self._write_modbus_do(5, True) # Machine B: addr 13 ON = machine ready, OFF = machine not ready
            else:
                pass
                self._write_modbus_do(5, False) # Machine B: addr 13 ON = machine ready, OFF = machine not ready

            check_film_ok = self.state.di_values.get(9, False)
            machine_run = self.state.di_values.get(12, False)

            if machine_run == False :
                if check_film_ok == True :
                    pass
                    self._write_modbus_do(8, False) #    Machine B: addr 8 ON = film ok, OFF = film not ok
                else:
                    pass
                    self._write_modbus_do(8, True) #    Machine B: addr 8 ON = film ok, OFF = film not ok


    def _check_safety_rules(self):
        """Check safety rules (Auto-Stop)"""
        if not self.auto_stop_enabled:
            return
            
        if self.state.person_detected:
            # Check cooldown
            if not self.state.auto_stop_active:
                if (time.time() - self.state.last_auto_stop_time) > self.auto_stop_cooldown:
                    self._trigger_auto_stop()
        else:
            # Person cleared
            if self.state.auto_stop_active:
                if self.auto_reset_on_clear:
                    self._trigger_auto_reset()
                else:
                    # Just clear the flag, manual reset required
                    self.state.auto_stop_active = False
                    self._on_person_exit_roi()

    def _trigger_auto_stop(self):
        """Trigger auto-stop sequence"""
        logger.warning(f"[{self.machine_id}] PERSON DETECTED → Auto-stopping!")
        
        # Send STOP command (Pulse DO 1)
        self._write_modbus_do(1, True)
        time.sleep(0.3)
        self._write_modbus_do(1, False)
        
        self.state.auto_stop_active = True
        self.state.last_auto_stop_time = time.time()
        
        # Save capture if available
        capture_path = None
        if self.capture_enabled and self.state.last_captured_frame:
            # Create machine-specific folder
            now = datetime.now()
            date_str = now.strftime('%Y-%m-%d')
            machine_folder = f"Machine{self.machine_id}"
            save_dir = Path(self.capture_dir) / machine_folder / date_str
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # Filename: Machine{ID}_{YYYYMMDD}_{HHMMSS}_AUTOSTOP.jpg
            time_str = now.strftime('%H%M%S')
            filename = f"Machine{self.machine_id}_{now.strftime('%Y%m%d')}_{time_str}_AUTOSTOP.jpg"
            capture_path = save_dir / filename
            
            try:
                with open(capture_path, "wb") as f:
                    f.write(self.state.last_captured_frame)
                self.state.last_captured_path = str(capture_path)
            except Exception as e:
                logger.error(f"Failed to save capture: {e}")
        
        self._log_event('AUTO_STOP', {
            'reason': 'Person detected in ROI',
            'person_count': self.state.person_count,
            'timestamp': datetime.now().isoformat(),
            'captured_frame_path': capture_path
        })
        
        self._on_person_enter_roi()

    def _trigger_auto_reset(self):
        """Trigger auto-reset sequence"""
        logger.info(f"[{self.machine_id}] Person cleared → Auto-resetting")
        
        # Send RESET command (Pulse DO 2)
        self._write_modbus_do(2, True)
        time.sleep(0.3)
        self._write_modbus_do(2, False)
        
        self.state.auto_stop_active = False
        
        self._log_event('AUTO_RESET', {
            'reason': 'Person cleared from ROI',
            'timestamp': datetime.now().isoformat()
        })
        
        self._on_person_exit_roi()

    def _trigger_error_alarm(self):
        """Trigger error alarm"""
        pass
    
    def _on_person_enter_roi(self):
        """Handle person entering ROI"""
        pass

    def _send_di_status_to_yolo(self):
        """Send DI status to YOLO worker for conditional detection"""
        if not self.di_status_to_yolo_queue:
            return
        
        di_addr = None
        if self.machine_id == 'A':
            di_addr = 0

        elif self.machine_id == 'B':
            di_addr = 8
            
        if di_addr is None:
            return
        
        detection_enabled = self.state.di_values.get(di_addr, False) 
        
        try:
            self.di_status_to_yolo_queue.put_nowait(detection_enabled)
        except Exception:
            pass
    
    def _on_person_exit_roi(self):
        """Handle person exiting ROI"""
        logger.info(f"[{self.machine_id}] Person exited ROI")
        self._log_event('PERSON_EXIT_ROI', {
            'timestamp': datetime.now().isoformat()
        })
        
    def _execute_logic(self):
        """Execute core machine logic"""
        self._update_machine_status()   # อัปเดตสถานะรวม
        self._check_safety_rules()      # ตรวจสอบความปลอดภัย (Auto Stop)
        self._check_production_status() # ตรวจสอบสถานะผลิต

    def _check_production_status(self):
        """
        Check production status based on Run signal (DI)
        Machine A: addr 4 ON = wrapping, OFF = finished
        Machine B: addr 12 ON = wrapping, OFF = finished
        """
        # Get current wrapping status from DI
        if self.machine_id == 'A':
            wrapping_addr = 4  # addr 4 ON = wrapping, OFF = finished
            check_roll = 0 # addr 0 ON = roll detected, OFF = roll not detected
            machine_ready = 5 # addr 5 ON = machine ready, OFF = machine not ready
        elif self.machine_id == 'B':
            wrapping_addr = 12 # addr 12 ON = wrapping, OFF = finished
            check_roll = 8 # addr 8 ON = roll detected, OFF = roll not detected
            machine_ready = 13 # addr 13 ON = machine ready, OFF = machine not ready
        else:
            return

        # addr 5 ON = machine ready, OFF = machine not ready
        blue_run = 6 # addr 6 ON = machine ready, OFF = machine not ready
        green_finish = 7 # addr 7 ON = machine ready, OFF = machine not ready
        yellow_film = 8 # addr 8 ON = machine ready, OFF = machine not ready
        red_problem = 9 # addr 9 ON = machine ready, OFF = machine not ready    
        
        current_wrapping = self.state.di_values.get(wrapping_addr, False)
        check_roll_status = self.state.di_values.get(check_roll, False)
        machine_ready_status = self.state.di_values.get(machine_ready, False)
        
        if machine_ready_status == True :
            # print("ready....")
            # Detect Rising Edge (OFF -> ON) = Start Wrapping
            if current_wrapping and not self.prev_wrapping_status:
                if check_roll_status == True and machine_ready_status == True :
                    # print("wrap ..............................start")
                    self._on_wrapping_started()
                    self._write_modbus_do(6, True) # ON  blue_run
                    self._write_modbus_do(7, False) # OFF green_finnished


                else:
                    logger.warning(f"[{self.machine_id}] Wrapping started but roll not detected")
            
            # Detect Falling Edge (ON -> OFF) = Finish Wrapping
            elif not current_wrapping and self.prev_wrapping_status:    
                if check_roll_status == False and machine_ready_status == True :
                    # print("wrap.............................. finished")
                    self._on_wrapping_finished()
                    self._write_modbus_do(6, False) # OFF blue_run
                    self._write_modbus_do(7, True) # ON green_finnished
                else:
                    logger.warning(f"[{self.machine_id}] Wrapping finished but roll not detected")
            
            # Update previous state
            self.prev_wrapping_status = current_wrapping
            
            # Update machine running state
            self.state.is_running = current_wrapping
          
        # Legacy: Still check green light for reference
        # current_green = self.state.do_values.get(7, False)
        # if current_green and not self.prev_green_finish:
        #     logger.info(f"[{self.machine_id}] Green Light ON (production may be complete)")
        # self.prev_green_finish = current_green

    def _capture_production_image(self, event_type: str) -> Optional[str]:
        """Capture production image with date-based folder structure
        
        Args:
            event_type: 'START' or 'FINISH'
            
        Returns:
            Path to saved image or None
        """
        if not self.production_capture_enabled or not self.state.last_captured_frame:
            return None
            
        try:
            # Get current datetime
            now = datetime.now()
            date_str = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H%M%S')
            
            # Create machine-specific date folder: production_captures/Machine{ID}/{Date}/
            machine_folder = f"Machine{self.machine_id}"
            save_dir = Path(self.production_capture_dir) / machine_folder / date_str
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename: Machine{ID}_{YYYYMMDD}_{HHMMSS}_{EVENT}.jpg
            filename = f"Machine{self.machine_id}_{now.strftime('%Y%m%d')}_{time_str}_{event_type}.jpg"
            filepath = save_dir / filename
            
            # Save image
            with open(filepath, 'wb') as f:
                f.write(self.state.last_captured_frame)
            
            logger.info(f"[{self.machine_id}] Production image captured: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"[{self.machine_id}] Failed to capture production image: {e}")
            return None

    def _on_wrapping_started(self):
        """Handle wrapping start event (DI ON)"""
        import time
        
        timestamp = time.time()
        self.wrapping_start_time = timestamp
        
        logger.info(
            f"[{self.machine_id}] 🟢 WRAPPING STARTED "
            f"(DI addr {4 if self.machine_id == 'A' else 12} = ON)"
        )
        
        # Capture image on start
        capture_path = None
        if self.production_capture_on_start:
            capture_path = self._capture_production_image('START')
        
        # Log event to database
        self._log_event('ROLL_STARTED', {
            'timestamp': datetime.now().isoformat(),
            'di_address': 4 if self.machine_id == 'A' else 12,
            'machine_status': 'WRAPPING',
            'capture_path': capture_path
        })

    def _on_wrapping_finished(self):
        """Handle wrapping finish event (DI OFF)"""
        import time
        
        timestamp = time.time()
        
        # Calculate wrapping duration
        duration_sec = 0
        if self.wrapping_start_time:
            duration_sec = timestamp - self.wrapping_start_time
        
        duration_min = duration_sec / 60.0
        
        logger.info(
            f"[{self.machine_id}] 🔴 WRAPPING FINISHED "
            f"(DI addr {4 if self.machine_id == 'A' else 12} = OFF) "
            f"Duration: {duration_min:.2f} min"
        )
        
        # Capture image on finish
        capture_path = None
        if self.production_capture_on_finish:
            capture_path = self._capture_production_image('FINISH')
        
        # Log event to database
        self._log_event('ROLL_FINISHED', {
            'timestamp': datetime.now().isoformat(),
            'di_address': 4 if self.machine_id == 'A' else 12,
            'duration_seconds': int(duration_sec),
            'duration_minutes': round(duration_min, 2),
            'machine_status': 'IDLE',
            'note': None,  # สามารถเพิ่ม note ได้ถ้าต้องการ
            'capture_path': capture_path
        })
        
        # Reset tracking
        self.wrapping_start_time = None
        self.current_log_id = None

    def _write_modbus_do(self, addr: int, value: bool):
        """Send write command to Modbus DO"""
        try:
            cmd = {
                'cmd': 'WRITE_COIL',
                'addr': addr,
                'value': bool(value)
            }
            if self.modbus_do_command_queue:
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