"""YOLO detection worker with pose keypoints checking"""
from multiprocessing import Process, Queue
from utils.logger import setup_logger
from ultralytics import YOLO
import numpy as np
import time
import config
import cv2
from collections import deque

logger = setup_logger('YOLOWorker')

class YOLOWorker(Process):
    def __init__(self, frame_queue: Queue, result_queue: Queue, command_queue: Queue, machine_id: int):
        super().__init__()
        self.frame_queue = frame_queue
        self.result_queue = result_queue
        self.command_queue = command_queue
        self.machine_id = machine_id
        self.running = False
        self.detection_history = deque(maxlen=getattr(config, "DETECTION_MEMORY_FRAMES", 10))
        
        # ✅ เพิ่มตัวแปรเก็บ ROI (คำนวณครั้งเดียว)
        self.frame_width = None
        self.frame_height = None
        self.roi_pixels = None
        self.roi_initialized = False

    def _init_roi(self, w: int, h: int):
        """Initialize ROI coordinates from first frame (called once)"""
        # เลือก ROI config ตาม machine_id
        roi_normalized = config.M1_DETECT_ROI if self.machine_id == 1 else config.M2_DETECT_ROI
        
        x0n, y0n, x1n, y1n = roi_normalized
        
        # ✅ คำนวณเป็น pixel coordinates (numpy array สำหรับ performance)
        self.roi_pixels = np.array([
            x0n * w,
            y0n * h,
            x1n * w,
            y1n * h
        ], dtype=np.float32)  # ใช้ float32 แทน float64 (เร็วกว่า)
        
        self.frame_width = w
        self.frame_height = h
        self.roi_initialized = True
        
        logger.info(
            f"[Machine {self.machine_id}] ROI initialized: "
            f"Frame={w}x{h}, "
            f"ROI=({self.roi_pixels[0]:.0f}, {self.roi_pixels[1]:.0f}, "
            f"{self.roi_pixels[2]:.0f}, {self.roi_pixels[3]:.0f})"
        )

    def _point_in_roi(self, x: float, y: float) -> bool:
        """Check if point (x,y) is inside ROI"""
        roi = self.roi_pixels
        return roi[0] <= x <= roi[2] and roi[1] <= y <= roi[3]

    def _inter_area(self, box_a, box_b) -> float:
        """Calculate intersection area between two boxes"""
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])
        iw = max(0.0, x2 - x1)
        ih = max(0.0, y2 - y1)
        return iw * ih

    def _check_keypoints_in_roi(self, keypoints):
        """Check if any person keypoints are inside ROI"""
        if keypoints is None or len(keypoints) == 0:
            return False, []
        
        check_indices = getattr(config, "KEYPOINTS_TO_CHECK", None)
        if check_indices is None:
            check_indices = list(range(17))
        
        detected_indices = []
        conf_th = getattr(config, "KEYPOINT_CONF_THRES", 0.25)
        
        for person_kpts in keypoints:
            for kpt_idx in check_indices:
                if kpt_idx >= len(person_kpts):
                    continue
                x, y, conf = person_kpts[kpt_idx]
                
                if conf > conf_th and self._point_in_roi(x, y):
                    if kpt_idx not in detected_indices:
                        detected_indices.append(kpt_idx)
        
        return len(detected_indices) > 0, detected_indices

    def _encode_frame_jpeg(self, frame_bgr):
        """Resize(optional) and encode BGR frame to JPEG bytes"""
        try:
            max_w = getattr(config, "RESULT_FRAME_MAX_WIDTH", None)
            if max_w and frame_bgr.shape[1] > max_w:
                scale = max_w / float(frame_bgr.shape[1])
                new_size = (int(frame_bgr.shape[1] * scale), int(frame_bgr.shape[0] * scale))
                frame_bgr = cv2.resize(frame_bgr, new_size, interpolation=cv2.INTER_AREA)
            q = int(getattr(config, "RESULT_JPEG_QUALITY", 85))
            ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), q])
            return buf.tobytes() if ok else None
        except Exception:
            return None

    def _draw_overlay(self, frame_bgr, result_obj, person_in_roi):
        """Draw ROI, BBoxes only (NO Skeleton, NO Keypoints)"""
        vis = frame_bgr.copy()
        
        # Draw ROI
        if getattr(config, "DRAW_ROI", True):
            color = config.COLOR_ALARM if person_in_roi else config.COLOR_NORMAL
            x0, y0, x1, y1 = self.roi_pixels.astype(int)  # ← ใช้ค่าที่เก็บไว้
            cv2.rectangle(vis, (x0, y0), (x1, y1), color, max(2, config.VIS_THICKNESS))
        
        # Draw Bounding Boxes
        if getattr(config, "DRAW_BBOX", True) and hasattr(result_obj, "boxes") and result_obj.boxes is not None:
            boxes = result_obj.boxes.xyxy.cpu().numpy().astype(int)
            for (x0, y0, x1, y1) in boxes:
                cv2.rectangle(vis, (x0, y0), (x1, y1), config.COLOR_BOX, config.VIS_THICKNESS)
        
        return vis

    def run(self):
        logger.info(f"[Machine {self.machine_id}] YOLO worker started")
        
        try:
            logger.info(f"[Machine {self.machine_id}] Loading model: {config.YOLO_MODEL_PATH}")
            model = YOLO(config.YOLO_MODEL_PATH)
            is_pose_model = 'pose' in config.YOLO_MODEL_PATH.lower()
            logger.info(f"[Machine {self.machine_id}] Model loaded (pose={is_pose_model})")
        except Exception as e:
            logger.error(f"[Machine {self.machine_id}] Load model error: {e}")
            return

        self.running = True

        while self.running:
            try:
                cmd = self.command_queue.get_nowait()
                if cmd == "STOP":
                    break
            except:
                pass

            frame = None
            while not self.frame_queue.empty():
                try:
                    frame = self.frame_queue.get_nowait()
                except:
                    break
            
            if frame is None:
                time.sleep(0.0001)
                continue

            
            if not self.roi_initialized:
                h, w = frame.shape[:2]
                self._init_roi(w, h)

            try:
                results = model(frame, conf=config.YOLO_CONFIDENCE, verbose=False)
                r = results[0]
                
                person_in_roi_raw = False
                person_count = 0
                detected_keypoints = []

                # Check pose keypoints
                if is_pose_model and hasattr(r, 'keypoints') and r.keypoints is not None:
                    kpts = r.keypoints.xy.cpu().numpy()
                    kpts_conf = r.keypoints.conf.cpu().numpy()
                    
                    if len(kpts) > 0:
                        person_count = len(kpts)
                        kpts_full = np.zeros((len(kpts), 17, 3))
                        kpts_full[:, :, :2] = kpts
                        kpts_full[:, :, 2] = kpts_conf
                        
                        person_in_roi_raw, detected_keypoints = self._check_keypoints_in_roi(kpts_full)
                
                # Fallback to bounding box check
                if not person_in_roi_raw and getattr(config, "FALLBACK_TO_BBOX", True):
                    if r.boxes is not None:
                        boxes = r.boxes.xyxy.cpu().numpy()
                        clss  = r.boxes.cls.cpu().numpy().astype(int)
                        names = r.names if hasattr(r, "names") else model.names

                        for b, c in zip(boxes, clss):
                            is_person = False
                            if isinstance(names, dict):
                                is_person = (names.get(c, "") == "person")
                            else:
                                is_person = (c == 0)
                            if not is_person:
                                continue
                            
                            if person_count == 0:
                                person_count = len([cls for cls in clss if (names.get(cls, "") == "person" if isinstance(names, dict) else cls == 0)])
                            
                            ba = max(1.0, (b[2]-b[0]) * (b[3]-b[1]))
                            ia = self._inter_area(b, self.roi_pixels)  # ← ใช้ค่าที่เก็บไว้
                            ratio = ia / ba
                            if ratio >= config.INTERSECT_THRESHOLD:
                                person_in_roi_raw = True
                                break

                # Temporal smoothing
                person_in_roi_final = person_in_roi_raw
                if getattr(config, "USE_TEMPORAL_SMOOTHING", True):
                    self.detection_history.append(person_in_roi_raw)
                    recent_detections = sum(self.detection_history)
                    min_detections = getattr(config, "MIN_DETECTIONS_FOR_ALARM", 3)
                    person_in_roi_final = (recent_detections >= min_detections)

                
                


                payload = {
                    'machine_id': self.machine_id,
                    'person_in_roi': person_in_roi_final,
                    'person_count': person_count,
                    'detected_keypoints': detected_keypoints,
                    'ts': time.time()
                }
                
                if getattr(config, "ATTACH_RESULT_FRAME", True):
                    if getattr(config, "DRAW_OVERLAY", True):
                        vis = self._draw_overlay(frame, r, person_in_roi_final)
                    else:
                        vis = frame
                        
                    jpg = self._encode_frame_jpeg(vis)
                    if jpg is not None:
                        payload['frame_jpeg'] = jpg

                try:
                    self.result_queue.put_nowait(payload)
                except:
                    pass

            except Exception as e:
                logger.exception(f"[Machine {self.machine_id}] Detection error: {e}")

        logger.info(f"[Machine {self.machine_id}] YOLO worker stopped")