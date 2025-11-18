"""Main application UI"""
import customtkinter as ctk
from ui.machine_panel import MachinePanel
from ui.modbus_status import ModbusStatusPanel
import config
 
class BM9App(ctk.CTk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self.title("BM9 Automatic WrapSafe System")
        self.geometry("1020x800")  
        ctk.set_appearance_mode("light")
        
        # Main content
        content = ctk.CTkFrame(self, fg_color="#e0e0e0")
        content.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Top section - Machines
        machines_frame = ctk.CTkFrame(content, fg_color="#e0e0e0")
        machines_frame.pack(fill="x", pady=5)
        
        # ✅ Machine A (machine_id="A")
        self.machineA_panel = MachinePanel(
            machines_frame, 
            "A",  # ✅ เปลี่ยนจาก 1 เป็น "A"
            config.MACHINEA_CAMERA_IP,
            on_start=self.controller.start_machine,
            on_stop=self.controller.stop_machine,
            on_reset=self.controller.reset_machine
        )
        self.machineA_panel.pack(side="left", fill="both", expand=True, padx=5)
        
        # ✅ Machine B (machine_id="B")
        self.machineB_panel = MachinePanel(
            machines_frame, 
            "B",  # ✅ เปลี่ยนจาก 2 เป็น "B"
            config.MACHINEB_CAMERA_IP,
            on_start=self.controller.start_machine,
            on_stop=self.controller.stop_machine,
            on_reset=self.controller.reset_machine
        )
        self.machineB_panel.pack(side="right", fill="both", expand=True, padx=5)
        
        # Bottom section - Modbus + Logs
        bottom_frame = ctk.CTkFrame(content, fg_color="#e0e0e0")
        bottom_frame.pack(fill="both", expand=True, pady=5)
        
        # Modbus panels
        modbus_container = ctk.CTkFrame(bottom_frame, fg_color="#c0c0c0")
        modbus_container.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        ctk.CTkLabel(
            modbus_container,
            text="Modbus IO status",
            font=("Arial", 14, "bold"),
            text_color="black"
        ).pack(pady=5)
        
        io_frame = ctk.CTkFrame(modbus_container, fg_color="#c0c0c0")
        io_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # WRAP_A_DO
        self.modbus_do1_panel = ModbusStatusPanel(
            io_frame,
            modbus_ip=config.MODBUSWRAP_A_DO_IP,
            title="WRAP_A_DO",
            io_config=config.MODBUSWRAP_A_DO_CONFIG['digital_outputs'],
            addr_start=0,
            addr_end=15
        )
        self.modbus_do1_panel.pack(side="left", fill="y", padx=3)
        
        # WRAP_B_DO
        self.modbus_do2_panel = ModbusStatusPanel(
            io_frame,
            modbus_ip=config.MODBUSWRAP_B_DO_IP,
            title="WRAP_B_DO",
            io_config=config.MODBUSWRAP_B_DO_CONFIG['digital_outputs'],
            addr_start=0,
            addr_end=15
        )
        self.modbus_do2_panel.pack(side="left", fill="y", padx=3)
        
        # WRAP_A_DI
        self.wrap_a_di_panel = ModbusStatusPanel(
            io_frame,
            modbus_ip=config.MODBUSWRAP_DI_IP,
            title="WRAP_A_DI",
            io_config=config.MODBUSWRAP_A_DI_CONFIG['digital_inputs'],
            addr_start=0,
            addr_end=7
        )
        self.wrap_a_di_panel.pack(side="left", fill="y", padx=3)
        
        # WRAP_B_DI
        self.wrap_b_di_panel = ModbusStatusPanel(
            io_frame,
            modbus_ip=config.MODBUSWRAP_DI_IP,
            title="WRAP_B_DI",
            io_config=config.MODBUSWRAP_B_DI_CONFIG['digital_inputs'],
            addr_start=8,
            addr_end=15
        )
        self.wrap_b_di_panel.pack(side="left", fill="y", padx=3)
        
        # Register indicators
        for addr, widget in self.modbus_do1_panel.io_indicators.get(self.modbus_do1_panel.DEFAULT_KEY, {}).items():
            self.modbus_do1_panel.register_indicator("Wrap_A_DO", addr, widget)
        
        for addr, widget in self.modbus_do2_panel.io_indicators.get(self.modbus_do2_panel.DEFAULT_KEY, {}).items():
            self.modbus_do2_panel.register_indicator("Wrap_B_DO", addr, widget)
        
        for addr, widget in self.wrap_a_di_panel.io_indicators.get(self.wrap_a_di_panel.DEFAULT_KEY, {}).items():
            self.wrap_a_di_panel.register_indicator("Wrap_A_DI", addr, widget)
        
        for addr, widget in self.wrap_b_di_panel.io_indicators.get(self.wrap_b_di_panel.DEFAULT_KEY, {}).items():
            self.wrap_b_di_panel.register_indicator("Wrap_B_DI", addr, widget)
        
        # Map worker_id -> panel
        self._panel_by_worker_id = {
            "Wrap_A_DO": self.modbus_do1_panel,
            "Wrap_B_DO": self.modbus_do2_panel,
            "Wrap_A_DI": self.wrap_a_di_panel,
            "Wrap_B_DI": self.wrap_b_di_panel,
        }
        self._modbus_prev_connected: dict[str, bool] = {}
        
        # Logs
        logs_frame = ctk.CTkFrame(bottom_frame, fg_color="white", border_width=2, border_color="black")
        logs_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        ctk.CTkLabel(
            logs_frame,
            text="Logs",
            font=("Arial", 14, "bold"),
            text_color="black"
        ).pack(pady=5)
        
        self.log_text = ctk.CTkTextbox(
            logs_frame,
            font=("Consolas", 10),
            text_color="black",
            fg_color="white"
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
    
    def add_log(self, message: str):
        """Add log message to UI"""
        try:
            if self.log_text.winfo_exists():
                self.log_text.insert("end", f"{message}\n")
                self.log_text.see("end")
        except Exception:
            pass
    
    def update_camera(self, machine_id: str, frame):  # ✅ รับ string
        """Update camera display for machine panel"""
        try:
            if machine_id == "A" and hasattr(self, 'machineA_panel') and self.machineA_panel.winfo_exists():
                self.machineA_panel.update_camera_frame(frame)
            elif machine_id == "B" and hasattr(self, 'machineB_panel') and self.machineB_panel.winfo_exists():
                self.machineB_panel.update_camera_frame(frame)
        except Exception as e:
            print(f"[update_camera] Error: {e}")
    
    def update_modbus_status(self, worker_id: str, status: dict):
        """Update Modbus status indicators in UI"""
        try:
            connected = bool(status.get('connected', False))
            values = status.get('values', {})

            # Log connection state changes
            prev = self._modbus_prev_connected.get(worker_id)
            if prev is None or prev != connected:
                self._modbus_prev_connected[worker_id] = connected
                self.add_log(f"[Modbus] {worker_id} {'connected' if connected else 'disconnected'}")

            panel = self._panel_by_worker_id.get(worker_id)
            if not panel or not hasattr(panel, "update_status"):
                return

            # Update UI in main thread
            self.after(0, lambda: panel.update_status(worker_id, values if connected else {}))
        except Exception as e:
            self.add_log(f"[UI] update_modbus_status error: {e}")
    
    def update_alarm_status(self, machine_id: str, alarm_active: bool):  # ✅ รับ string
        """Update alarm indicator for machine panel"""
        try:
            if machine_id == "A" and hasattr(self, 'machineA_panel'):
                self.machineA_panel.update_alarm_status(alarm_active)
            elif machine_id == "B" and hasattr(self, 'machineB_panel'):
                self.machineB_panel.update_alarm_status(alarm_active)
        except Exception as e:
            print(f"[UI] update_alarm_status error: {e}")

    def _on_close(self):
        """Handle window close event"""
        self.controller.cleanup()
        self.destroy()