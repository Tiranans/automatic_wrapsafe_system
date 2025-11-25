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
        target_date = datetime.strptime(date, "%Y-%m-%d")
        start_ts = target_date.timestamp()
        end_ts = (target_date + timedelta(days=1)).timestamp()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query production logs
        cursor.execute("""
            SELECT machine_id, shift, COUNT(*) as count
            FROM production_log
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY machine_id, shift
        """, (start_ts, end_ts))
        
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
                "shifts": {
                    1: 0,
                    2: 0,
                    3: 0
                }
            }
            
        for row in rows:
            mid = row["machine_id"]
            shift = row["shift"]
            count = row["count"]
            
            if mid not in stats["machines"]:
                stats["machines"][mid] = {"total": 0, "shifts": {1:0, 2:0, 3:0}}
                
            stats["machines"][mid]["shifts"][shift] = count
            stats["machines"][mid]["total"] += count
            
        return stats
        
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
