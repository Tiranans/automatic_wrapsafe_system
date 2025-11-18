"""IP Camera streaming worker"""
from multiprocessing import Process, Queue
from utils.logger import setup_logger
import cv2
import time
import config

logger = setup_logger('CameraWorker')

class CameraWorker(Process):
    def __init__(self, camera_url: str, frame_queue: Queue, command_queue: Queue, machine_id: str):
        super().__init__()
        self.camera_url = camera_url
        self.frame_queue = frame_queue
        self.command_queue = command_queue
        self.machine_id = machine_id  
        self.running = False
        
   
        self.frame_width = None
        self.frame_height = None
        self.roi_pixels = None
        self.roi_initialized = False

    def _init_roi(self, w: int, h: int):
        """Initialize ROI coordinates from first frame (called once)"""
        if self.machine_id == "A":
            roi_normalized = config.M1_DETECT_ROI
        elif self.machine_id == "B":
            roi_normalized = config.M2_DETECT_ROI
        else:
            logger.warning(f"Unknown machine_id: {self.machine_id}, using M1_DETECT_ROI")
            roi_normalized = config.M1_DETECT_ROI
        
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

    def run(self):
        logger.info(f"[Machine {self.machine_id}] Camera worker starting: {self.camera_url}")
        
        cap = cv2.VideoCapture(self.camera_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not cap.isOpened():
            logger.error(f"[Machine {self.machine_id}] Cannot open camera URL: {self.camera_url}")
            return

        self.running = True
        frame_count = 0
        last_log_time = time.time()
        
        while self.running:
            # Check STOP command
            try:
                while not self.command_queue.empty():
                    cmd = self.command_queue.get_nowait()
                    if cmd == "STOP":
                        logger.info(f"[Machine {self.machine_id}] Received STOP command")
                        self.running = False
                        break
            except Exception as e:
                logger.error(f"[Machine {self.machine_id}] Command queue error: {e}")

            if not self.running:
                break

            # Read frame
            ret, frame = cap.read()
            if not ret:
                logger.warning(f"[Machine {self.machine_id}] RTSP read failed (no frame)")
                time.sleep(0.1)
                continue

            frame_count += 1

            # Initialize ROI from first frame
            if not self.roi_initialized:
                h, w = frame.shape[:2]
                self._init_roi(w, h)

            # Draw ROI rectangle
            try:
                if config.DRAW_ROI:
                    x0, y0, x1, y1 = self.roi_pixels  
                    cv2.rectangle(
                        frame, 
                        (x0, y0), 
                        (x1, y1), 
                        config.ROI_COLOR_BGR, 
                        config.ROI_THICKNESS
                    )
                    cv2.putText(
                        frame, 
                        "ROI", 
                        (x0 + 6, max(20, y0 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.6, 
                        config.ROI_COLOR_BGR, 
                        2, 
                        cv2.LINE_AA
                    )
            except Exception as e:
                logger.error(f"[Machine {self.machine_id}] ROI drawing error: {e}")

            # Send frame to YOLO worker
            try:
                if self.frame_queue.full():
                    try:
                        _ = self.frame_queue.get_nowait()
                    except Exception:
                        pass
                
                self.frame_queue.put(frame)
                
            except Exception as e:
                logger.error(f"[Machine {self.machine_id}] Frame queue error: {e}")

            # Log FPS every 5 seconds
            now = time.time()
            if now - last_log_time >= 5.0:
                fps = frame_count / (now - last_log_time)
                logger.info(f"[Machine {self.machine_id}] Camera FPS: {fps:.2f}")
                frame_count = 0
                last_log_time = now

            time.sleep(0.001)

        cap.release()
        logger.info(f"[Machine {self.machine_id}] Camera worker stopped")