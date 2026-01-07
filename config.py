"""Configuration for BM9 WrapSafe System"""

# Camera Authentication
CAMERA_USERNAME = "admin"    
CAMERA_PASSWORD = "admin12345"   

# Machine A Configuration
MACHINEA_CAMERA_IP = "192.168.1.31"
MACHINEA_CAMERA_URL = f"rtsp://{CAMERA_USERNAME}:{CAMERA_PASSWORD}@{MACHINEA_CAMERA_IP}"

# Machine B Configuration
MACHINEB_CAMERA_IP = "192.168.1.32"
MACHINEB_CAMERA_URL = f"rtsp://{CAMERA_USERNAME}:{CAMERA_PASSWORD}@{MACHINEB_CAMERA_IP}"

CAMERA_DISPLAY_WIDTH = 640
CAMERA_DISPLAY_HEIGHT = 480

# Modbus Configuration
MODBUS_PORT = 501
MODBUS_TIMEOUT = 5
MODBUS_UNIT_ID = 1  

# Digital I/O address ranges (0-based for Modbus)
DO_START_ADDRESS = 0
DO_END_ADDRESS = 15

DI_A_START_ADDRESS = 0
DI_A_END_ADDRESS = 7

DI_B_START_ADDRESS = 8
DI_B_END_ADDRESS = 15

# YOLO / Detection
YOLO_MODEL_PATH = "models/yolov8n-pose.pt"
YOLO_CONFIDENCE = 0.15  
YOLO_FRAME_SKIP = 1
YOLO_IMG_SIZE = 640 
YOLO_HALF_PRECISION = False 

# ROI (normalized 0..1: x0,y0,x1,y1)
A1_DETECT_ROI = (0.15, 0.02, 0.85, 1.00)  # Machine A
B2_DETECT_ROI = (0.10, 0.02, 0.85, 1.00)  # Machine B
ROI_COLOR_BGR = (255, 0, 0)
ROI_THICKNESS = 10

# Auto stop config
AUTO_STOP_ON_PERSON = True
STOP_COOLDOWN_SEC = 3.0
INTERSECT_THRESHOLD = 0.05  # 5% overlap to consider as intersecting

KEYPOINTS_TO_CHECK = [5, 6, 7, 8,9,10, 11, 12, 13, 14,15,16] 
KEYPOINT_CONF_THRES = 0.25  
KEYPOINTS_IN_ROI_FRACTION = 0.0
KEYPOINTS_MIN_IN_ROI = 1  

FALLBACK_TO_BBOX = True  

# Detection Enable Condition (based on Digital Input)
ENABLE_DETECTION_ON_DI = True  # Only detect when specific DI is ON
DETECTION_ENABLE_DI_ADDR_A = 0  # Machine A: Check_roll (addr 0)
DETECTION_ENABLE_DI_ADDR_B = 8  # Machine B: Check_roll (addr 8)

# Roll Clamp Detection (using white/gray metal color detection)
ENABLE_ROLL_CLAMP_DETECTION = True
ROLL_CLAMP_METAL_GRAY_THRESHOLD = 0.05  # 5% gray/white metal pixels = clamp detected
ROLL_CLAMP_AUTO_START_DELAY = 180  # seconds (3 minutes) - delay after clamp release before auto start

# Paper Roll Detection (using white/cream/brown color detection)
ENABLE_PAPER_ROLL_DETECTION = True
PAPER_ROLL_COLOR_RATIO_THRESHOLD = 0.3  # 30% white/cream/brown pixels = paper roll detected

# YOLO OBB Clamp Detection
ENABLE_OBB_CLAMP_DETECTION = True
YOLO_OBB_MODEL_PATH = "models/yolo-obb-clamp.pt"
YOLO_OBB_CONFIDENCE = 0.25  # Confidence threshold for OBB detection
YOLO_OBB_FRAME_SKIP = 2  # Process every 2nd frame (reduced from 3 for better detection)
CLAMP_PRESENT_THRESHOLD = 0.25  # FIXED: Must be <= YOLO_OBB_CONFIDENCE (was 0.5, causing detection failures!)

# OBB Class Names (nc: 3)
OBB_CLASS_NAMES = {
    0: 'forklift_clamp',
    1: 'paper_roll_small', 
    2: 'paper_roll_big'
}
OBB_CLAMP_CLASS_ID = 0  # Only detect forklift_clamp for auto start logic

# Temporal Smoothing
USE_TEMPORAL_SMOOTHING = False
DETECTION_MEMORY_FRAMES = 10
MIN_DETECTIONS_FOR_ALARM = 1 

# Visualization
DRAW_OVERLAY = True
DRAW_ROI = True
USE_RESULT_FRAME = True  # Enable frame visualization from YOLO
ATTACH_RESULT_FRAME = False
RESULT_JPEG_QUALITY = 75
RESULT_FRAME_MAX_WIDTH = 640
RESULT_FRAME_MAX_HEIGHT = 480

COLOR_BOX = (0, 255, 0)  # Green color for bounding boxes
SHOW_VIDEO_ON_SERVER_UI = False  # Disable local UI video rendering for performance

# UI Configuration
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 640

# Control button addresses (0-based Modbus address)
CONTROL_BUTTON_START_ADDR = 0
CONTROL_BUTTON_STOP_ADDR = 1
CONTROL_BUTTON_RESET_ADDR = 2
CONTROL_PULSE_MS = 300

# Modbus IPs
MODBUSWRAP_A_DO_IP = "192.168.1.22"
MODBUSWRAP_B_DO_IP = "192.168.1.23"
MODBUSWRAP_DI_IP = "192.168.1.24"

# Modbus IO configurations (0-based addresses)
MODBUSWRAP_A_DO_CONFIG = {
    'digital_outputs': [
        {'label': 'Start', 'addr': 0, 'type': 'DO'},
        {'label': 'Stop', 'addr': 1, 'type': 'DO'},
        {'label': 'Reset', 'addr': 2, 'type': 'DO'},
        {'label': 'I4', 'addr': 3, 'type': 'DO'},
        {'label': 'I5', 'addr': 4, 'type': 'DO'},
        {'label': 'L_white_Ready', 'addr': 5, 'type': 'DO'},
        {'label': 'L_Blue_Run', 'addr': 6, 'type': 'DO'},
        {'label': 'L_Green_Finish', 'addr': 7, 'type': 'DO'},
        {'label': 'L_Yellow_Film', 'addr': 8, 'type': 'DO'},
        {'label': 'L_Red_Problem', 'addr': 9, 'type': 'DO'},
        {'label': 'I11', 'addr': 10, 'type': 'DO'},
        {'label': 'I12', 'addr': 11, 'type': 'DO'},
        {'label': 'I13', 'addr': 12, 'type': 'DO'},
        {'label': 'I14', 'addr': 13, 'type': 'DO'},
        {'label': 'I15', 'addr': 14, 'type': 'DO'},
        {'label': 'I16', 'addr': 15, 'type': 'DO'},
    ]
}

MODBUSWRAP_B_DO_CONFIG = {
    'digital_outputs': [
        {'label': 'Start', 'addr': 0, 'type': 'DO'},
        {'label': 'Stop', 'addr': 1, 'type': 'DO'},
        {'label': 'Reset', 'addr': 2, 'type': 'DO'},
        {'label': 'I4', 'addr': 3, 'type': 'DO'},
        {'label': 'I5', 'addr': 4, 'type': 'DO'},
        {'label': 'L_white_Ready', 'addr': 5, 'type': 'DO'},
        {'label': 'L_Blue_Run', 'addr': 6, 'type': 'DO'},
        {'label': 'L_Green_Finish', 'addr': 7, 'type': 'DO'},
        {'label': 'L_Yellow_Film', 'addr': 8, 'type': 'DO'},
        {'label': 'L_Red_Problem', 'addr': 9, 'type': 'DO'},
        {'label': 'I11', 'addr': 10, 'type': 'DO'},
        {'label': 'I12', 'addr': 11, 'type': 'DO'},
        {'label': 'I13', 'addr': 12, 'type': 'DO'},
        {'label': 'I14', 'addr': 13, 'type': 'DO'},
        {'label': 'I15', 'addr': 14, 'type': 'DO'},
        {'label': 'I16', 'addr': 15, 'type': 'DO'},
    ]
}

MODBUSWRAP_A_DI_CONFIG = {
    'digital_inputs': [
        {'label': 'Check_roll', 'addr': 0, 'type': 'DI'},
        {'label': 'Check_film', 'addr': 1, 'type': 'DI'},
        {'label': 'Auto Mode', 'addr': 2, 'type': 'DI'},
        {'label': 'I4', 'addr': 3, 'type': 'DI'},
        {'label': 'Run', 'addr': 4, 'type': 'DI'},
        {'label': 'Ready', 'addr': 5, 'type': 'DI'},
        {'label': 'I7', 'addr': 6, 'type': 'DI'},
        {'label': 'I8', 'addr': 7, 'type': 'DI'},
    ]
}

MODBUSWRAP_B_DI_CONFIG = {
    'digital_inputs': [
        {'label': 'Check_roll', 'addr': 8, 'type': 'DI'},
        {'label': 'Check_film', 'addr': 9, 'type': 'DI'},
        {'label': 'Auto Mode', 'addr': 10, 'type': 'DI'},
        {'label': 'I12', 'addr': 11, 'type': 'DI'},
        {'label': 'Run', 'addr': 12, 'type': 'DI'},
        {'label': 'Ready', 'addr': 13, 'type': 'DI'},
        {'label': 'I15', 'addr': 14, 'type': 'DI'},
        {'label': 'I16', 'addr': 15, 'type': 'DI'}
    ]
}

# Production Tracking
PRODUCTION_RUN_DI_ADDR_A = 4   # Machine A wrapping status
PRODUCTION_RUN_DI_ADDR_B = 12  # Machine B wrapping status

# Auto/Manual Mode Tracking
AUTO_MANUAL_MODE_DI_ADDR_A = 2   # Machine A: Man/Auto DI
AUTO_MANUAL_MODE_DI_ADDR_B = 10  # Machine B: Man/Auto DI
AUTO_MODE_DI_VALUE = True  # True = AUTO mode, False = MANUAL mode

# Database
DATABASE_PATH = "data/machine_events.db"

# Auto Control
AUTO_STOP_ON_PERSON = True
STOP_COOLDOWN_SEC = 3.0
AUTO_RESET_ON_CLEAR = False  # True = auto reset, False = manual reset

# Capture
CAPTURE_ON_DETECTION = True
CAPTURE_DIR = "captures"

# Production Capture
PRODUCTION_CAPTURE_ENABLED = True
PRODUCTION_CAPTURE_DIR = "production_captures"
PRODUCTION_CAPTURE_ON_START = True
PRODUCTION_CAPTURE_ON_FINISH = True

# Helper function
def mb_addr0(addr1):
    """Convert 1-based address to 0-based (deprecated - kept for compatibility)"""
    return max(0, int(addr1) - 1)