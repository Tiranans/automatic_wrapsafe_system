"""Test database functionality"""
import sqlite3
from pathlib import Path

def test_sqlite():
    print(f"Python SQLite version: {sqlite3.sqlite_version}")
    print(f"Python sqlite3 module version: {sqlite3.version}")
    
    # Test create database
    db_path = "data/test.db"
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Test create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Test insert
    cursor.execute("INSERT INTO test (name) VALUES (?)", ("Test Machine A",))
    conn.commit()
    
    # Test select
    cursor.execute("SELECT * FROM test")
    rows = cursor.fetchall()
    
    print(f"\n✅ Database test successful!")
    print(f"   Created: {db_path}")
    print(f"   Rows: {len(rows)}")
    
    conn.close()
    
    # Cleanup
    Path(db_path).unlink()
    print(f"   Cleaned up test database")

if __name__ == "__main__":
    test_sqlite()