"""
Database Worker - Handle all database operations
"""
from multiprocessing import Process, Queue
from queue import Empty
import sqlite3
import json
from datetime import datetime
import logging
from pathlib import Path

logger = logging.getLogger('DatabaseWorker')


class DatabaseWorker(Process):
    """
    Worker process for database operations
    
    รับ events จาก MachineLogicWorker และบันทึกลง database
    """
    
    def __init__(self, event_queue: Queue, db_path: str = "data/machine_events.db"):
        super().__init__()
        self.event_queue = event_queue
        self.db_path = db_path
        self.running = False
        self.conn = None
    
    def _init_database(self):
        """Initialize database schema"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
        # Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT,
                timestamp REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Machine status table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS machine_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                is_running BOOLEAN,
                is_ready BOOLEAN,
                person_detected BOOLEAN,
                person_count INTEGER,
                film_ok BOOLEAN,
                roll_ok BOOLEAN,
                timestamp REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_machine_time 
            ON events(machine_id, timestamp DESC)
        """)
"""
Database Worker - Handle all database operations
"""
from multiprocessing import Process, Queue
from queue import Empty
import sqlite3
import json
from datetime import datetime
import logging
from pathlib import Path

logger = logging.getLogger('DatabaseWorker')


class DatabaseWorker(Process):
    """
    Worker process for database operations
    
    รับ events จาก MachineLogicWorker และบันทึกลง database
    """
    
    def __init__(self, event_queue: Queue, db_path: str = "data/machine_events.db"):
        super().__init__()
        self.event_queue = event_queue
        self.db_path = db_path
        self.running = False
        self.conn = None
    
    def _init_database(self):
        """Initialize database schema"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
        # Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT,
                timestamp REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Machine status table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS machine_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                is_running BOOLEAN,
                is_ready BOOLEAN,
                person_detected BOOLEAN,
                person_count INTEGER,
                film_ok BOOLEAN,
                roll_ok BOOLEAN,
                timestamp REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_machine_time 
            ON events(machine_id, timestamp DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type 
            ON events(event_type)
        """)
        
        # Production log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS production_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                shift INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_production_time 
            ON production_log(timestamp)
        """)
        
        self.conn.commit()
        logger.info(f"Database initialized: {self.db_path}")
    
    def run(self):
        """Main worker loop"""
        logger.info(f"Database Worker started - PID={self.pid}")
        
        try:
            self._init_database()
            self.running = True
            
            while self.running:
                try:
                    # Get events from queue
                    event = self.event_queue.get(timeout=1.0)
                    
                    if event == "STOP":
                        break
                    
                    if isinstance(event, dict):
                        if event.get('type') == 'GET_STATS':
                            # Handle synchronous query (via response queue if we had one, 
                            # but here we might need a different approach for API)
                            # For now, API will read DB directly.
                            pass
                        elif event.get('event_type') == 'ROLL_FINISHED':
                            self._log_production(event)
                        else:
                            self._save_event(event)
                
                except Empty:
                    continue
                except Exception as e:
                    logger.exception(f"Event processing error: {e}")
        
        finally:
            if self.conn:
                self.conn.close()
            logger.info("Database Worker stopped")
    
    def _save_event(self, event: dict):
        """Save event to database"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                INSERT INTO events (machine_id, event_type, data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                event.get('machine_id'),
                event.get('event_type'),
                json.dumps(event.get('data', {})),
                event.get('timestamp', 0)
            ))
            
            self.conn.commit()
            # logger.debug(f"Event saved: {event.get('event_type')} for {event.get('machine_id')}")
        
        except Exception as e:
            logger.error(f"Save event error: {e}")

    def _log_production(self, event: dict):
        """Log production count"""
        try:
            cursor = self.conn.cursor()
            ts = event.get('timestamp', 0)
            shift = self._calculate_shift(ts)
            
            cursor.execute("""
                INSERT INTO production_log (machine_id, timestamp, shift)
                VALUES (?, ?, ?)
            """, (
                event.get('machine_id'),
                ts,
                shift
            ))
            
            self.conn.commit()
            logger.info(f"Production logged: Machine {event.get('machine_id')} Shift {shift}")
            
        except Exception as e:
            logger.error(f"Log production error: {e}")

    def _calculate_shift(self, timestamp: float) -> int:
        """
        Calculate shift based on timestamp
        Shift 1: 08:00 - 16:00
        Shift 2: 16:00 - 00:00
        Shift 3: 00:00 - 08:00
        """
        dt = datetime.fromtimestamp(timestamp)
        h = dt.hour
        
        if 8 <= h < 16:
            return 1
        elif 16 <= h < 24:
            return 2
        else:
            return 3

    def stop(self):
        """Stop the worker"""
        self.running = False
        try:
            self.event_queue.put("STOP")
        except:
            pass