from fastapi import APIRouter, HTTPException, Query
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

router = APIRouter()
logger = logging.getLogger("API.Production")

DB_PATH = "data/machine_events.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@router.get("/stats")
def get_production_stats(date: str = Query(None, description="Date in YYYY-MM-DD format")):
    """Get production stats for a specific date (default: today)"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query from production_logs table (new schema)
        cursor.execute("""
            SELECT 
                pl.machine_name,
                pl.shift_id,
                COUNT(*) as count,
                SUM(pl.pieces_completed) as total_pieces,
                SUM(pl.film_wrap_cycle) as total_cycles,
                SUM(pl.duration_minutes) as total_duration_min
            FROM production_logs pl
            WHERE pl.date = ?
              AND pl.end_datetime IS NOT NULL
            GROUP BY pl.machine_name, pl.shift_id
        """, (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Structure the response
        stats = {
            "date": date,
            "machines": {}
        }
        
        # Initialize structure for known machines
        for mid in ["A", "B"]:
            stats["machines"][mid] = {
                "total": 0,
                "total_pieces": 0,
                "total_cycles": 0,
                "total_duration_min": 0.0,
                "shifts": {
                    1: 0,
                    2: 0,
                    3: 0
                }
            }
            
        # Process query results
        for row in rows:
            machine_name = row["machine_name"]  # "Machine A" or "Machine B"
            shift_id = row["shift_id"]
            count = row["count"]
            pieces = row["total_pieces"] or 0
            cycles = row["total_cycles"] or 0
            duration = row["total_duration_min"] or 0.0
            
            # Extract machine ID from name ("Machine A" -> "A")
            mid = machine_name.replace("Machine ", "").strip()
            
            if mid not in stats["machines"]:
                stats["machines"][mid] = {
                    "total": 0, 
                    "total_pieces": 0,
                    "total_cycles": 0,
                    "total_duration_min": 0.0,
                    "shifts": {1:0, 2:0, 3:0}
                }
                
            stats["machines"][mid]["shifts"][shift_id] = count
            stats["machines"][mid]["total"] += count
            stats["machines"][mid]["total_pieces"] += pieces
            stats["machines"][mid]["total_cycles"] += cycles
            stats["machines"][mid]["total_duration_min"] += duration
            
        return stats
        
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/details")
def get_production_details(
    date: str = Query(None, description="Date in YYYY-MM-DD format"),
    machine: str = Query(None, description="Machine ID (A or B)")
):
    """Get detailed production logs for a specific date and machine"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                pl.log_id,
                pl.machine_name,
                pl.shift_id,
                s.shift_name,
                pl.start_datetime,
                pl.end_datetime,
                pl.duration_seconds,
                pl.duration_minutes,
                pl.pieces_completed,
                pl.film_wrap_cycle,
                pl.note
            FROM production_logs pl
            LEFT JOIN shifts s ON pl.shift_id = s.shift_id
            WHERE pl.date = ?
        """
        
        params = [date]
        
        if machine:
            query += " AND pl.machine_name = ?"
            params.append(f"Machine {machine}")
        
        query += " ORDER BY pl.start_datetime DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        # Convert to list of dicts
        details = []
        for row in rows:
            details.append({
                "log_id": row["log_id"],
                "machine_name": row["machine_name"],
                "shift_id": row["shift_id"],
                "shift_name": row["shift_name"],
                "start_datetime": row["start_datetime"],
                "end_datetime": row["end_datetime"],
                "duration_seconds": row["duration_seconds"],
                "duration_minutes": row["duration_minutes"],
                "pieces_completed": row["pieces_completed"],
                "film_wrap_cycle": row["film_wrap_cycle"],
                "note": row["note"]
            })
        
        return {
            "date": date,
            "machine": machine,
            "count": len(details),
            "logs": details
        }
        
    except Exception as e:
        logger.error(f"Error fetching details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
