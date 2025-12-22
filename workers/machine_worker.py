from multiprocessing import Process, Queue
from queue import Empty
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, Callable
from datetime import datetime
import time
import logging
import os
import sqlite3
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
    
    # Roll Clamp & Paper Roll Detection
    roll_clamp_detected: bool = False
    paper_roll_detected: bool = False
    auto_start_countdown: Optional[float] = None
    
    # Capture
    last_captured_frame: Optional[bytes] = None
    last_original_frame: Optional[bytes] = None
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
        self.prev_check_roll_status = False
        self.wrapping_start_time = None
        self.check_roll_status = False
        self.current_log_id = None
        self.is_waiting_for_removal = False
        self.removal_wait_start_time = None
        
        # Legacy tracking
        self.prev_green_finish = False
        
        # Delayed capture
        self.roll_capture_pending_time = None
        
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
        
        # Database path for recovery
        self.db_path = "data/machine_events.db"

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
                
                # Roll Clamp & Paper Roll Detection
                self.state.roll_clamp_detected = result.get('roll_clamp_detected', False)
                self.state.paper_roll_detected = result.get('paper_roll_detected', False)
                self.state.auto_start_countdown = result.get('auto_start_countdown', None)
                
                # Handle Auto Start Signal
                if result.get('auto_start_signal', False):
                    self._handle_auto_start()
                
                # Handle capture if available
                if 'frame_jpeg' in result:
                    self.state.last_captured_frame = result['frame_jpeg']
                
                if 'original_frame_jpeg' in result:
                    self.state.last_original_frame = result['original_frame_jpeg']
                    
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
            
            if machine_ready == True :
                self._write_modbus_do(5, True)
            else:
                self._write_modbus_do(5, False)

            check_film_ok = self.state.di_values.get(1, False)
            machine_run = self.state.di_values.get(4, False)

            if machine_run == False :
                if check_film_ok == True :
                    pass
                    self._write_modbus_do(8, False)
                else:
                    pass
                    self._write_modbus_do(8, True)
            
        elif self.machine_id == 'B':
            machine_ready = self.state.di_values.get(13, False) 
            if machine_ready == True :
                pass
                self._write_modbus_do(5, True)
            else:
                pass
                self._write_modbus_do(5, False)

            check_film_ok = self.state.di_values.get(9, False)
            machine_run = self.state.di_values.get(12, False)

            if machine_run == False :
                if check_film_ok == True :
                    pass
                    self._write_modbus_do(8, False)
                else:
                    pass
                    self._write_modbus_do(8, True)

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
    
    def _handle_auto_start(self):
        """Handle auto start signal from Roll clamp release"""
        
        # Check machine state before auto start
        if self.machine_id == 'A':
            machine_ready = self.state.di_values.get(5, False)
            machine_running = self.state.di_values.get(4, False)
            check_roll = self.state.di_values.get(0, False)
        elif self.machine_id == 'B':
            machine_ready = self.state.di_values.get(13, False)
            machine_running = self.state.di_values.get(12, False)
            check_roll = self.state.di_values.get(8, False)
        else:
            logger.error(f"[{self.machine_id}] Unknown machine ID - Auto start cancelled")
            return
        
        # Validate machine state
        if not machine_ready:
            logger.warning(f"[{self.machine_id}]  Auto start cancelled - Machine not ready")
            return
        
        if machine_running:
            logger.warning(f"[{self.machine_id}]  Auto start cancelled - Machine already running")
            return
        
        if not check_roll:
            logger.warning(f"[{self.machine_id}]  Auto start cancelled - No roll detected")
            return
        
        # All conditions met - trigger auto start
        logger.warning(f"[{self.machine_id}]  AUTO START triggered by Roll clamp release!")
        
        # Send START command (Pulse DO 0)
        self._write_modbus_do(0, True)
        time.sleep(0.3)
        self._write_modbus_do(0, False)
        
        self._log_event('AUTO_START', {
            'reason': 'Roll clamp released (3 min delay elapsed)',
            'timestamp': datetime.now().isoformat(),
            'machine_ready': machine_ready,
            'machine_running': machine_running,
            'check_roll': check_roll
        })
    
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
        self._update_machine_status()
        self._check_safety_rules()
        self._check_pending_captures()
        self._check_production_status()

    def _check_pending_captures(self):
        """Check and execute pending delayed captures"""
        if self.roll_capture_pending_time and time.time() >= self.roll_capture_pending_time:
            self.roll_capture_pending_time = None
            logger.info(f"[{self.machine_id}] Executing delayed roll capture (5s after detection)")
            self._capture_production_image('ROLL_DETECTED')

    def _get_last_unfinished_roll(self):
        """Get last unfinished roll from database for state recovery"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Find ROLL_STARTED without matching ROLL_FINISHED in events table
            cursor.execute("""
                SELECT 
                    e1.id,
                    e1.timestamp,
                    e1.data
                FROM events e1
                WHERE e1.machine_id = ?
                  AND e1.event_type = 'ROLL_STARTED'
                  AND NOT EXISTS (
                      SELECT 1 FROM events e2
                      WHERE e2.machine_id = e1.machine_id
                        AND e2.event_type = 'ROLL_FINISHED'
                        AND e2.timestamp > e1.timestamp
                  )
                ORDER BY e1.timestamp DESC
                LIMIT 1
            """, (self.machine_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                start_time = row['timestamp']
                minutes_ago = (time.time() - start_time) / 60.0
                
                return {
                    'log_id': row['id'],
                    'start_time': start_time,
                    'minutes_ago': minutes_ago
                }
            
            return None
            
        except Exception as e:
            logger.error(f"[{self.machine_id}] Error checking unfinished rolls: {e}")
            return None

    def _check_production_status(self):
        """
        Check production status with state recovery
        - Recovers unfinished rolls from database on startup
        - Start: wrapping OFF -> ON (when roll present)
        - Finish: wrapping ON -> OFF AND roll removed
        """
        # Get DI addresses
        if self.machine_id == 'A':
            wrapping_addr = 4
            check_roll_addr = 0
            machine_ready_addr = 5
        elif self.machine_id == 'B':
            wrapping_addr = 12
            check_roll_addr = 8
            machine_ready_addr = 13
        else:
            return

        # DO addresses
        blue_run = 6
        green_finish = 7
        
        # Read current DI
        current_wrapping = self.state.di_values.get(wrapping_addr, False)
        check_roll_current = self.state.di_values.get(check_roll_addr, False)
        machine_ready = self.state.di_values.get(machine_ready_addr, False)
        
        # Update machine running state
        self.state.is_running = current_wrapping
        
        # ต้องเครื่องพร้อมก่อน
        if not machine_ready:
            # Reset states when not ready
            self.prev_wrapping_status = current_wrapping
            self.prev_check_roll_status = check_roll_current
            self.is_waiting_for_removal = False
            self.wrapping_start_time = None
            return

        # ========== STATE RECOVERY: Check for unfinished roll ==========
        # ถ้าไม่มี wrapping_start_time แต่เครื่องกำลังพัน หรือรอยกออก
        if self.wrapping_start_time is None:
            if current_wrapping or (check_roll_current and not current_wrapping):
                unfinished = self._get_last_unfinished_roll()
                if unfinished:
                    self.wrapping_start_time = unfinished['start_time']
                    self.current_log_id = unfinished['log_id']
                    
                    if current_wrapping:
                        logger.info(f"[{self.machine_id}] 🔄 RECOVERED: Active wrapping session (started {unfinished['minutes_ago']:.1f} min ago)")
                    else:
                        logger.info(f"[{self.machine_id}] 🔄 RECOVERED: Waiting for roll removal (started {unfinished['minutes_ago']:.1f} min ago)")
                        self.is_waiting_for_removal = True
                        self.removal_wait_start_time = time.time()

        # ========== EDGE CASE: Roll removed while wrapping ==========
        if current_wrapping and not check_roll_current and self.prev_check_roll_status:
            logger.warning(f"[{self.machine_id}] ⚠️ ABNORMAL: Roll removed while wrapping!")
            # ไม่นับเป็นงานเสร็จ เพราะยังพันไม่เสร็จ
            self.is_waiting_for_removal = False
            self.wrapping_start_time = None

        # ========== DETECT START: wrapping OFF -> ON ==========
        if current_wrapping and not self.prev_wrapping_status:
            # ต้องมี Roll ก่อนถึงจะเริ่มนับ
            if check_roll_current:
                # ตรวจสอบว่าไม่ได้อยู่ในสถานะรอยกออก (ป้องกันการนับซ้ำ)
                if not self.is_waiting_for_removal:
                    logger.info(f"[{self.machine_id}]  WRAP START (Roll detected)")
                    self._on_wrapping_started()
                    self._write_modbus_do(blue_run, True)
                    self._write_modbus_do(green_finish, False)
                    self.is_waiting_for_removal = False
                else:
                    logger.warning(f"[{self.machine_id}]  Wrapping started but still waiting for previous roll removal - IGNORED")
            else:
                logger.warning(f"[{self.machine_id}]  Wrapping started but NO ROLL detected - IGNORED")

        # ========== DETECT WRAPPING STOP: wrapping ON -> OFF ==========
        elif not current_wrapping and self.prev_wrapping_status:
            # ต้องมีการเริ่มงานก่อน (wrapping_start_time ไม่เป็น None)
            if self.wrapping_start_time is not None:
                logger.info(f"[{self.machine_id}]  WRAPPING STOPPED (Waiting for roll removal)")
                self._write_modbus_do(blue_run, False)
                # ยังไม่จบงาน รอคนยกออกก่อน
                self.is_waiting_for_removal = True
                self._write_modbus_do(green_finish, True)
                self.removal_wait_start_time = time.time()  # เริ่มจับเวลารอ
            else:
                logger.warning(f"[{self.machine_id}]  Wrapping stopped but no start time - IGNORED")

        # ========== DETECT REMOVAL: Roll ON -> OFF ==========
        # เช็คว่าพันเสร็จแล้ว (is_waiting_for_removal) และของถูกยกออก (check_roll OFF)
        if self.is_waiting_for_removal:
            # ตรวจสอบ Timeout (ถ้ารอนานเกิน 5 นาที ให้บังคับจบงาน)
            if self.removal_wait_start_time is not None:
                wait_duration = time.time() - self.removal_wait_start_time
                if wait_duration > 300:  # 5 minutes timeout
                    logger.warning(f"[{self.machine_id}]  TIMEOUT: Waited {wait_duration:.0f}s for roll removal - Force completing")
                    self._on_wrapping_finished()
                    self._write_modbus_do(green_finish, False)
                    self.is_waiting_for_removal = False
                    self.removal_wait_start_time = None
            
            # ตรวจจับการยก Roll ออก (Edge: ON -> OFF)
            if not check_roll_current and self.prev_check_roll_status:
                logger.info(f"[{self.machine_id}]  COMPLETE (Roll removed)")
                self._on_wrapping_finished()
                self._write_modbus_do(green_finish, False)
                self.is_waiting_for_removal = False
                self.removal_wait_start_time = None

        # ========== EDGE CASE: Roll placed while waiting ==========
        if self.is_waiting_for_removal and not self.prev_check_roll_status and check_roll_current:
            logger.warning(f"[{self.machine_id}]  ABNORMAL: New roll placed while waiting for removal!")
            # อาจเป็นการวาง Roll ใหม่ ให้รีเซ็ตสถานะ
            # แต่ไม่นับเป็นงานเสร็จ

        # Update Previous State (ต้องอยู่ท้ายสุดเสมอ)
        
        # Detect Roll Rising Edge for Capture (Check Roll ON)
        if check_roll_current and not self.prev_check_roll_status:
             logger.info(f"[{self.machine_id}] Roll Detected -> Scheduling capture in 5s")
             self.roll_capture_pending_time = time.time() + 5.0

        self.prev_wrapping_status = current_wrapping
        self.prev_check_roll_status = check_roll_current

    def _capture_production_image(self, event_type: str) -> Optional[str]:
        """Capture production image with date-based folder structure
        
        Args:
            event_type: 'START' or 'FINISH'
            
        Returns:
            Path to saved image or None
        """
        if not self.production_capture_enabled:
            return None
            
        # Use original frame if available (clean image), otherwise fallback to processed frame
        frame_to_save = self.state.last_original_frame if self.state.last_original_frame else self.state.last_captured_frame
        
        if not frame_to_save:
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
                f.write(frame_to_save)
            
            logger.info(f"[{self.machine_id}] Production image captured: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"[{self.machine_id}] Failed to capture production image: {e}")
            return None

    def _on_wrapping_started(self):
        """Handle wrapping start event (DI ON)"""
        timestamp = time.time()
        self.wrapping_start_time = timestamp
        
        logger.info(
            f"[{self.machine_id}]  WRAPPING STARTED "
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
        timestamp = time.time()
        
        # Calculate wrapping duration
        duration_sec = 0
        if self.wrapping_start_time:
            duration_sec = timestamp - self.wrapping_start_time
        
        duration_min = duration_sec / 60.0
        
        logger.info(
            f"[{self.machine_id}]  WRAPPING FINISHED "
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
            'note': None,
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