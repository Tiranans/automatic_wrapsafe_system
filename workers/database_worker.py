"""
Database Worker - Handle all database operations
"""
from multiprocessing import Process, Queue
from queue import Empty
import sqlite3 
import json
from datetime import datetime
import time
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
        
        # Shifts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shifts (
                shift_id INTEGER PRIMARY KEY,
                shift_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL
            )
        """)
        
        # Insert default shifts
        cursor.execute("SELECT COUNT(*) FROM shifts")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("""
                INSERT INTO shifts (shift_id, shift_name, start_time, end_time)
                VALUES (?, ?, ?, ?)
            """, [
                (1, 'Morning Shift', '08:00:00', '16:00:00'),
                (2, 'Evening Shift', '16:00:00', '00:00:00'),
                (3, 'Night Shift', '00:00:00', '08:00:00')
            ])
        
        # Production Logs table - เพิ่ม field duration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS production_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id INTEGER NOT NULL,
                machine_name TEXT NOT NULL,
                start_datetime TEXT NOT NULL,
                end_datetime TEXT,
                duration_seconds INTEGER,
                duration_minutes REAL,
                pieces_completed INTEGER DEFAULT 0,
                film_wrap_cycle INTEGER DEFAULT 0,
                date TEXT NOT NULL,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (shift_id) REFERENCES shifts(shift_id)
            )
        """)
        
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
        
        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_production_logs_machine_date 
            ON production_logs(machine_name, date DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_machine_time 
            ON events(machine_id, timestamp DESC)
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
                        event_type = event.get('event_type')
                        
                        if event_type == 'ROLL_STARTED':
                            self._start_production_log(event)
                        elif event_type == 'ROLL_FINISHED':
                            self._finish_production_log(event)
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
        
        except Exception as e:
            logger.error(f"Save event error: {e}")

    def _start_production_log(self, event: dict):
        """Start new production log when wrapping begins (DI ON)"""
        try:
            cursor = self.conn.cursor()
            
            machine_id = event.get('machine_id')
            timestamp = event.get('timestamp', time.time())
            dt = datetime.fromtimestamp(timestamp)
            data = event.get('data', {})
            
            # Calculate shift
            shift_id = self._calculate_shift(timestamp)
            
            # Format datetime
            start_datetime = dt.strftime('%Y-%m-%d %H:%M:%S')
            date = dt.strftime('%Y-%m-%d')
            machine_name = f"Machine {machine_id}"
            
            # Insert new production log
            cursor.execute("""
                INSERT INTO production_logs (
                    shift_id, 
                    machine_name, 
                    start_datetime, 
                    date,
                    pieces_completed,
                    film_wrap_cycle
                )
                VALUES (?, ?, ?, ?, 0, 0)
            """, (shift_id, machine_name, start_datetime, date))
            
            log_id = cursor.lastrowid
            
            self.conn.commit()
            
            logger.info(
                f"Production started: log_id={log_id}, "
                f"machine={machine_name}, shift={shift_id}, "
                f"date={date}, time={start_datetime}"
            )
            
        except Exception as e:
            logger.error(f"Start production log error: {e}")
            self.conn.rollback()

    def _finish_production_log(self, event: dict):
        """Update production log when wrapping finishes (DI OFF)"""
        try:
            cursor = self.conn.cursor()
            
            machine_id = event.get('machine_id')
            timestamp = event.get('timestamp', time.time())
            dt = datetime.fromtimestamp(timestamp)
            data = event.get('data', {})
            
            machine_name = f"Machine {machine_id}"
            end_datetime = dt.strftime('%Y-%m-%d %H:%M:%S')
            date = dt.strftime('%Y-%m-%d')
            
            # Get duration from event data
            duration_seconds = data.get('duration_seconds', 0)
            duration_minutes = data.get('duration_minutes', 0.0)
            
            # Find latest open production log
            cursor.execute("""
                SELECT log_id, start_datetime, pieces_completed, film_wrap_cycle
                FROM production_logs
                WHERE machine_name = ?
                  AND date = ?
                  AND end_datetime IS NULL
                ORDER BY log_id DESC
                LIMIT 1
            """, (machine_name, date))
            
            row = cursor.fetchone()
            
            if row:
                log_id, start_datetime, current_pieces, current_cycles = row
                
                # Increment counters
                new_pieces = current_pieces + 1
                new_cycles = current_cycles + 1
                
                # Get optional data
                pieces_override = data.get('pieces_completed')
                note = data.get('note')
                
                if pieces_override is not None:
                    new_pieces = pieces_override
                
                # Update production log with duration
                cursor.execute("""
                    UPDATE production_logs
                    SET end_datetime = ?,
                        duration_seconds = ?,
                        duration_minutes = ?,
                        pieces_completed = ?,
                        film_wrap_cycle = ?,
                        note = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE log_id = ?
                """, (
                    end_datetime, 
                    duration_seconds, 
                    duration_minutes,
                    new_pieces, 
                    new_cycles, 
                    note, 
                    log_id
                ))
                
                self.conn.commit()
                
                logger.info(
                    f"Production finished: log_id={log_id}, "
                    f"machine={machine_name}, pieces={new_pieces}, "
                    f"cycles={new_cycles}, duration={duration_minutes:.2f} min"
                )
                
            else:
                logger.warning(
                    f"No open production log found for {machine_name} on {date}"
                )
            
        except Exception as e:
            logger.error(f"Finish production log error: {e}")
            self.conn.rollback()

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