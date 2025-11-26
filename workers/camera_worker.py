"""IP Camera streaming worker"""
from multiprocessing import Process, Queue
from multiprocessing.shared_memory import SharedMemory
from utils.logger import setup_logger
import cv2
import time
import config
import numpy as np
from queue import Full

logger = setup_logger('CameraWorker')

class CameraWorker(Process):
    def __init__(
        self, 
        camera_url: str, 
        frame_queue: Queue, 
        command_queue: Queue, 
        machine_id: str,
        shm_name: str = None,
        shm_shape: tuple = None,
        shm_dtype = None
    ):
        super().__init__()
        self.camera_url = camera_url
        self.frame_queue = frame_queue
        self.command_queue = command_queue
        self.machine_id = machine_id  
        self.running = False
        
        # Shared Memory Config
        self.shm_name = shm_name
        self.shm_shape = shm_shape
        self.shm_dtype = shm_dtype
        self.shm = None
        self.shared_frame = None
        
        self.frame_width = None
        self.frame_height = None
        self.roi_pixels = None
        self.roi_initialized = False

    def _init_roi(self, w: int, h: int):
        """Initialize ROI coordinates from first frame (called once)"""
        if self.machine_id == "A":
            roi_normalized = config.A1_DETECT_ROI
        elif self.machine_id == "B":
            roi_normalized = config.B2_DETECT_ROI
        else:
            logger.warning(f"Unknown machine_id: {self.machine_id}, using A1_DETECT_ROI")
            roi_normalized = config.A1_DETECT_ROI
        
        x0n, y0n, x1n, y1n = roi_normalized
        
        self.roi_pixels = (
            int(x0n * w),
            int(y0n * h),
            int(x1n * w),
            int(y1n * h)
        )
        self.frame_width = w
        self.frame_height = h
        self.roi_initialized = True
        
        logger.info(
            f"[Machine {self.machine_id}] ROI initialized: "
            f"Frame={w}x{h}, ROI={self.roi_pixels}"
        )

    def _connect_shared_memory(self):
        """Connect to existing shared memory block"""
        if self.shm_name:
            try:
                self.shm = SharedMemory(name=self.shm_name)
                self.shared_frame = np.ndarray(self.shm_shape, dtype=self.shm_dtype, buffer=self.shm.buf)
                logger.info(f"[{self.machine_id}] Connected to shared memory: {self.shm_name}")
            except Exception as e:
                logger.error(f"[{self.machine_id}] Failed to connect to shared memory: {e}")
                self.shared_frame = None

    def run(self):
        """Main worker loop"""
        logger.info(f"[{self.machine_id}] Camera Worker started - PID={self.pid}")
        self.running = True
        
        self._connect_shared_memory()
        
        cap = cv2.VideoCapture(self.camera_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize internal buffer
        
        # Retry connection logic
        while not cap.isOpened() and self.running:
            logger.warning(f"[{self.machine_id}] Failed to open camera, retrying in 5s...")
            time.sleep(5)
            cap = cv2.VideoCapture(self.camera_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
        frame_count = 0
        last_log = time.time()
        
        while self.running:
            try:
                # Check commands
                if not self.command_queue.empty():
                    cmd = self.command_queue.get_nowait()
                    if cmd == "STOP":
                        self.running = False
                        break
                
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"[{self.machine_id}] Failed to read frame, reconnecting...")
                    cap.release()
                    time.sleep(1)
                    cap = cv2.VideoCapture(self.camera_url)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    continue
                
                # Init ROI on first frame
                if not self.roi_initialized:
                    h, w = frame.shape[:2]
                    self._init_roi(w, h)
                
                # Draw ROI (Optional - maybe move to YOLO or UI to save processing here? 
                # But requirement said read image -> process. Let's keep raw frame clean if possible?
                # Actually, if we write to shared memory, we should write the RAW frame so YOLO gets clean input.
                # Visualization can happen later.)
                
                # Resize if needed to match shared memory shape
                if self.shared_frame is not None:
                    target_h, target_w = self.shm_shape[:2]
                    if frame.shape[:2] != (target_h, target_w):
                        frame = cv2.resize(frame, (target_w, target_h))
                    
                    # Write to shared memory (Zero-copy from Python perspective, but numpy does copy)
                    np.copyto(self.shared_frame, frame)
                    
                    # Notify YOLO (Send timestamp instead of frame)
                    if not self.frame_queue.full():
                        self.frame_queue.put(time.time())
                else:
                    # Fallback to Queue if SHM failed
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)

                frame_count += 1
                if time.time() - last_log > 10:
                    fps = frame_count / (time.time() - last_log)
                    logger.info(f"[{self.machine_id}] Camera FPS: {fps:.1f}")
                    frame_count = 0
                    last_log = time.time()
                
                # Limit FPS slightly to prevent busy loop if camera is too fast
                time.sleep(0.005)
                
            except Exception as e:
                logger.exception(f"[{self.machine_id}] Camera loop error: {e}")
                time.sleep(1)
        
        cap.release()
        if self.shm:
            self.shm.close()
        logger.info(f"[{self.machine_id}] Camera Worker stopped")