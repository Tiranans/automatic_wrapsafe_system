"""YOLO detection worker with pose keypoints checking and dynamic frame skip"""
from multiprocessing import Process, Queue
from multiprocessing.shared_memory import SharedMemory
from utils.logger import setup_logger
from ultralytics import YOLO
import numpy as np
import time
import config
import cv2
import traceback 
from collections import deque
from queue import Empty

logger = setup_logger('YOLOWorker')

class YOLOWorker(Process):
    def __init__(
        self, 
        frame_queue: Queue, 
        result_queue: Queue, 
        command_queue: Queue, 
        machine_id: str,
        shm_name: str = None,
        shm_shape: tuple = None,
        shm_dtype = None,
        di_status_queue: Queue = None
    ):
        super().__init__()
        self.frame_queue = frame_queue
        self.result_queue = result_queue
        self.command_queue = command_queue
        self.machine_id = machine_id
        self.running = False
        self.detection_history = deque(maxlen=getattr(config, "DETECTION_MEMORY_FRAMES", 10))
        
        # Shared Memory Config
        self.shm_name = shm_name
        self.shm_shape = shm_shape
        self.shm_dtype = shm_dtype
        self.shm = None
        self.shared_frame = None
        
        # ROI
        self.frame_width = None
        self.frame_height = None
        self.roi_pixels = None
        self.roi_initialized = False
        
        # Optimization State
        self.frame_count = 0
        self.last_person_detected = False
        self.last_person_count = 0
        self.last_results = None
        
        # Dynamic Frame Skip - แก้ไขให้ใช้ค่าจาก config
        self.base_skip = config.YOLO_FRAME_SKIP
        self.skip_when_no_person = max(1, self.base_skip * 3)  # 3x slower when no person
        self.skip_when_person = self.base_skip  # Use config value when person detected
        self.adaptive_skip = self.base_skip
        
        # DI Status Queue
        self.di_status_queue = di_status_queue
        self.di_enabled = True  # Default to enabled
        
        # Roll Clamp Detection State
        self.last_roll_clamp_detected = False
        self.roll_clamp_released_time = None
        self.auto_start_delay_seconds = 180  # 3 minutes = 180 seconds
        self.auto_start_triggered = False
        
        # OBB Clamp Detection State
        self.obb_frame_count = 0
        self.last_clamp_detected = False
        self.last_clamp_confidence = 0.0
        self.last_clamp_bbox = None
        self.last_clamp_angle = None
        self.last_paper_roll_detected = False  # Added persistence for paper roll
        
        logger.info(f"[{self.machine_id}] Frame skip config: base={self.base_skip}, no_person={self.skip_when_no_person}, person={self.skip_when_person}")

    def _init_roi(self, w: int, h: int):
        """Initialize ROI coordinates from first frame (called once)"""
        roi_normalized = config.A1_DETECT_ROI if self.machine_id == "A" else config.B2_DETECT_ROI
        
        x0n, y0n, x1n, y1n = roi_normalized
        
        self.roi_pixels = np.array([
            x0n * w,
            y0n * h,
            x1n * w,
            y1n * h
        ], dtype=np.float32)
        
        self.frame_width = w
        self.frame_height = h
        self.roi_initialized = True
        
        roi_width = self.roi_pixels[2] - self.roi_pixels[0]
        roi_height = self.roi_pixels[3] - self.roi_pixels[1]
        
        # logger.info(
        #     f"[Machine {self.machine_id}] ROI initialized: "
        #     f"Frame={w}x{h}, "
        #     f"ROI=({int(self.roi_pixels[0])},{int(self.roi_pixels[1])}) to ({int(self.roi_pixels[2])},{int(self.roi_pixels[3])}), "
        #     f"Size={int(roi_width)}x{int(roi_height)}"
        # )

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
        
        check_indices = config.KEYPOINTS_TO_CHECK
        if check_indices is None:
            check_indices = list(range(17))
        
        detected_indices = []
        conf_th = config.KEYPOINT_CONF_THRES
        min_kpts_in_roi = config.KEYPOINTS_MIN_IN_ROI
        
        for person_kpts in keypoints:
            person_detected_indices = []
            for kpt_idx in check_indices:
                if kpt_idx >= len(person_kpts):
                    continue
                x, y, conf = person_kpts[kpt_idx]
                
                if conf > conf_th and self._point_in_roi(x, y):
                    if kpt_idx not in person_detected_indices:
                        person_detected_indices.append(kpt_idx)
            
            # ต้องมี keypoints ตามที่กำหนด
            if len(person_detected_indices) >= min_kpts_in_roi:
                detected_indices.extend(person_detected_indices)
                logger.debug(f"[{self.machine_id}] Person has {len(person_detected_indices)} keypoints in ROI: {person_detected_indices}")
        
        return len(detected_indices) >= min_kpts_in_roi, detected_indices

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

    def _detect_roll_clamp(self, frame, obb_results=None) -> bool:
        """Detect Roll clamp using OBB results (Class 0: forklift_clamp)"""
        if not config.ENABLE_ROLL_CLAMP_DETECTION:
            return False
            
        if obb_results is not None:
            if hasattr(obb_results, 'obb') and obb_results.obb is not None and len(obb_results.obb) > 0:
                obb_data = obb_results.obb
                if hasattr(obb_data, 'cls') and obb_data.cls is not None:
                    class_ids = obb_data.cls.cpu().numpy().astype(int)
                    confs = obb_data.conf.cpu().numpy()
                    
                    # Check for class 0 (forklift_clamp) with high confidence
                    for idx, (cid, conf) in enumerate(zip(class_ids, confs)):
                        if cid == config.OBB_CLAMP_CLASS_ID and conf >= config.CLAMP_PRESENT_THRESHOLD:
                            logger.warning(f"[{self.machine_id}] ROLL CLAMP DETECTED via OBB Model! (conf={conf:.2f})")
                            return True
        return False

    def _detect_paper_roll(self, frame, obb_results=None) -> bool:
        """Detect paper roll using OBB results (Class 1 or 2)"""
        if not config.ENABLE_PAPER_ROLL_DETECTION:
            return False

        if obb_results is not None:
            if hasattr(obb_results, 'obb') and obb_results.obb is not None and len(obb_results.obb) > 0:
                obb_data = obb_results.obb
                if hasattr(obb_data, 'cls') and obb_data.cls is not None:
                    class_ids = obb_data.cls.cpu().numpy().astype(int)
                    # Class 1: paper_roll_small, Class 2: paper_roll_big
                    if any(cid in [1, 2] for cid in class_ids):
                        logger.warning(f"[{self.machine_id}] PAPER ROLL DETECTED via OBB Model!")
                        return True
        return False

    def run(self):
        """Main worker loop"""
        logger.info(f"[{self.machine_id}] YOLO Worker started - PID={self.pid}")
        self.running = True
        
        # Load Pose model with retry
        model = None
        while self.running and model is None:
            try:
                model = YOLO(config.YOLO_MODEL_PATH)
                logger.info(f"[{self.machine_id}] YOLO Pose model loaded: {config.YOLO_MODEL_PATH}")
                is_pose_model = 'pose' in config.YOLO_MODEL_PATH.lower()
            except Exception as e:
                logger.error(f"[{self.machine_id}] Failed to load YOLO Pose model: {e}")
                time.sleep(5)
        
        if not self.running:
            return
        
        # Load OBB model if enabled
        obb_model = None
        if config.ENABLE_OBB_CLAMP_DETECTION:
            while self.running and obb_model is None:
                try:
                    obb_model = YOLO(config.YOLO_OBB_MODEL_PATH)
                    logger.info(f"[{self.machine_id}] YOLO OBB model loaded: {config.YOLO_OBB_MODEL_PATH}")
                except Exception as e:
                    logger.error(f"[{self.machine_id}] Failed to load YOLO OBB model: {e}")
                    time.sleep(5)
            
            if not self.running:
                return

        self._connect_shared_memory()
        
        while self.running:
            try:
                # Check commands
                if not self.command_queue.empty():
                    cmd = self.command_queue.get_nowait()
                    if cmd == "STOP":
                        self.running = False
                        break
                
                # Update DI status if available
                if self.di_status_queue:
                    try:
                        while not self.di_status_queue.empty():
                            di_status = self.di_status_queue.get_nowait()
                            # logger.info(f"[{self.machine_id}] DI Status received: {di_status}")
                            if self.di_enabled != di_status:
                                logger.info(f"[{self.machine_id}] DI Status changed: {self.di_enabled} -> {di_status}")
                                self.di_enabled = di_status
                    except Empty:
                        pass
                
                # Get frame (or signal)
                try:
                    item = self.frame_queue.get(timeout=0.1)
                except Empty:
                    continue
                
                frame = None
                ts = time.time()
                
                if isinstance(item, float): # coppy from SHM
                    if self.shared_frame is not None:
                        frame = self.shared_frame.copy()
                        ts = item
                    else:
                        logger.warning(f"[{self.machine_id}] Received timestamp but SHM not connected")
                        continue
                else:
                    frame = item
                
                if frame is None:
                    continue

                # Init ROI
                if not self.roi_initialized:
                    h, w = frame.shape[:2]
                    self._init_roi(w, h)

                # Check if detection is enabled via DI
                di_detection_disabled = False
                logger.debug(f"[{self.machine_id}] DI Enabled: {self.di_enabled}")
                if config.ENABLE_DETECTION_ON_DI :
                    if not self.di_enabled:
                        di_detection_disabled = True

                # If DI is OFF, skip YOLO but still send frame
                if di_detection_disabled:
                    result_data = {
                        'person_in_roi': False,
                        'person_count': 0,
                        'ts': ts,
                        'raw_detected': False,
                        'roll_clamp_detected': False,
                        'paper_roll_detected': False
                    }

                    # Still send frame for web display
                    if config.USE_RESULT_FRAME:
                        vis_frame = frame.copy()
                        
                        if config.DRAW_ROI:
                            rx1, ry1, rx2, ry2 = self.roi_pixels.astype(int)
                            cv2.rectangle(vis_frame, (rx1, ry1), (rx2, ry2), (128, 128, 128), 2)
                            cv2.putText(vis_frame, "DETECTION DISABLED", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        
                        # Display Roll Clamp status
                        if config.ENABLE_ROLL_CLAMP_DETECTION:
                            clamp_status = "CLAMP: YES" if result_data.get('roll_clamp_detected', False) else "CLAMP: NO"
                            clamp_color = (0, 255, 255) if result_data.get('roll_clamp_detected', False) else (128, 128, 128)
                            cv2.putText(vis_frame, clamp_status, (10, 60), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, clamp_color, 2)
                        
                        # Display Paper Roll status
                        if config.ENABLE_PAPER_ROLL_DETECTION:
                            paper_status = "PAPER ROLL: YES" if result_data.get('paper_roll_detected', False) else "PAPER ROLL: NO"
                            paper_color = (255, 255, 0) if result_data.get('paper_roll_detected', False) else (255, 0, 255)
                            cv2.putText(vis_frame, paper_status, (10, 90), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, paper_color, 2)
                        
                        vis_frame = cv2.resize(vis_frame, (config.CAMERA_DISPLAY_WIDTH, config.CAMERA_DISPLAY_HEIGHT))
                        _, jpg = cv2.imencode('.jpg', vis_frame, [int(cv2.IMWRITE_JPEG_QUALITY), config.RESULT_JPEG_QUALITY])
                        result_data['frame_jpeg'] = jpg.tobytes()
                    
                    try:
                        self.result_queue.put_nowait(result_data)
                    except:
                        pass
                    continue

                # Dynamic Frame Skipping Logic
                self.frame_count += 1
                
                if self.last_person_detected:
                    self.adaptive_skip = self.skip_when_person
                else:
                    self.adaptive_skip = self.skip_when_no_person
                
                should_infer = (self.frame_count % max(1, self.adaptive_skip) == 0)
                
                # Inference
                if should_infer:
                    # logger.info(f"[{self.machine_id}]  Running YOLO inference on frame {self.frame_count} (skip={self.adaptive_skip})")
                    
                    results = model(
                        frame, 
                        verbose=False,  # Disable verbose output mean disable print 
                        conf=config.YOLO_CONFIDENCE,
                        imgsz= config.YOLO_IMG_SIZE,
                        half=config.YOLO_HALF_PRECISION
                    )
                    
                    person_detected = False
                    person_count = 0
                    keypoints = []
                    
                    r = results[0]
                    self.last_results = r
                    
                    # Log raw YOLO results
                    total_detections = len(r.boxes) if r.boxes is not None else 0
                    # logger.info(f"[{self.machine_id}] YOLO found {total_detections} objects")
                    
                    # Check pose keypoints
                    if is_pose_model and hasattr(r, 'keypoints') and r.keypoints is not None:
                        kpts = r.keypoints.xy.cpu().numpy()
                        kpts_conf = r.keypoints.conf.cpu().numpy()
                        
                        if len(kpts) > 0:
                            person_count = len(kpts)
                            kpts_full = np.zeros((len(kpts), 17, 3))
                            kpts_full[:, :, :2] = kpts
                            kpts_full[:, :, 2] = kpts_conf
                            
                            person_detected, keypoints = self._check_keypoints_in_roi(kpts_full)
                            logger.info(f"[{self.machine_id}] Keypoint check: {person_count} person(s), in_roi={person_detected}, kpts={keypoints}")
                    
                    # Fallback to bounding box check
                    if not person_detected and config.FALLBACK_TO_BBOX:
                        if r.boxes is not None and len(r.boxes) > 0:
                            boxes = r.boxes.xyxy.cpu().numpy()
                            clss  = r.boxes.cls.cpu().numpy().astype(int)
                            confs = r.boxes.conf.cpu().numpy()
                            names = r.names if hasattr(r, "names") else model.names

                            for idx, (b, c, conf) in enumerate(zip(boxes, clss, confs)):
                                # ตรวจสอบว่าเป็น person 
                                is_person = False
                                if isinstance(names, dict):
                                    class_name = names.get(c, "")
                                    is_person = (class_name.lower() == "person")
                                else:
                                    # สำหรับ COCO dataset, person = class 0
                                    is_person = (c == 0)
                                    class_name = "person" if c == 0 else f"class_{c}"
                                
                                # ถ้าไม่ใช่คน ให้ log และข้าม
                                if not is_person:
                                    # logger.debug(f"[{self.machine_id}] Box {idx}: {class_name}, conf={conf:.2f}, is_person=False - SKIP")
                                    continue
                                
                                # นับจำนวนคน (นับเฉพาะ class person เท่านั้น)
                                if person_count == 0:
                                    if isinstance(names, dict):
                                        person_count = sum(1 for cls in clss if names.get(cls, "").lower() == "person")
                                    else:
                                        person_count = sum(1 for cls in clss if cls == 0)
                                
                                # Calculate intersection ratio
                                ba = max(1.0, (b[2]-b[0]) * (b[3]-b[1]))
                                ia = self._inter_area(b, self.roi_pixels)
                                ratio = ia / ba
                                
                                box_str = f"({int(b[0])},{int(b[1])}) to ({int(b[2])},{int(b[3])})"
                                logger.info(f"[{self.machine_id}] Person box {idx}: {box_str}, conf={conf:.2f}, overlap={ratio:.3f} (threshold={config.INTERSECT_THRESHOLD})")
                                
                                # เช็ค ratio และ confidence
                                if ratio >= config.INTERSECT_THRESHOLD:
                                    person_detected = True
                                    logger.warning(f"[{self.machine_id}]  PERSON DETECTED IN ROI! (overlap={ratio:.3f}, conf={conf:.2f})")
                                    break
                                else:
                                    logger.debug(f"[{self.machine_id}] Person box {idx} overlap too low: {ratio:.3f} < {config.INTERSECT_THRESHOLD}")
                            
                            if not person_detected and person_count > 0:
                                logger.info(f"[{self.machine_id}] Found {person_count} person(s) but none overlap ROI enough (>{config.INTERSECT_THRESHOLD*100:.0f}%)")
                    
                    self.last_person_detected = person_detected
                    self.last_person_count = person_count
                
                else:
                    # Reuse last detection result
                    person_detected = self.last_person_detected
                    person_count = self.last_person_count
                    logger.debug(f"[{self.machine_id}] Frame {self.frame_count}: Reusing last result (detected={person_detected})")
                
                # Temporal smoothing
                self.detection_history.append(person_detected)
                detection_sum = sum(self.detection_history)
                
                if config.USE_TEMPORAL_SMOOTHING:
                    final_detected = (detection_sum >= config.MIN_DETECTIONS_FOR_ALARM)
                    logger.info(f"[{self.machine_id}] Temporal smoothing: {detection_sum}/{len(self.detection_history)} >= {config.MIN_DETECTIONS_FOR_ALARM} → {final_detected}")
                else:
                    final_detected = person_detected
                
                # Prepare result
                result_data = {
                    'person_in_roi': final_detected,
                    'person_count': person_count,
                    'ts': ts,
                    'raw_detected': person_detected
                }

                # Encode clean frame for production capture (no overlays)
                if config.PRODUCTION_CAPTURE_ENABLED:
                    try:
                        clean_frame_resized = cv2.resize(frame, (config.CAMERA_DISPLAY_WIDTH, config.CAMERA_DISPLAY_HEIGHT))
                        _, clean_jpg = cv2.imencode('.jpg', clean_frame_resized, [int(cv2.IMWRITE_JPEG_QUALITY), config.RESULT_JPEG_QUALITY])
                        result_data['original_frame_jpeg'] = clean_jpg.tobytes()
                    except Exception as e:
                        logger.error(f"[{self.machine_id}] Failed to encode original frame: {e}")
                
                # OBB Detection (Independent of Person Detection)
                clamp_detected = self.last_clamp_detected
                clamp_confidence = self.last_clamp_confidence
                clamp_bbox = self.last_clamp_bbox
                clamp_angle = self.last_clamp_angle
                paper_roll_detected = self.last_paper_roll_detected # Use persistent state

                if config.ENABLE_OBB_CLAMP_DETECTION and obb_model:
                    self.obb_frame_count += 1
                    should_run_obb = (self.obb_frame_count % max(1, config.YOLO_OBB_FRAME_SKIP) == 0)
                    
                    if should_run_obb:
                        try:
                            # Inference
                            obb_results = obb_model(
                                frame,
                                verbose=False,
                                conf=config.YOLO_OBB_CONFIDENCE,
                                imgsz=config.YOLO_IMG_SIZE,
                                half=config.YOLO_HALF_PRECISION
                            )
                            
                            if obb_results and len(obb_results) > 0:
                                obb_r = obb_results[0]
                                
                                # Detect Paper Roll via OBB
                                paper_roll_detected = self._detect_paper_roll(frame, obb_results=obb_r)

                                # Detect Roll Clamp via OBB
                                clamp_detected = self._detect_roll_clamp(frame, obb_results=obb_r)
                                
                                # If clamp detected, extract detailed OBB data for visualization
                                if clamp_detected:
                                    obb_data = obb_r.obb
                                    class_ids = obb_data.cls.cpu().numpy().astype(int)
                                    confs = obb_data.conf.cpu().numpy()
                                    
                                    # Find the best clamp instance (Class 0)
                                    best_idx = -1
                                    max_conf = 0
                                    for idx, (cid, conf) in enumerate(zip(class_ids, confs)):
                                        if cid == config.OBB_CLAMP_CLASS_ID and conf > max_conf:
                                            max_conf = conf
                                            best_idx = idx
                                    
                                    if best_idx != -1:
                                        clamp_confidence = float(max_conf)
                                        if hasattr(obb_data, 'xyxyxyxy'):
                                            clamp_bbox = obb_data.xyxyxyxy.cpu().numpy()[best_idx].flatten().tolist()
                                        if hasattr(obb_data, 'xywhr'):
                                            clamp_angle = float(np.degrees(obb_data.xywhr.cpu().numpy()[best_idx][4]))
                            
                            # Update persistency
                            self.last_clamp_detected = clamp_detected
                            self.last_clamp_confidence = clamp_confidence
                            self.last_clamp_bbox = clamp_bbox
                            self.last_clamp_angle = clamp_angle
                            self.last_paper_roll_detected = paper_roll_detected # Save state
                            
                        except Exception as e:
                            logger.error(f"[{self.machine_id}] OBB detection error: {e}")
                            traceback.print_exc()
                
                # Update main result_data
                result_data['paper_roll_detected'] = paper_roll_detected
                roll_clamp_detected = clamp_detected
                result_data['roll_clamp_detected'] = roll_clamp_detected
                result_data['clamp_confidence'] = clamp_confidence
                result_data['clamp_bbox'] = clamp_bbox
                result_data['clamp_angle'] = clamp_angle

                # Update auto-start logic based on roll clamp
                if config.ENABLE_ROLL_CLAMP_DETECTION:
                    # Check if Roll clamp was released (from detected → not detected)
                    if self.last_roll_clamp_detected and not roll_clamp_detected:
                        self.roll_clamp_released_time = time.time()
                        self.auto_start_triggered = False
                        logger.warning(f"[{self.machine_id}]  ROLL CLAMP RELEASED! Starting {self.auto_start_delay_seconds}s delay timer for auto start")
                    
                    # Reset countdown if Roll clamp is detected again (forklift returns)
                    if roll_clamp_detected and self.roll_clamp_released_time is not None:
                        logger.warning(f"[{self.machine_id}]  Roll Clamp detected again - Resetting auto start countdown")
                        self.roll_clamp_released_time = None
                        self.auto_start_triggered = False
                    
                    # Update countdown display
                    if self.last_roll_clamp_detected and not roll_clamp_detected and self.roll_clamp_released_time is not None:
                         # Still counting down
                         pass

                    self.last_roll_clamp_detected = roll_clamp_detected
                    result_data['auto_start_countdown'] = (
                        self.auto_start_delay_seconds - (time.time() - self.roll_clamp_released_time)
                        if self.roll_clamp_released_time and not self.auto_start_triggered
                        else None
                    )
                
                # ========== AUTO START SIGNAL CHECK ==========
                # Check after OBB detection to verify both person and clamp status
                if self.roll_clamp_released_time is not None and not self.auto_start_triggered:
                    elapsed = time.time() - self.roll_clamp_released_time
                    if elapsed >= self.auto_start_delay_seconds:
                        # Check ALL conditions:
                        # 1. No person in ROI
                        # 2. No clamp detected (OBB)
                        
                        can_auto_start = True
                        cancel_reason = []
                        
                        if final_detected:
                            can_auto_start = False
                            cancel_reason.append(f"Person in ROI (count: {person_count})")
                        
                        if config.ENABLE_OBB_CLAMP_DETECTION and clamp_detected:
                            can_auto_start = False
                            cancel_reason.append(f"Clamp present (conf: {clamp_confidence:.2f})")
                        
                        if can_auto_start:
                            self.auto_start_triggered = True
                            logger.warning(f"[{self.machine_id}]  AUTO START TRIGGERED! (after {elapsed:.1f}s delay)")
                            logger.info(f"[{self.machine_id}] Auto start conditions: Person={final_detected}, Clamp={clamp_detected}")
                            result_data['auto_start_signal'] = True
                        else:
                            logger.warning(f"[{self.machine_id}]  AUTO START DELAYED - {', '.join(cancel_reason)}")
                            # Reset timer to wait for conditions to clear
                            self.roll_clamp_released_time = time.time()
                
                # Attach frame if needed
                if config.USE_RESULT_FRAME:
                    vis_frame = frame.copy()
                    
                    if config.DRAW_ROI:
                        rx1, ry1, rx2, ry2 = self.roi_pixels.astype(int)
                        roi_color = (0, 255, 0) if final_detected else config.ROI_COLOR_BGR
                        cv2.rectangle(vis_frame, (rx1, ry1), (rx2, ry2), roi_color, config.ROI_THICKNESS)
                    
                    if self.last_results:
                        res = self.last_results
                        if hasattr(res, 'boxes') and res.boxes is not None:
                            for box in res.boxes:
                                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                                cv2.rectangle(vis_frame, (x1, y1), (x2, y2), config.COLOR_BOX, 2)
                    
                    # Add detection status text
                    status_text = f"Person: {final_detected} (raw:{person_detected}) [{detection_sum}/{len(self.detection_history)}]"
                    cv2.putText(vis_frame, status_text, (10, 30), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if final_detected else (255, 255, 255), 2)
                    
                    # Display Roll Clamp status
                    if config.ENABLE_ROLL_CLAMP_DETECTION:
                        clamp_status = "CLAMP: YES" if result_data.get('roll_clamp_detected', False) else "CLAMP: NO"
                        clamp_color = (0, 255, 255) if result_data.get('roll_clamp_detected', False) else (128, 128, 128)
                        cv2.putText(vis_frame, clamp_status, (10, 60), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, clamp_color, 2)
                        
                        # Display countdown if active
                        countdown = result_data.get('auto_start_countdown', None)
                        if countdown is not None and countdown > 0:
                            countdown_text = f"Auto Start in: {countdown:.0f}s"
                            cv2.putText(vis_frame, countdown_text, (10, 85), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    
                    # Display Paper Roll status
                    if config.ENABLE_PAPER_ROLL_DETECTION:
                        paper_status = "PAPER ROLL: YES" if result_data.get('paper_roll_detected', False) else "PAPER ROLL: NO"
                        paper_color = (255, 255, 0) if result_data.get('paper_roll_detected', False) else (128, 128, 128)
                        y_pos = 110 if result_data.get('auto_start_countdown', None) is not None else 85
                        cv2.putText(vis_frame, paper_status, (10, y_pos), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, paper_color, 2)
                    
                    # Display OBB Clamp status
                    if config.ENABLE_OBB_CLAMP_DETECTION:
                        clamp_status = f"OBB CLAMP: {'YES' if result_data.get('roll_clamp_detected', False) else 'NO'}"
                        if result_data.get('roll_clamp_detected', False):
                            clamp_conf = result_data.get('clamp_confidence', 0.0)
                            clamp_ang = result_data.get('clamp_angle', 0.0)
                            clamp_status += f" ({clamp_conf:.2f}, {clamp_ang:.0f}°)"
                        clamp_color = (0, 165, 255) if result_data.get('roll_clamp_detected', False) else (128, 128, 128)
                        y_pos_clamp = 135 if result_data.get('auto_start_countdown', None) is not None else 110
                        cv2.putText(vis_frame, clamp_status, (10, y_pos_clamp), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, clamp_color, 2)
                        
                        # Draw OBB bounding box if detected
                        if result_data.get('roll_clamp_detected', False) and result_data.get('clamp_bbox') is not None:
                            bbox = result_data.get('clamp_bbox')
                            if len(bbox) == 8:  # xyxyxyxy format
                                pts = np.array([
                                    [bbox[0], bbox[1]],
                                    [bbox[2], bbox[3]],
                                    [bbox[4], bbox[5]],
                                    [bbox[6], bbox[7]]
                                ], np.int32)
                                pts = pts.reshape((-1, 1, 2))
                                cv2.polylines(vis_frame, [pts], True, (0, 165, 255), 3)
                    
                    vis_frame = cv2.resize(vis_frame, (config.CAMERA_DISPLAY_WIDTH, config.CAMERA_DISPLAY_HEIGHT))
                    
                    _, jpg = cv2.imencode('.jpg', vis_frame, [int(cv2.IMWRITE_JPEG_QUALITY), config.RESULT_JPEG_QUALITY])
                    result_data['frame_jpeg'] = jpg.tobytes()
                
                # Send result
                try:
                    self.result_queue.put_nowait(result_data)
                except:
                    pass
                
            except Exception as e:
                logger.error(f"[{self.machine_id}] YOLO loop error: {e}")
                traceback.print_exc()
                continue
        
        # Cleanup
        if self.shm:
            try:
                self.shm.close()
            except:
                pass
        
        logger.info(f"[{self.machine_id}] YOLO Worker stopped")