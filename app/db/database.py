"""
Database Management Module
--------------------------
Handles asynchronous persistence using aiosqlite. 
This module is optimized for high-throughput write operations to meet 
the < 20ms latency requirement through:
- Write-Ahead Logging (WAL) mode for concurrent R/W.
- Memory-mapped I/O and optimized cache sizes.
- Bulk insertion strategies for transactional and feature data.
"""

import aiosqlite
import os
from typing import List, Optional, Dict, Any
from app.core.logging_config import setup_app_logger

# Configuration
logger = setup_app_logger("Database")
DB_NAME = os.environ.get("DB_PATH", "/data/optasia_mlops.db")

# Singleton-like connection state
_db_connection: Optional[aiosqlite.Connection] = None

async def init_db():
    """
    Initializes the SQLite database and configures performance tuning parameters.
    Creates necessary tables and indexes if they do not exist.
    
    Performance Tuning:
    - journal_mode=WAL: Allows simultaneous reads and writes.
    - synchronous=OFF: Maximizes write speed by offloading OS-level syncs.
    - mmap_size: Uses memory-mapping to speed up file access.
    """
    global _db_connection
    os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)

    try:
        _db_connection = await aiosqlite.connect(DB_NAME)
        _db_connection.row_factory = aiosqlite.Row

        # Performance PRAGMAs for MLOps workloads
        await _db_connection.execute("PRAGMA journal_mode=WAL;")
        await _db_connection.execute("PRAGMA synchronous=OFF;")
        await _db_connection.execute("PRAGMA cache_size=-10000;")  # 10MB Cache
        await _db_connection.execute("PRAGMA wal_autocheckpoint=0;") 
        await _db_connection.execute("PRAGMA busy_timeout=3000;")
        await _db_connection.execute("PRAGMA mmap_size=268435456;") # 256MB MMAP

        # Transactional Table Schema
        await _db_connection.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT,
                loan_date TEXT,
                amount REAL,
                fee REAL,
                loan_status TEXT,
                term TEXT,
                annual_income REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Feature Store Schema
        await _db_connection.execute("""
            CREATE TABLE IF NOT EXISTS features (
                customer_id TEXT PRIMARY KEY,
                total_loan_amount REAL,
                total_fees REAL,
                default_rate REAL,
                loan_count INTEGER,
                zero_value_count INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexing for optimized historical lookups
        await _db_connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_customer_id ON transactions(customer_id);"
        )

        await _db_connection.commit()
        logger.info(f"Database initialized successfully at {DB_NAME}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def close_db():
    """
    Gracefully closes the database connection and checkpoints the WAL file.
    Ensures data integrity before the application shuts down.
    """
    global _db_connection
    if _db_connection:
        await _db_connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        await _db_connection.close()
        logger.info("Database connection closed gracefully.")

async def save_transactional_data_bulk(records: List[tuple]):
    """
    Performs batch insertion of raw transaction records.
    Args:
        records: List of tuples containing loan data (customer_id, date, amount, etc.)
    """
    if not records or _db_connection is None:
        logger.warning("Attempted bulk save on empty records or null connection.")
        return
    try:
        query = """INSERT INTO transactions
                   (customer_id, loan_date, amount, fee, loan_status, term, annual_income)
                   VALUES (?, ?, ?, ?, ?, ?, ?)"""
        await _db_connection.executemany(query, records)
        await _db_connection.commit()
    except Exception as e:
        logger.error(f"Transactional bulk save failed: {e}")
        raise

async def save_feature_data_bulk(records: List[tuple]):
    """
    Upserts computed features into the features table.
    Ensures strict type casting to prevent SQLite API misuse errors.
    """
    if not records or _db_connection is None:
        return
    try:
        query = """INSERT OR REPLACE INTO features 
                   (customer_id, total_loan_amount, total_fees, default_rate, loan_count, zero_value_count) 
                   VALUES (?, ?, ?, ?, ?, ?)"""
        
        # Enforce type safety for SQLite persistence
        safe_records = [
            (str(r[0]), float(r[1]), float(r[2]), float(r[3]), int(r[4]), int(r[5]))
            for r in records
        ]
        
        await _db_connection.executemany(query, safe_records)
        await _db_connection.commit()
    except Exception as e:
        logger.error(f"Feature bulk save failed: {e}")
        raise

async def get_transaction_history(customer_id: str) -> List[Dict[str, Any]]:
    """Retrieves all historical transactions for a specific customer ID."""
    async with _db_connection.execute(
        "SELECT * FROM transactions WHERE customer_id = ? ORDER BY created_at DESC",
        (customer_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_feature_history(customer_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves the latest computed features for a specific customer ID."""
    async with _db_connection.execute(
        "SELECT * FROM features WHERE customer_id = ?", (customer_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None

async def delete_customer_data(customer_id: str) -> bool:
    """
    Removes all transactional and feature data associated with a customer.
    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    try:
        await _db_connection.execute("DELETE FROM transactions WHERE customer_id = ?", (customer_id,))
        await _db_connection.execute("DELETE FROM features WHERE customer_id = ?", (customer_id,))
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Deletion failed for customer {customer_id}: {e}")
        return False