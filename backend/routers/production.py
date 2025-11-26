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

@router.get("/summary/daily")
def get_daily_summary(date: str = Query(None, description="Date in YYYY-MM-DD format")):
    """Get daily production summary with totals and statistics"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get production logs for the day
        cursor.execute("""
            SELECT 
                pl.machine_name,
                pl.shift_id,
                s.shift_name,
                COUNT(*) as total_rolls,
                SUM(pl.pieces_completed) as total_pieces,
                SUM(pl.film_wrap_cycle) as total_cycles,
                SUM(pl.duration_minutes) as total_duration_min,
                AVG(pl.duration_minutes) as avg_duration_min,
                MIN(pl.duration_minutes) as min_duration_min,
                MAX(pl.duration_minutes) as max_duration_min
            FROM production_logs pl
            LEFT JOIN shifts s ON pl.shift_id = s.shift_id
            WHERE pl.date = ?
              AND pl.end_datetime IS NOT NULL
            GROUP BY pl.machine_name, pl.shift_id, s.shift_name
            ORDER BY pl.machine_name, pl.shift_id
        """, (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Structure response
        summary = {
            "date": date,
            "report_type": "daily",
            "machines": {}
        }
        
        for row in rows:
            machine_name = row["machine_name"]
            mid = machine_name.replace("Machine ", "").strip()
            
            if mid not in summary["machines"]:
                summary["machines"][mid] = {
                    "machine_name": machine_name,
                    "total_rolls": 0,
                    "total_pieces": 0,
                    "total_cycles": 0,
                    "total_duration_min": 0.0,
                    "shifts": []
                }
            
            shift_data = {
                "shift_id": row["shift_id"],
                "shift_name": row["shift_name"],
                "total_rolls": row["total_rolls"],
                "total_pieces": row["total_pieces"] or 0,
                "total_cycles": row["total_cycles"] or 0,
                "total_duration_min": round(row["total_duration_min"] or 0.0, 2),
                "avg_duration_min": round(row["avg_duration_min"] or 0.0, 2),
                "min_duration_min": round(row["min_duration_min"] or 0.0, 2),
                "max_duration_min": round(row["max_duration_min"] or 0.0, 2)
            }
            
            summary["machines"][mid]["shifts"].append(shift_data)
            summary["machines"][mid]["total_rolls"] += row["total_rolls"]
            summary["machines"][mid]["total_pieces"] += row["total_pieces"] or 0
            summary["machines"][mid]["total_cycles"] += row["total_cycles"] or 0
            summary["machines"][mid]["total_duration_min"] += row["total_duration_min"] or 0.0
        
        # Round totals
        for mid in summary["machines"]:
            summary["machines"][mid]["total_duration_min"] = round(
                summary["machines"][mid]["total_duration_min"], 2
            )
        
        return summary
        
    except Exception as e:
        logger.error(f"Error fetching daily summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary/monthly")
def get_monthly_summary(
    year: int = Query(..., description="Year (YYYY)"),
    month: int = Query(..., description="Month (1-12)")
):
    """Get monthly production summary"""
    try:
        # Validate month
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
        
        # Calculate date range
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get monthly summary
        cursor.execute("""
            SELECT 
                pl.machine_name,
                pl.date,
                COUNT(*) as daily_rolls,
                SUM(pl.pieces_completed) as daily_pieces,
                SUM(pl.film_wrap_cycle) as daily_cycles,
                SUM(pl.duration_minutes) as daily_duration_min
            FROM production_logs pl
            WHERE pl.date >= ? AND pl.date < ?
              AND pl.end_datetime IS NOT NULL
            GROUP BY pl.machine_name, pl.date
            ORDER BY pl.date, pl.machine_name
        """, (start_date, end_date))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Structure response
        summary = {
            "year": year,
            "month": month,
            "report_type": "monthly",
            "daily_data": [],
            "machines": {}
        }
        
        # Organize by date and machine
        date_dict = {}
        for row in rows:
            date = row["date"]
            machine_name = row["machine_name"]
            mid = machine_name.replace("Machine ", "").strip()
            
            if date not in date_dict:
                date_dict[date] = {"date": date, "machines": {}}
            
            date_dict[date]["machines"][mid] = {
                "rolls": row["daily_rolls"],
                "pieces": row["daily_pieces"] or 0,
                "cycles": row["daily_cycles"] or 0,
                "duration_min": round(row["daily_duration_min"] or 0.0, 2)
            }
            
            # Accumulate machine totals
            if mid not in summary["machines"]:
                summary["machines"][mid] = {
                    "total_rolls": 0,
                    "total_pieces": 0,
                    "total_cycles": 0,
                    "total_duration_min": 0.0
                }
            
            summary["machines"][mid]["total_rolls"] += row["daily_rolls"]
            summary["machines"][mid]["total_pieces"] += row["daily_pieces"] or 0
            summary["machines"][mid]["total_cycles"] += row["daily_cycles"] or 0
            summary["machines"][mid]["total_duration_min"] += row["daily_duration_min"] or 0.0
        
        summary["daily_data"] = list(date_dict.values())
        
        # Round totals
        for mid in summary["machines"]:
            summary["machines"][mid]["total_duration_min"] = round(
                summary["machines"][mid]["total_duration_min"], 2
            )
        
        return summary
        
    except Exception as e:
        logger.error(f"Error fetching monthly summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary/yearly")
def get_yearly_summary(year: int = Query(..., description="Year (YYYY)")):
    """Get yearly production summary"""
    try:
        start_date = f"{year}-01-01"
        end_date = f"{year + 1}-01-01"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get yearly summary by month
        cursor.execute("""
            SELECT 
                pl.machine_name,
                strftime('%m', pl.date) as month,
                COUNT(*) as monthly_rolls,
                SUM(pl.pieces_completed) as monthly_pieces,
                SUM(pl.film_wrap_cycle) as monthly_cycles,
                SUM(pl.duration_minutes) as monthly_duration_min
            FROM production_logs pl
            WHERE pl.date >= ? AND pl.date < ?
              AND pl.end_datetime IS NOT NULL
            GROUP BY pl.machine_name, month
            ORDER BY month, pl.machine_name
        """, (start_date, end_date))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Structure response
        summary = {
            "year": year,
            "report_type": "yearly",
            "monthly_data": [],
            "machines": {}
        }
        
        # Organize by month and machine
        month_dict = {}
        for row in rows:
            month = int(row["month"])
            machine_name = row["machine_name"]
            mid = machine_name.replace("Machine ", "").strip()
            
            if month not in month_dict:
                month_dict[month] = {"month": month, "machines": {}}
            
            month_dict[month]["machines"][mid] = {
                "rolls": row["monthly_rolls"],
                "pieces": row["monthly_pieces"] or 0,
                "cycles": row["monthly_cycles"] or 0,
                "duration_min": round(row["monthly_duration_min"] or 0.0, 2)
            }
            
            # Accumulate machine totals
            if mid not in summary["machines"]:
                summary["machines"][mid] = {
                    "total_rolls": 0,
                    "total_pieces": 0,
                    "total_cycles": 0,
                    "total_duration_min": 0.0
                }
            
            summary["machines"][mid]["total_rolls"] += row["monthly_rolls"]
            summary["machines"][mid]["total_pieces"] += row["monthly_pieces"] or 0
            summary["machines"][mid]["total_cycles"] += row["monthly_cycles"] or 0
            summary["machines"][mid]["total_duration_min"] += row["monthly_duration_min"] or 0.0
        
        summary["monthly_data"] = [month_dict[m] for m in sorted(month_dict.keys())]
        
        # Round totals
        for mid in summary["machines"]:
            summary["machines"][mid]["total_duration_min"] = round(
                summary["machines"][mid]["total_duration_min"], 2
            )
        
        return summary
        
    except Exception as e:
        logger.error(f"Error fetching yearly summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/images")
def get_production_images(date: str = Query(..., description="Date in YYYY-MM-DD format")):
    """Get list of production images for a specific date"""
    try:
        import os
        from pathlib import Path
        
        images = []
        base_dir = Path("production_captures")
        
        # 1. Check legacy folder: production_captures/{date}/
        legacy_dir = base_dir / date
        if legacy_dir.exists():
            for file in legacy_dir.glob("*.jpg"):
                images.append({
                    "filename": file.name,
                    "path": str(file),
                    "size_bytes": file.stat().st_size,
                    "modified_time": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                })

        # 2. Check machine-specific folders: production_captures/Machine{ID}/{date}/
        for machine_id in ["A", "B"]:
            machine_dir = base_dir / f"Machine{machine_id}" / date
            if machine_dir.exists():
                for file in machine_dir.glob("*.jpg"):
                    images.append({
                        "filename": file.name,
                        "path": str(file),
                        "size_bytes": file.stat().st_size,
                        "modified_time": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                    })
        
        # Sort by filename (which includes timestamp)
        images.sort(key=lambda x: x["filename"])
        
        return {
            "date": date,
            "count": len(images),
            "images": images
        }
        
    except Exception as e:
        logger.error(f"Error fetching production images: {e}")
        raise HTTPException(status_code=500, detail=str(e))

