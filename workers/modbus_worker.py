"""Modbus communication worker with clean architecture"""
from multiprocessing import Process
from pymodbus.client import ModbusTcpClient
from dataclasses import dataclass
from typing import Dict, Optional, Any
import os
import time
import config
import logging 
from logging import FileHandler, Formatter


@dataclass
class ModbusStats:

    read_success: int = 0
    read_fail: int = 0
    write_success: int = 0
    write_fail: int = 0


class ModbusConnection:
  
    
    def __init__(self, host: str, port: int, unit_id: int, timeout: int = 5):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.client: Optional[ModbusTcpClient] = None
        self.is_connected = False
    
    def connect(self) -> bool:
     
        # Ensure client is closed before attempting new connection
        if self.client:
            self.client.close()
            
        try:
            self.client = ModbusTcpClient(
                host=self.host, 
                port=self.port, 
                timeout=self.timeout
            )
            self.is_connected = self.client.connect()
            
            # NOTE: Logging handled by ModbusWorker for unified output
            return self.is_connected
            
        except Exception as e:
            # NOTE: Logging handled by ModbusWorker for unified output
            self.is_connected = False
            return False
    
    def disconnect(self):
  
        try:
            if self.client:
                self.client.close()
                self.is_connected = False
        except Exception:
            # Silent disconnect error
            pass
    
    def read_holding_registers(self, address: int, count: int) -> Optional[Any]:
    
        if not self.client or not self.is_connected:
            return None
            
        try:
            # Use client directly to return response object
            return self.client.read_holding_registers(
                address, 
                count, 
                slave=self.unit_id
            )
            
        except Exception:
            return None
    
    def write_register(self, address: int, value: int) -> Optional[Any]:
       
        if not self.client or not self.is_connected:
            return None
            
        try:
            # Use client directly to return response object
            return self.client.write_register(
                address=address, 
                value=value, 
                slave=self.unit_id
            )
            
        except Exception:
            return None


class ModbusWorker(Process):
  
    
    def __init__(
        self, 
        modbus_ip: str,
        io_type: str,
        result_queue,
        command_queue,
        status_queue,
        worker_id: str,
        addr_start: int,
        addr_end: int,
        port: int,
    ):
        super().__init__()
        
        # Configuration
        self.worker_id = worker_id
        self.io_type = io_type
        self.addr_start = int(addr_start)
        self.addr_end = int(addr_end)
        
        # Queues
        self.result_queue = result_queue
        self.command_queue = command_queue
        self.status_queue = status_queue
        
        # Modbus connection
        self.unit_id = config.MODBUS_UNIT_ID
        self.connection = ModbusConnection(modbus_ip, port, self.unit_id)
        
        # State
        self.running = False
        self.last_values: Dict[int, bool] = {}
        self.last_error: Optional[str] = None
        self.stats = ModbusStats()
        
        # Logging setup
        self.logger: Optional[logging.Logger] = None
        self._setup_logging()

    def _setup_logging(self):
    
        try:
            os.makedirs("logs", exist_ok=True)
            self.logger = logging.getLogger(self.worker_id)
            self.logger.setLevel(logging.INFO)
            
            # Prevent adding multiple handlers if worker is restarted
            if not self.logger.handlers:
                fh = FileHandler(
                    f"logs/modbus_{self.worker_id}.log", 
                    mode="a", 
                    encoding="utf-8"
                )
                formatter = Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
                fh.setFormatter(formatter)
                self.logger.addHandler(fh)
            
            # Ensure console output is available if no logger is set up yet
            if not self.logger.hasHandlers():
                self.logger.addHandler(logging.StreamHandler())
                
        except Exception as e:
            # Fallback print if logging fails
            print(f"[{self.worker_id}] Logging setup failed: {e}")
            self.logger = None

    def _log(self, level: str, msg: str, *args, **kwargs):
      
        if self.logger:
            getattr(self.logger, level.lower())(f"[{self.worker_id}] {msg}", *args, **kwargs)
        else:
            print(f"{level} [{self.worker_id}] {msg}")
    
    def _initial_connect_with_retry(self, max_retry_delay: int = 30) -> bool:
        """Connect with exponential backoff, returns True if connected, False if stopped"""
        
        self._log("INFO", f"Attempting connection to {self.connection.host}:{self.connection.port}...")
        
        if self.connection.connect():
            self._log("INFO", f"✓ Connected successfully.")
            return True
        
        self._log("WARNING", "Initial connection failed, entering background retry mode...")
        self._notify_disconnection("Initial connection failed")
        
        retry_delay = 2
        last_log_time = 0
        
        while True: # Will break on success or STOP command
            if self._check_stop_command():
                return False
            
            time.sleep(retry_delay)
            
            if self.connection.connect():
                self._log("INFO", f"✓ Reconnected successfully.")
                return True
            
            # Log only occasionally to avoid spam
            if time.time() - last_log_time > 10:
                self._log("INFO", f"Still trying to connect... (next retry in {retry_delay}s)")
                last_log_time = time.time()
            
            retry_delay = min(max_retry_delay, retry_delay * 2)
    
    def _check_stop_command(self) -> bool:
        """Check if STOP command is in queue"""
        try:
            cmd = self.command_queue.get_nowait()
            if cmd == "STOP":
                self._log("INFO", "Received STOP command")
                self.running = False
                return True
        except:
            pass
        return False
    
    def _read_modbus_data(self) -> Dict[int, bool]:
        """Read data from Modbus device with retry"""
        count = self.addr_end - self.addr_start + 1
        
        # Retry up to 3 times
        for attempt in range(3):
            result = self.connection.read_holding_registers(self.addr_start, count)
            
            if result and not result.isError() and hasattr(result, 'registers'):
                
                if attempt > 0:
                    self.stats.read_fail += attempt
                
                self.stats.read_success += 1
                self.last_error = None
                
                data = {}
                for i, reg_value in enumerate(result.registers):
                    addr = self.addr_start + i
                    data[addr] = bool(reg_value)
                
                self.last_values = data
                return data
            
            # Wait before retry (except last attempt)
            if attempt < 2:
                time.sleep(0.05)
        
        # All retries failed
        self.stats.read_fail += 3  
        read_error_msg = f"Read failed after 3 attempts"
        self.last_error = read_error_msg
        self._log("ERROR", read_error_msg)
        
        if result and result.isError():
            raise ConnectionError(f"Modbus Read Error: {result}")
        else:
            raise ConnectionError("Modbus Read Timeout")

    def _process_write_commands(self):
        """Process all pending write commands with retry"""
        while not self.command_queue.empty():
            cmd = self.command_queue.get()
            
            if cmd == "STOP":
                self._log("INFO", "Received STOP command")
                self.running = False
                return
            
            if isinstance(cmd, dict) and cmd.get("cmd") == "WRITE_COIL":
                address = cmd.get("addr")
                value = cmd.get("value")
                int_value = 1 if value else 0
                
                self._log("INFO", f"Processing WRITE addr={address} value={value}")
                
             
                write_success = False
                for attempt in range(3):
                    result = self.connection.write_register(address, int_value)
                    
                    if result and not result.isError():
                       
                        if attempt > 0:
                            self.stats.write_fail += attempt
                        
                        self.stats.write_success += 1
                        self._log("INFO", f"✓ Wrote register addr={address} value={int_value}")
                        write_success = True
                        break
                    
                    # Wait before retry
                    if attempt < 2:
                        self._log("WARNING", f"Write attempt {attempt+1} failed, retrying...")
                        time.sleep(0.05)
                
                if not write_success:
                    self.stats.write_fail += 3  
                    self._log("ERROR", f"✗ Write failed at addr {address} after 3 attempts")
                    raise ConnectionError(f"Modbus Write Error after retry")
    
    def _create_status_payload(self) -> Dict[str, Any]:
        """Create status payload for queue"""
        return {
            'worker_id': self.worker_id,
            'connected': self.connection.is_connected,
            'io_type': self.io_type,
            'values': self.last_values.copy(),
            'unit_id': self.unit_id,
            'error': self.last_error,
            'timestamp': time.time(),
            'stats': {
                'read_success': self.stats.read_success,
                'read_fail': self.stats.read_fail,
                'write_success': self.stats.write_success,
                'write_fail': self.stats.write_fail
            }
        }
    
    def _publish_status(self):
        """Publish status to queue"""
        if self.status_queue is None:
            return
        
        try:
            payload = self._create_status_payload()
            self.status_queue.put_nowait(payload)
        except Exception as e:
            self._log("ERROR", f"Status queue error: {e}")
    
    def _notify_disconnection(self, error_msg: str):
        """Notify queue about disconnection"""
        try:
            if self.status_queue:
                self.status_queue.put_nowait({
                    'worker_id': self.worker_id,
                    'connected': False,
                    'error': error_msg,
                    'timestamp': time.time()
                })
        except Exception as e:
            self._log("ERROR", f"Notification queue error: {e}")
    
    def run(self):
      
        
        # 1. Setup
        self._log("INFO", f"Worker starting - PID={os.getpid()}")
        self._log("INFO", f"Config: {self.io_type}, addr={self.addr_start}-{self.addr_end}, unit_id={self.unit_id}")
        
        # 2. Initial connection attempt
        if not self._initial_connect_with_retry():
            self._log("ERROR", "Failed to establish initial connection, exiting")
            return
        
        self.running = True
        
        # 3. Main loop
        try:
            while self.running:
                try:
                    # Process commands (includes STOP check)
                    self._process_write_commands()
                    if not self.running: 
                        break

                    # Read Modbus data
                    self._read_modbus_data()
                    
                    # Publish status to queue
                    self._publish_status()
                    
                    # Sleep before next cycle
                    time.sleep(0.1)
                    
                except ConnectionError as e:
                    # 4. FIX FOR CONNECTION LOSS (2.3)
                    self._log("ERROR", f"Modbus communication error detected: {e}. Attempting reconnection.")
                    self.last_error = str(e)
                    
                    # 4a. Disconnect and Notify
                    self.connection.disconnect()
                    self._notify_disconnection(f"Modbus connection lost: {str(e)}")
                    
                    # 4b. Re-enter connection retry loop
                    if not self._initial_connect_with_retry(max_retry_delay=30):
                        # If connection attempt fails and STOP command was received
                        break
                    
                    self.last_error = None # Clear error after successful reconnection
                    self._log("INFO", "Reconnection successful. Resuming operations.")
                    
                except Exception as e:
                    self._log("CRITICAL", f"Unforeseen critical exception: {e}", exc_info=True)
                    self.last_error = str(e)
                    time.sleep(1) # Slow down loop on critical unhandled errors
        
        finally:
            # Cleanup
            self.connection.disconnect()
            self._log("INFO", "Worker stopped")
            self._log("INFO", f"Stats - Success: {self.stats.read_success}, Fail: {self.stats.read_fail}")
            
            # Clean up logger handlers
            if self.logger:
                for handler in self.logger.handlers[:]:
                    handler.close()
                    self.logger.removeHandler(handler)
