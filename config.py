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

CAMERA_DISPLAY_WIDTH = 480
CAMERA_DISPLAY_HEIGHT = 360

# Modbus Configuration
MODBUS_PORT = 501
MODBUS_TIMEOUT = 5
MODBUS_UNIT_ID = 1  

# ✅ Digital I/O address ranges (0-based for Modbus)
DO_START_ADDRESS = 0
DO_END_ADDRESS = 15

DI_A_START_ADDRESS = 0
DI_A_END_ADDRESS = 7

DI_B_START_ADDRESS = 8
DI_B_END_ADDRESS = 15

# YOLO / Detection
YOLO_MODEL_PATH = "models/yolov8n-pose.pt"
YOLO_CONFIDENCE = 0.6

# ROI (normalized 0..1: x0,y0,x1,y1)
M1_DETECT_ROI = (0.20, 0.02, 0.85, 1.00)
M2_DETECT_ROI = (0.15, 0.02, 0.80, 1.00)
ROI_COLOR_BGR = (255, 0, 0)
ROI_THICKNESS = 10

# Auto stop config
AUTO_STOP_ON_PERSON = True
STOP_COOLDOWN_SEC = 3.0
INTERSECT_THRESHOLD = 0.3

# Keypoints (pose)
KEYPOINTS_TO_CHECK = None
KEYPOINT_CONF_THRES = 0.6
KEYPOINTS_IN_ROI_FRACTION = 0.0
KEYPOINTS_MIN_IN_ROI = 1

FALLBACK_TO_BBOX = False

# Temporal smoothing
USE_TEMPORAL_SMOOTHING = True
DETECTION_MEMORY_FRAMES = 10
MIN_DETECTIONS_FOR_ALARM = 5

# Visualization
DRAW_OVERLAY = True
DRAW_ROI = True
DRAW_BBOX = True
DRAW_SKELETON = False
VIS_THICKNESS = 2
COLOR_NORMAL = (0, 255, 0)
COLOR_ALARM = (0, 0, 255)
COLOR_BOX = (255, 255, 0)
COLOR_KPT = (0, 255, 255)
COLOR_SKELETON = (255, 0, 255)

ENHANCE_DISPLAY = False
ENHANCE_CONTRAST = False
CONTRAST_ALPHA = 1.2
CONTRAST_BETA = 5
APPLY_CLAHE = False

USE_RESULT_FRAME = True
ATTACH_RESULT_FRAME = False
RESULT_JPEG_QUALITY = 70
RESULT_FRAME_MAX_WIDTH = 480

# UI Configuration
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 640

# ✅ Control button addresses (0-based Modbus address)
CONTROL_BUTTON_START_ADDR = 0
CONTROL_BUTTON_STOP_ADDR = 1
CONTROL_BUTTON_RESET_ADDR = 2
CONTROL_PULSE_MS = 300

# Modbus IPs
MODBUSWRAP_A_DO_IP = "192.168.1.22"
MODBUSWRAP_B_DO_IP = "192.168.1.23"
MODBUSWRAP_DI_IP = "192.168.1.24"

# ✅ Modbus IO configurations (0-based addresses)
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
        {'label': 'Man/Auto', 'addr': 2, 'type': 'DI'},
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
        {'label': 'Man/Auto', 'addr': 10, 'type': 'DI'},
        {'label': 'I12', 'addr': 11, 'type': 'DI'},
        {'label': 'Run', 'addr': 12, 'type': 'DI'},
        {'label': 'Ready', 'addr': 13, 'type': 'DI'},
        {'label': 'I15', 'addr': 14, 'type': 'DI'},
        {'label': 'I16', 'addr': 15, 'type': 'DI'}
    ]
}

# OpenCV ใช้ BGR (Blue-Green-Red)
# PIL/Tkinter ใช้ RGB (Red-Green-Blue)

# ภาพ 1920x1080 → target 480x360
# scale_w = 480/1920 = 0.25
# scale_h = 360/1080 = 0.33
# ใช้ min = 0.25 → ได้ 480x270 (ไม่บิดเบี้ยว)

# ✅ Helper function (ไม่จำเป็นอีกต่อไปเพราะใช้ 0-based ตรง ๆ)
def mb_addr0(addr1):
    """Convert 1-based address to 0-based (deprecated - kept for compatibility)"""
    return max(0, int(addr1) - 1)