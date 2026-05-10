"""
System Observability & Monitoring
---------------------------------
Defines Prometheus metrics to track API performance, resource utilization, 
και data quality. This module enables real-time monitoring of:
- Feature engineering data quality (Zero-value tracking).
- Request latency distribution.
- System resource health (CPU/Memory).
"""

from prometheus_client import Counter, Histogram, Gauge
import psutil
import os

# 1. Data Quality Metric: Tracks instances where features result in zero
# Requirement: "Count of features with zero values"
ZERO_FEATURES_COUNTER = Counter(
    "api_zero_features_total",
    "Total count of features with zero values",
    ["endpoint"] # Labeling allows granular tracking per API route
)

# 2. Performance Metric: High-resolution latency tracking
# Buckets are heavily weighted around the 20ms target (0.02s) to capture precision
FEATURE_LATENCY_HISTOGRAM = Histogram(
    "feature_engineering_duration_seconds",
    "Time spent performing feature engineering",
    ["customer_tier"],
    buckets=(.005, .01, .015, .02, .025, .05, .075, .1, .25, .5, 1.0)
)

# 3. Resource Metric: Real-time CPU Utilization
CPU_USAGE_GAUGE = Gauge(
    "api_cpu_usage_percent",
    "Current system-wide CPU usage percentage"
)

# 4. Resource Metric: Resident Set Size (RSS) Memory
MEMORY_USAGE_GAUGE = Gauge(
    "api_memory_usage_bytes",
    "Current resident memory usage in bytes"
)

def update_system_metrics():
    """
    Updates system-level gauges by interfacing with the OS via psutil.
    This function is typically triggered by middleware on every request
    to ensure the Grafana dashboard reflects the current state of the container.
    """
    try:
        process = psutil.Process(os.getpid())
        
        # System-wide CPU percentage (non-blocking interval for real-time reporting)
        CPU_USAGE_GAUGE.set(psutil.cpu_percent(interval=None))
        
        # Resident Set Size: The non-swapped physical memory the process has used
        MEMORY_USAGE_GAUGE.set(process.memory_info().rss)
    except Exception as e:
        # Metrics failure should not halt the API; we log and continue
        from app.core.logging_config import setup_app_logger
        logger = setup_app_logger("Metrics")
        logger.warning(f"Failed to update system metrics: {e}")