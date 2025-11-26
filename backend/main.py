from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import status, stream, control, production
import sqlite3
from datetime import datetime
from typing import Optional

app = FastAPI(title="BM9 WrapSafe API")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(status.router, prefix="/api/status", tags=["Status"])
app.include_router(stream.router, prefix="/api/stream", tags=["Stream"])
app.include_router(control.router, prefix="/api/control", tags=["Control"])
app.include_router(production.router, prefix="/api/production", tags=["Production"])

@app.get("/")
def read_root():
    return {"message": "BM9 WrapSafe API is running"}

@app.get("/api/production/logs")
async def get_production_logs(
    machine: Optional[str] = None,
    date: Optional[str] = None,
    shift: Optional[int] = None
):
    """Get production logs with filters"""
    conn = sqlite3.connect("data/machine_events.db")
    cursor = conn.cursor()
    
    query = "SELECT * FROM production_logs WHERE 1=1"
    params = []
    
    if machine:
        query += " AND machine_name = ?"
        params.append(f"Machine {machine}")
    
    if date:
        query += " AND date = ?"
        params.append(date)
    
    if shift:
        query += " AND shift_id = ?"
        params.append(shift)
    
    query += " ORDER BY log_id DESC LIMIT 100"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    columns = [desc[0] for desc in cursor.description]
    results = [dict(zip(columns, row)) for row in rows]
    
    conn.close()
    
    return {"logs": results}

@app.get("/api/production/summary")
async def get_production_summary(date: Optional[str] = None):
    """Get production summary by shift"""
    conn = sqlite3.connect("data/machine_events.db")
    cursor = conn.cursor()
    
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute("""
        SELECT 
            p.shift_id,
            s.shift_name,
            p.machine_name,
            COUNT(*) as total_rolls,
            SUM(p.pieces_completed) as total_pieces,
            SUM(p.film_wrap_cycle) as total_cycles
        FROM production_logs p
        JOIN shifts s ON p.shift_id = s.shift_id
        WHERE p.date = ?
        GROUP BY p.shift_id, p.machine_name
        ORDER BY p.shift_id, p.machine_name
    """, (date,))
    
    rows = cursor.fetchall()
    
    summary = []
    for row in rows:
        summary.append({
            'shift_id': row[0],
            'shift_name': row[1],
            'machine_name': row[2],
            'total_rolls': row[3],
            'total_pieces': row[4],
            'total_cycles': row[5]
        })
    
    conn.close()
    
    return {"date": date, "summary": summary}
