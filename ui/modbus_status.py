"""Modbus IO status display component (Status display only)"""
import customtkinter as ctk
from typing import List, Dict

class ModbusStatusPanel(ctk.CTkFrame):
    DEFAULT_KEY = ""

    def __init__(self, master, modbus_ip: str, title: str, io_config: List[Dict],
                 addr_start: int, addr_end: int):
        super().__init__(master, fg_color="#c0c0c0", border_width=2, border_color="black", corner_radius=5)
        self.modbus_ip = modbus_ip
        self.io_config = io_config or []
        self.io_indicators = {self.DEFAULT_KEY: {}}
        self.addr_start = int(addr_start)
        self.addr_end = int(addr_end)

        ctk.CTkLabel(self, text=title, font=("Arial", 16, "bold"),
                     text_color="black").pack(pady=(10, 5), padx=5)

        grid = ctk.CTkFrame(self, fg_color="#c0c0c0")
        grid.pack(fill="both", expand=True, padx=10, pady=5)

       
        count = self.addr_end - self.addr_start + 1
        
        if count == 16:
            # 16 outputs: แสดง 2 คอลัมน์
            left = ctk.CTkFrame(grid, fg_color="#c0c0c0")
            left.pack(side="left", fill="y", expand=True, padx=(0, 15))
            right = ctk.CTkFrame(grid, fg_color="#c0c0c0")
            right.pack(side="left", fill="y", expand=True)
            
            # 0-7 ซ้าย, 8-15 ขวา
            for addr in range(self.addr_start, self.addr_start + 8):
                self._create_fixed_row(left, addr)
            for addr in range(self.addr_start + 8, self.addr_end + 1):
                self._create_fixed_row(right, addr)
        else:
            # 8 inputs: แสดง 1 คอลัมน์
            col = ctk.CTkFrame(grid, fg_color="#c0c0c0")
            col.pack(side="left", fill="y", expand=True)
            for addr in range(self.addr_start, self.addr_end + 1):
                self._create_fixed_row(col, addr)

        ctk.CTkLabel(self, text=f"IP {modbus_ip}", font=("Arial", 10),
                     text_color="black").pack(pady=(5, 10), padx=5)

    def _label_for(self, addr: int) -> str:
     
        item = next((i for i in self.io_config if i.get('addr') == addr), None)
        if item and item.get('label'):
            return item.get('label')
    
        return f"I{addr}"

    def _create_fixed_row(self, parent, addr: int):
        row = ctk.CTkFrame(parent, fg_color="#c0c0c0")
        row.pack(pady=2, fill="x")
        
        ctk.CTkLabel(
            row, 
            text=self._label_for(addr), 
            font=("Arial", 12),
            text_color="black", 
            width=120, 
            anchor="w"
        ).pack(side="left", padx=(5, 10))

        # indicator dot
        dot = ctk.CTkLabel(row, text="●", font=("Arial", 24), text_color="#808080", width=15)
        dot.pack(side="left", padx=2)

    
        self.io_indicators[self.DEFAULT_KEY][addr] = dot

    def register_indicator(self, worker_id: str, addr: int, widget):
     
        key = worker_id if worker_id else self.DEFAULT_KEY
        self.io_indicators.setdefault(key, {})[addr] = widget

    def update_status(self, worker_id: str, values: dict):
        """Update indicators from values dict (using 0-based addresses)"""
        mapping = self.io_indicators.get(worker_id) or self.io_indicators.get(self.DEFAULT_KEY, {})

        # disconnected: gray out all
        if not values:
            for _, w in mapping.items():
                try:
                    if isinstance(w, ctk.CTkLabel):
                        w.configure(text="●", text_color="#808080")
                except Exception:
                    pass
            return

     
        for addr, val in values.items():
            try:
                a = int(addr)  
            except Exception:
                continue
            
            w = mapping.get(a)
            if not w:
                continue
            
            try:
                color = "#e74c3c" if bool(val) else "#808080"
                if isinstance(w, ctk.CTkLabel):
                    w.configure(text="●", text_color=color)
            except Exception:
                pass