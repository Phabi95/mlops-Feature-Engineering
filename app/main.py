"""
Optasia MLOps Feature Engineering API
------------------------------------
Main entry point for the FastAPI application. This module handles:
- Application lifecycle management (DB init/cleanup).
- Middleware for system monitoring and error logging.
- Integration with Prometheus for real-time metrics.
- High-performance feature generation via concurrent processing.
"""

import asyncio
import time
from fastapi.responses import ORJSONResponse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from fastapi.concurrency import run_in_threadpool

from app.api.endpoints import router as api_router
from app.core.metrics import ZERO_FEATURES_COUNTER, update_system_metrics
from app.services.feature_service import FeatureService
from app.core.logging_config import setup_app_logger
from app.schemas.customer import DataPayload
from app.db.database import (
    init_db, close_db,
    save_transactional_data_bulk,
    save_feature_data_bulk
)

# Initialize application-wide logger
logger = setup_app_logger("MainAPI")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles the application startup and shutdown sequence.
    Ensures that the SQLite database is properly initialized with WAL mode 
    and that all connections are gracefully closed during teardown.
    """
    await init_db()
    update_system_metrics()
    logger.info("Startup: Database connection established and metrics initialized.")
    yield
    await close_db()
    logger.info("Shutdown: Database connection closed and WAL checkpointed.")

# Using ORJSONResponse for the fastest possible serialization [cite: 5]
app = FastAPI(
    title="Optasia MLOps API",
    description="Real-time Feature Engineering Pipeline for Creditworthiness Evaluation",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    HTTP Middleware to track system performance and capture critical server failures.
    Fires system metric updates on every request to maintain dashboard accuracy.
    """
    response = await call_next(request)
    update_system_metrics()
    
    # Focused logging on 5xx errors to maintain a high signal-to-noise ratio in logs
    if response.status_code >= 500:
        logger.error(f"Server Error on {request.url.path} - Traceback required.")
    return response

# API Route Registration
app.include_router(api_router, prefix="/api/v1")

# Prometheus Monitoring Setup
# Excludes health and metrics endpoints to avoid polluting latency data
instrumentator = Instrumentator(excluded_handlers=["/metrics", "/health"])
instrumentator.add(metrics.default()).instrument(app).expose(app)

@app.post("/generate-features", status_code=status.HTTP_207_MULTI_STATUS)
async def generate_features(payload: DataPayload):
    """
    Core engine for feature extraction and data persistence.
    
    Logic Flow:
    1. Synchronous extraction of loan records from validated Pydantic models.
    2. Bulk persistence of raw transactional data to SQLite.
    3. Concurrent computation of customer features using asyncio.gather.
    4. Offloading CPU-bound feature calculation to a thread pool to avoid blocking the event loop.
    5. Final bulk save of computed features with type safety enforcement.
    """
    customers = payload.data

    # Prepare transactional records for bulk insertion
    loan_records = [
        (c.customer_ID, str(loan.loan_date), loan.amount,
         loan.fee, loan.loan_status, loan.term, loan.annual_income)
        for c in customers
        for loan in c.loans
    ]
    
    # Optimized bulk save to meet < 20ms latency requirements
    await save_transactional_data_bulk(loan_records)

    async def compute(customer):
        """Helper to process features per customer in a thread-safe manner."""
        service = FeatureService(customer.model_dump())
        # Use run_in_threadpool for CPU-bound feature engineering logic
        features = await run_in_threadpool(service.process_customer_features)
        return customer.customer_ID, features

    # Execute all customer feature calculations concurrently
    results = await asyncio.gather(*[compute(c) for c in customers])

    feature_records = []
    output = []
    
    for cid, feats in results:
        if feats:
            # Structuring data for SQLite with explicit type casting to prevent API misuse errors
            feature_records.append((
                str(cid),
                float(feats["total_loan_amount"]),
                float(feats["total_fees"]),
                float(feats["default_rate"]),
                int(feats["loan_count"]),
                int(feats["zero_value_count"])
            ))
            output.append({"customer_ID": cid, "status": "success", "features": feats})
        else:
            # Track failures via custom Prometheus counter
            ZERO_FEATURES_COUNTER.labels(endpoint="/generate-features").inc()
            output.append({"customer_ID": cid, "status": "no_features"})

    # Conditional bulk save to minimize I/O overhead
    if feature_records:
        await save_feature_data_bulk(feature_records)

    return ORJSONResponse({
        "processed_at": time.time(),
        "results": output
    })

@app.get("/health", tags=["Monitoring"])
async def health_check():
    """Liveness probe for orchestration and load balancing checks."""
    return {"status": "UP"}