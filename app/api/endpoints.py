"""
API Endpoints Module
--------------------
Defines the operational routes for data retrieval and management, including:
- Retrieval of historical transactional records.
- Access to historical feature engineering results.
- Data deletion capabilities to ensure system hygiene and compliance.
- Internal statistics for database monitoring.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from app.db.database import get_transaction_history, get_feature_history, delete_customer_data
from app.core.logging_config import setup_app_logger

# Initialize router with specific tags for better OpenAPI/Swagger organization
router = APIRouter(tags=["Data Management"])
logger = setup_app_logger("Endpoints")

@router.get("/history/transactions/{customer_id}")
async def fetch_transaction_history(customer_id: str) -> Dict[str, Any]:
    """
    Retrieves the complete historical transactional log for a specific customer.
    
    Args:
        customer_id: The unique identifier for the customer (10-20 ASCII chars).
        
    Returns:
        A dictionary containing the customer_id and a list of all historical transactions.
        
    Raises:
        HTTPException 404: If no transactions exist for the given ID in the database.
    """
    data: List[Dict[str, Any]] = await get_transaction_history(customer_id)
    
    if not data:
        # Warning log helps identify missed lookups or non-existent IDs in the audit trail
        logger.warning(f"Lookup failed: No transactions found for customer {customer_id}")
        raise HTTPException(status_code=404, detail="Customer transactional history not found")
        
    return {"customer_id": customer_id, "history": data}

@router.get("/history/features/{customer_id}")
async def fetch_feature_history(customer_id: str) -> Dict[str, Any]:
    """
    Retrieves the latest computed feature engineering results for a specific customer.
    This fulfills the requirement for accessing historic feature data.
    
    Returns:
        The most recent feature set (loan count, default rate, etc.) for the customer.
        
    Raises:
        HTTPException 404: If no features have been generated for this customer yet.
    """
    data: Optional[Dict[str, Any]] = await get_feature_history(customer_id)
    
    if not data:
        logger.warning(f"Lookup failed: No feature records found for customer {customer_id}")
        raise HTTPException(status_code=404, detail="Feature history not found")
        
    return {"customer_id": customer_id, "features": data}

@router.delete("/customer/{customer_id}")
async def remove_customer(customer_id: str) -> Dict[str, str]:
    """
    Executes a hard delete of all data associated with a customer.
    Cleans up records from both 'transactions' and 'features' tables to ensure atomicity.
    
    Returns:
        A success status message upon successful deletion.
        
    Raises:
        HTTPException 500: If the database operation fails unexpectedly.
    """
    success: bool = await delete_customer_data(customer_id)
    
    if not success:
        logger.error(f"Integrity Error: Failed to delete data for customer {customer_id}")
        raise HTTPException(status_code=500, detail="Internal error during data deletion")
    
    logger.info(f"Cleanup: Customer {customer_id} and associated data removed successfully.")
    return {"status": "success", "message": f"Customer {customer_id} successfully removed from persistence layer."}

@router.get("/api/v1/stats", include_in_schema=False)
async def get_stats() -> Dict[str, int]:
    """
    Internal utility to monitor database growth and record counts.
    Primarily used for high-level observability during performance testing.
    """
    from app.db.database import _db_connection
    
    # Direct execution for monitoring purposes
    async with _db_connection.execute("SELECT COUNT(*) FROM transactions") as c:
        transactions_count = (await c.fetchone())[0]
        
    async with _db_connection.execute("SELECT COUNT(*) FROM features") as c:
        features_count = (await c.fetchone())[0]
        
    return {
        "total_transactions_stored": transactions_count,
        "total_feature_records_stored": features_count
    }