"""Main application controller"""
from multiprocessing import Queue, freeze_support
from multiprocessing.shared_memory import SharedMemory
from queue import Empty
import threading
import time
import config
from workers.camera_worker import CameraWorker
from workers.yolo_worker import YOLOWorker
from workers.modbus_worker import ModbusWorker
from workers.machine_worker import MachineLogicWorker
from workers.database_worker import DatabaseWorker
from utils.logger import setup_logger
import logging
import numpy as np  
import cv2           
import uvicorn
import os

# Fix for OpenMP runtime conflict (common with YOLO/PyTorch)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from backend.main import app as api_app
from backend.shared import state as api_state

logger = logging.getLogger("Main")
BM9App = None

class AppController:
    def __init__(self):
        self.event_queue = Queue()
        
        # ใช้ "A", "B" ทั้งหมด
        self.machines = {
            "A": {
                'frame_queue': Queue(maxsize=2),
                'camera_cmd_queue': Queue(),
                'yolo_cmd_queue': Queue(),
                'result_queue': Queue(maxsize=5),
                'logic_cmd_queue': Queue(),
                'modbus_di_status_queue': Queue(maxsize=10),
                'modbus_do_status_queue': Queue(maxsize=10),
                'di_status_to_yolo_queue': Queue(maxsize=1),  # DI status for YOLO worker
                'camera_worker': None,
                'yolo_worker': None,
                'logic_worker': None,
                'last_stop_ts': 0.0,
                'alarm_active': False,
            },
            "B": {
                'frame_queue': Queue(maxsize=2),
                'camera_cmd_queue': Queue(),
                'yolo_cmd_queue': Queue(),
                'result_queue': Queue(maxsize=5),
                'logic_cmd_queue': Queue(),
                'modbus_di_status_queue': Queue(maxsize=10),
                'modbus_do_status_queue': Queue(maxsize=10),
                'di_status_to_yolo_queue': Queue(maxsize=1),  # DI status for YOLO worker
                'camera_worker': None,
                'yolo_worker': None,
                'logic_worker': None,
                'last_stop_ts': 0.0,
                'alarm_active': False,
            }
        }

        # Shared Memory Setup
        # 1920x1080 RGB = 6,220,800 bytes
        self.shm_shape = (1080, 1920, 3)
        self.shm_dtype = np.uint8
        self.shm_size = int(np.prod(self.shm_shape))
        self.shared_memories = {}
        
        try:
            for mid in ["A", "B"]:
                shm_name = f"camera_shm_{mid}"
                # Create new shared memory
                shm = SharedMemory(create=True, size=self.shm_size, name=shm_name)
                self.shared_memories[mid] = shm
                logger.info(f"Created shared memory: {shm_name} size={self.shm_size}")
        except FileExistsError:
            logger.warning("Shared memory already exists. Attempting to reuse/overwrite.")

        # API Integration
        self.latest_frames = {}
        api_state.controller = self
        self._start_api_server()

        self.modbus_workers = {}
        
        self.database_worker = DatabaseWorker(self.event_queue)
        self.database_worker.start()
        logger.info("Database worker started")

        self._start_modbus_workers()

        global BM9App
        if BM9App is None:
            from ui.app import BM9App as _BM9App
            BM9App = _BM9App
        self.app = BM9App(self)

        self._start_machine_workers("A", config.MACHINEA_CAMERA_URL)
        self._start_machine_workers("B", config.MACHINEB_CAMERA_URL)

        self.app.after(10, self._poll_frames)
        self.app.after(100, self._poll_modbus_status)

        logger.info("Application initialized")
        self.app.add_log("System initialized - All workers running")
    
    def _start_modbus_workers(self):
        """Start all Modbus workers"""
        # Wrap A DO
        try:
            cmd_q = Queue()
            status_q = Queue()
            w = ModbusWorker(
                config.MODBUSWRAP_A_DO_IP,
                "DO",
                None,
                cmd_q,
                status_q,
                "Wrap_A_DO",
                addr_start=config.DO_START_ADDRESS,
                addr_end=config.DO_END_ADDRESS,
                port=config.MODBUS_PORT
            )
            w.start()
            self.modbus_workers["Wrap_A_DO"] = {"worker": w, "command_queue": cmd_q, "status_queue": status_q}
            logger.info(f"Started Modbus worker Wrap_A_DO")
        except Exception as e:
            logger.exception("Failed to start Wrap_A_DO worker: %s", e)

        # Wrap B DO
        try:
            cmd_q2 = Queue()
            status_q2 = Queue()
            w2 = ModbusWorker(
                config.MODBUSWRAP_B_DO_IP,
                "DO",
                None,
                cmd_q2,
                status_q2,
                "Wrap_B_DO",
                addr_start=config.DO_START_ADDRESS,
                addr_end=config.DO_END_ADDRESS,
                port=config.MODBUS_PORT
            )
            w2.start()
            self.modbus_workers["Wrap_B_DO"] = {"worker": w2, "command_queue": cmd_q2, "status_queue": status_q2}
            logger.info(f"Started Modbus worker Wrap_B_DO")
        except Exception as e:
            logger.exception("Failed to start Wrap_B_DO worker: %s", e)

        # Wrap DI (Combined for A and B as they share the same IP)
        try:
            cmd_q_di = Queue()
            status_q_di = Queue()
            
            # Determine combined address range
            start_addr = min(config.DI_A_START_ADDRESS, config.DI_B_START_ADDRESS)
            end_addr = max(config.DI_A_END_ADDRESS, config.DI_B_END_ADDRESS)
            
            w_di = ModbusWorker(
                config.MODBUSWRAP_DI_IP,
                "DI",
                None,
                cmd_q_di,
                status_q_di,
                "Wrap_DI_Combined",
                addr_start=start_addr,
                addr_end=end_addr,
                port=config.MODBUS_PORT
            )
            w_di.start()
            self.modbus_workers["Wrap_DI_Combined"] = {"worker": w_di, "command_queue": cmd_q_di, "status_queue": status_q_di}
            logger.info(f"Started Modbus worker Wrap_DI_Combined (Addr {start_addr}-{end_addr})")
        except Exception as e:
            logger.exception("Failed to start Wrap_DI_Combined worker: %s", e)
    
    def _start_machine_workers(self, machine_id: str, camera_url: str):
        """Start all workers for a machine"""
        m = self.machines[machine_id]
        
        # Camera worker
        if not m['camera_worker']:
            cam_queue = m['frame_queue']
            cam_cmd_queue = m['camera_cmd_queue']
            
            shm_name = f"camera_shm_{machine_id}"
            
            cw = CameraWorker(
                camera_url, 
                cam_queue, 
                cam_cmd_queue, 
                machine_id,
                shm_name=shm_name,
                shm_shape=self.shm_shape,
                shm_dtype=self.shm_dtype
            )
            cw.start()
            m['camera_worker'] = cw
            logger.info(f"Started Camera worker Machine {machine_id}")
        
        # YOLO worker
        if not m['yolo_worker']:
            yolo_cmd_queue = m['yolo_cmd_queue']
            result_queue = m['result_queue']
            shm_name = f"camera_shm_{machine_id}"
            
            yw = YOLOWorker(
                m['frame_queue'], 
                result_queue, 
                yolo_cmd_queue, 
                machine_id,
                shm_name=shm_name,
                shm_shape=self.shm_shape,
                shm_dtype=self.shm_dtype,
                di_status_queue=m['di_status_to_yolo_queue']  # Pass DI status queue
            )
            yw.start()
            m['yolo_worker'] = yw
            logger.info(f"Started YOLO worker Machine {machine_id}")
        
        # Machine Logic worker
        if not m['logic_worker']:
            do_worker_id = f"Wrap_{machine_id}_DO"
            di_worker_id = f"Wrap_{machine_id}_DI"
            
            logic_config = {
                'auto_stop_enabled': getattr(config, 'AUTO_STOP_ON_PERSON', True),
                'auto_stop_cooldown': getattr(config, 'STOP_COOLDOWN_SEC', 3.0),
                'auto_reset_on_clear': False,
            }
            
            lw = MachineLogicWorker(
                machine_id=machine_id,
                yolo_result_queue=m['result_queue'],
                modbus_di_status_queue=m['modbus_di_status_queue'],
                modbus_do_status_queue=m['modbus_do_status_queue'],
                modbus_do_command_queue=self.modbus_workers.get(do_worker_id, {}).get('command_queue'),
                event_queue=self.event_queue,
                config=logic_config,
                command_queue=m['logic_cmd_queue'],
                di_status_to_yolo_queue=m['di_status_to_yolo_queue']  # Pass DI status queue
            )
            lw.start()
            m['logic_worker'] = lw
            logger.info(f"Started Logic worker Machine {machine_id}")

    def _worker_id_for_machine(self, machine_id: str) -> str: 
        """Get Modbus worker ID for machine"""
        return f"Wrap_{machine_id}_DO" 

    def _send_write_coil(self, worker_id: str, addr: int, value: bool):
        """Send write command to Modbus worker"""
        if worker_id not in self.modbus_workers:
            self.app.add_log(f" [{worker_id}] not found")
            logger.error(f"Modbus worker {worker_id} not found")
            return
        
        cmd_queue = self.modbus_workers[worker_id]["command_queue"]
        cmd_queue.put({"cmd": "WRITE_COIL", "addr": addr, "value": bool(value)})
        logger.info(f"Sent WRITE_COIL to {worker_id}: addr={addr}, value={value}")

    def _pulse_coil(self, worker_id: str, addr: int, pulse_ms: int = None):
        """Send pulse (ON → wait → OFF) to Modbus"""
        pulse_ms = pulse_ms or config.CONTROL_PULSE_MS
        
        self._send_write_coil(worker_id, addr, True)
        
        def _turn_off():
            time.sleep(pulse_ms / 1000.0)
            self._send_write_coil(worker_id, addr, False)
        
        threading.Thread(target=_turn_off, daemon=True).start()

    def start_machine(self, machine_id: str):  
        """Send START command to machine via Modbus"""
        worker_id = self._worker_id_for_machine(machine_id)
        self._pulse_coil(worker_id, config.CONTROL_BUTTON_START_ADDR)
        self.app.add_log(f"[Machine {machine_id}] START command sent")
        logger.info(f"Machine {machine_id} START button pressed")

    def stop_machine(self, machine_id: str): 
        """Send STOP command to machine via Modbus"""
        worker_id = self._worker_id_for_machine(machine_id)
        self._pulse_coil(worker_id, config.CONTROL_BUTTON_STOP_ADDR)
        self.app.add_log(f" [Machine {machine_id}] STOP command sent")
        logger.info(f"Machine {machine_id} STOP button pressed")

    def reset_machine(self, machine_id: str): 
        """Send RESET command to machine via Modbus"""
        worker_id = self._worker_id_for_machine(machine_id)
        self._pulse_coil(worker_id, config.CONTROL_BUTTON_RESET_ADDR)
        self.app.add_log(f" [Machine {machine_id}] RESET command sent")
        logger.info(f"Machine {machine_id} RESET button pressed")

    def _poll_frames(self):
        """Poll camera frames and YOLO results"""
        for mid, m in self.machines.items():  # mid = "A" or "B"
            # Check worker health
            cam_worker = m.get('camera_worker')
            yolo_worker = m.get('yolo_worker')
            logic_worker = m.get('logic_worker') 
            
            if cam_worker and not cam_worker.is_alive():
                logger.error(f"Machine {mid} Camera worker is DEAD!")
                # self.app.add_log(f" Machine {mid} Camera worker stopped!")
                # self._restart_worker(cam_worker, mid)
            
            if yolo_worker and not yolo_worker.is_alive():
                logger.error(f"Machine {mid} YOLO worker is DEAD!")
                # self.app.add_log(f" Machine {mid} YOLO worker stopped!")
            
            if logic_worker and not logic_worker.is_alive():
                logger.error(f"Machine {mid} Logic worker is DEAD!")
                # self.app.add_log(f" Machine {mid} Logic worker stopped!")
            
            # Poll YOLO results
            got = 0
            while got < 10:
                try:
                    r = m['result_queue'].get_nowait()
                    person = r.get('person_in_roi', False)

                    # Decode JPEG frame
                    jpg = r.get('frame_jpeg')
                    
                    # Cache for API streaming (Always needed for Next.js)
                    if jpg:
                        self.latest_frames[mid] = jpg

                    # Update Local UI (Only if enabled)
                    if jpg is not None and getattr(config, 'SHOW_VIDEO_ON_SERVER_UI', True):
                        try:
                            arr = np.frombuffer(jpg, dtype=np.uint8)
                            vis = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if vis is not None:
                                self.app.update_camera(mid, vis)
                        except Exception as e:
                            logger.error(f"Machine {mid} JPEG decode error: {e}")

                    # Update alarm status
                    m['alarm_active'] = person
                
                    self.app.update_alarm_status(mid, person)
                    
                    got += 1
                except Empty:
                    break
                except Exception as e:
                    logger.exception(f"_poll_frames result machine {mid}: {e}")
                    break
        
        self.app.after(10, self._poll_frames)

    def _poll_modbus_status(self):
        """Poll modbus status and forward to logic workers"""
        for worker_id, w_data in self.modbus_workers.items():
            worker = w_data.get("worker")
            if worker and not worker.is_alive():
                logger.error(f"Modbus worker {worker_id} is DEAD!")
                self.app.add_log(f" {worker_id} worker stopped!")
                continue
            
            sq = w_data.get("status_queue")
            if sq is None:
                continue
            
            count = 0
            while count < 20:
                try:
                    status = sq.get_nowait()
                    
                    # Handle Combined DI Worker
                    if worker_id == "Wrap_DI_Combined":
                        # Split data for Machine A (0-7) and B (8-15)
                        status_a = {k: v for k, v in status.get('values', {}).items() if 0 <= k <= 7}
                        status_b = {k: v for k, v in status.get('values', {}).items() if 8 <= k <= 15}
                        
                        # Update UI (Masquerade as separate workers)
                        payload_a = status.copy()
                        payload_a['values'] = status_a
                        self.app.update_modbus_status("Wrap_A_DI", payload_a)
                        
                        payload_b = status.copy()
                        payload_b['values'] = status_b
                        self.app.update_modbus_status("Wrap_B_DI", payload_b)

                        # Send to Machine A Logic
                        if status_a:
                            m_a = self.machines.get("A")
                            if m_a and m_a.get('modbus_di_status_queue'):
                                try:
                                    m_a['modbus_di_status_queue'].put_nowait({'values': status_a})
                                except:
                                    pass
                                    
                        # Send to Machine B Logic
                        if status_b:
                            m_b = self.machines.get("B")
                            if m_b and m_b.get('modbus_di_status_queue'):
                                try:
                                    m_b['modbus_di_status_queue'].put_nowait({'values': status_b})
                                except:
                                    pass
                                    
                    else:
                        # Standard handling for other workers (DOs)
                        self.app.update_modbus_status(worker_id, status)
                        
                        if "DO" in worker_id:
                            machine_id = "A" if "Wrap_A" in worker_id else "B"
                            m = self.machines.get(machine_id)
                            if m and m.get('modbus_do_status_queue'):
                                try:
                                    m['modbus_do_status_queue'].put_nowait(status)
                                except:
                                    pass
                    
                    count += 1
                except Empty:
                    break
                except Exception as e:
                    logger.exception(f"_poll_modbus_status {worker_id}: {e}")
                    break
        
        self.app.after(100, self._poll_modbus_status)

    def run(self):
        """Start the application mainloop"""
        logger.info("[Controller] Entering mainloop...")
        try:
            self.app.mainloop()
        finally:
            self.cleanup()

    def cleanup(self):
        """Stop all workers"""
        logger.info("[Controller] Cleanup started...")
        
        # Send STOP commands
        for mid, m in self.machines.items():
            if m.get('camera_cmd_queue'):
                m['camera_cmd_queue'].put("STOP")
            if m.get('yolo_cmd_queue'):
                m['yolo_cmd_queue'].put("STOP")
            if m.get('logic_cmd_queue'):
                m['logic_cmd_queue'].put("STOP")
        
        for wid, wdict in self.modbus_workers.items():
            cq = wdict.get('command_queue')
            if cq:
                cq.put("STOP")
        
        # Stop database worker
        if self.database_worker:
            self.database_worker.stop()
            self.database_worker.join(timeout=5)
        
        # Wait for workers to stop
        for mid, m in self.machines.items():
            for worker_key in ['camera_worker', 'yolo_worker', 'logic_worker']:
                worker = m.get(worker_key)
                if worker:
                    try:
                        worker.join(timeout=5)
                        if worker.is_alive():
                            logger.warning(f"Machine {mid} {worker_key} didn't stop gracefully")
                            worker.terminate()
                    except Exception as e:
                        logger.error(f"Machine {mid} {worker_key} cleanup error: {e}")
        
        for wid, wdict in self.modbus_workers.items():
            try:
                proc = wdict.get('worker')
                if proc:
                    proc.join(timeout=5)
                    if proc.is_alive():
                        logger.warning(f"Modbus {wid} didn't stop gracefully")
                        proc.terminate()
            except Exception as e:
                logger.error(f"Modbus {wid} cleanup error: {e}")
        
        logger.info("[Controller] All workers stopped")
        
        # Cleanup Shared Memory
        for mid, shm in self.shared_memories.items():
            try:
                shm.close()
                shm.unlink()
                logger.info(f"Shared memory {shm.name} unlinked")
            except Exception as e:
                logger.error(f"Error cleaning up shared memory {mid}: {e}")

    def _start_api_server(self):
        """Start FastAPI server in a separate thread"""
        def run_server():
            uvicorn.run(api_app, host="0.0.0.0", port=8061, log_level="info")
        
        api_thread = threading.Thread(target=run_server, daemon=True)
        api_thread.start()
        logger.info("FastAPI server started on port 8061")

def main():
    """Entry point"""
    freeze_support()
    setup_logger()
    logger.info("=" * 60)
    logger.info("BM9 Automatic Wrap Safety System Starting...")
    logger.info("=" * 60)
    
    try:
        controller = AppController()
        controller.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
    finally:
        logger.info("Application exited")

if __name__ == "__main__":
    main()
