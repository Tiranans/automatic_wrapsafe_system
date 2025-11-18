"""Machine control panel UI component"""
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2, config

class MachinePanel(ctk.CTkFrame):
    def __init__(self, master, machine_id: str, camera_ip, on_start, on_stop, on_reset,
                 camera_width=None, camera_height=None):
        super().__init__(master, fg_color="#d9d9d9")
        
        self.machine_id = machine_id  
        self.camera_ip = camera_ip
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_reset = on_reset
        
        self.cam_width = camera_width or config.CAMERA_DISPLAY_WIDTH
        self.cam_height = camera_height or config.CAMERA_DISPLAY_HEIGHT
        
        self._img_ref = None

        # Header
        header = ctk.CTkFrame(self, fg_color="#d9d9d9")
        header.pack(fill="x", padx=5, pady=5)
        
        ctk.CTkLabel(
            header,
            text=f"Machine {machine_id}",  
            font=("Arial", 16, "bold"),
            text_color="black"
        ).pack(side="left", padx=10)
        
        # Alarm indicator
        self.alarm_indicator = ctk.CTkLabel(
            header,
            text="● NORMAL",
            font=("Arial", 16, "bold"),
            text_color="#00ff00",
            fg_color="#2b2b2b",
            corner_radius=8,
            width=200,
            height=40
        )
        self.alarm_indicator.pack(side="left", padx=10)
        
        # Status label
        self.status_label = ctk.CTkLabel(
            header,
            text="● READY",
            font=("Arial", 14),
            text_color="#00ff00"
        )
        self.status_label.pack(side="right", padx=10)
        
        # Main content
        content = ctk.CTkFrame(self, fg_color="#d9d9d9")
        content.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Camera display
        camera_frame = ctk.CTkFrame(content, fg_color="white", border_width=2, border_color="black")
        camera_frame.pack(side="left", fill="both", expand=True, padx=5)
        
        self.camera_label = ctk.CTkLabel(
            camera_frame,
            text="Waiting for camera...",
            width=self.cam_width,
            height=self.cam_height,
            fg_color="black",
            text_color="white"
        )
        self.camera_label.pack(pady=10)
        
        # Controller panel
        controller_frame = ctk.CTkFrame(content, fg_color="white", border_width=2, border_color="black")
        controller_frame.pack(side="right", padx=5)
        
        ctk.CTkLabel(
            controller_frame,
            text="Controller",
            font=("Arial", 16, "bold"),
            text_color="black"
        ).pack(pady=10)
        
        # Buttons
        self.start_btn = ctk.CTkButton(
            controller_frame,
            text="▶ Start",
            font=("Arial", 14, "bold"),
            fg_color="#4caf50",
            hover_color="#45a049",
            width=150,
            height=40,
            command=self._on_start_click
        )
        self.start_btn.pack(pady=5, padx=20)
        
        self.stop_btn = ctk.CTkButton(
            controller_frame,
            text="⏹ Stop",
            font=("Arial", 14, "bold"),
            fg_color="#f44336",
            hover_color="#da190b",
            width=150,
            height=40,
            command=self._on_stop_click
        )
        self.stop_btn.pack(pady=5, padx=20)
        
        self.reset_btn = ctk.CTkButton(
            controller_frame,
            text="🔄 Reset",
            font=("Arial", 14, "bold"),
            fg_color="#ff9800",
            hover_color="#e68900",
            width=150,
            height=40,
            command=self._on_reset_click
        )
        self.reset_btn.pack(pady=5, padx=20)
    
    def _on_start_click(self):
        """Handle start button click"""
        try:
            self.on_start(self.machine_id)  
        except Exception as e:
            print(f"[MachinePanel] on_start error: {e}")
    
    def _on_stop_click(self):
        """Handle stop button click"""
        try:
            self.on_stop(self.machine_id)  
        except Exception as e:
            print(f"[MachinePanel] on_stop error: {e}")
    
    def _on_reset_click(self):
        """Handle reset button click"""
        try:
            self.on_reset(self.machine_id)  
        except Exception as e:
            print(f"[MachinePanel] on_reset error: {e}")
    
    def show_frame(self, frame_bgr, keep_aspect=True):
        """Update camera display with new BGR frame"""
        if frame_bgr is None:
            return
        try:
            h, w = frame_bgr.shape[:2]
            if h == 0 or w == 0:
                return

            if keep_aspect:
                target_w, target_h = self.cam_width, self.cam_height
                scale = min(target_w / w, target_h / h)
                new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            else:
                new_w, new_h = int(self.cam_width), int(self.cam_height)

            resized = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            photo = ImageTk.PhotoImage(image=img)

            self._img_ref = photo
            self.camera_label.configure(image=photo, text="")
            self.camera_label.image = photo
        except Exception as e:
            print(f"[MachinePanel] show_frame error: {e}")

    def update_camera_frame(self, frame, keep_aspect=True):
        """Backward-compatible alias"""
        self.show_frame(frame, keep_aspect=keep_aspect)
    
    def update_alarm_status(self, alarm_active: bool):
        """Update alarm indicator when person detected"""
        if alarm_active:
            self.alarm_indicator.configure(
                text="🚨 PERSON DETECTED!",
                text_color="#ffffff",
                fg_color="#cc0000"
            )
        else:
            self.alarm_indicator.configure(
                text="● NORMAL",
                text_color="#00ff00",
                fg_color="#2b2b2b"
            )
    
    def update_status(self, status: str):
        """Update machine status"""
        color_map = {
            "RUNNING": "#00ff00",
            "STOPPED": "#ff0000",
            "READY": "#ffaa00",
            "ERROR": "#ff0000"
        }
        self.status_label.configure(
            text=f"● {status}",
            text_color=color_map.get(status, "#808080")
        )