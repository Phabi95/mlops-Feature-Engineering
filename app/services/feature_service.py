"""
Feature Engineering Service
--------------------------
Core engine for extracting risk-related features from transactional data.
Optimized using O(n) single-pass logic to meet strict latency targets.
"""

from app.core.logging_config import setup_app_logger
from app.core.metrics import ZERO_FEATURES_COUNTER

class FeatureService:
    def __init__(self, customer_data: dict):
        # Data is pre-validated by Pydantic schemas before initialization
        self.customer_data = customer_data
        self.logger = setup_app_logger("FeatureService")

    def process_customer_features(self):
        """
        Derives customer-level features via single-pass iteration.
        Returns computed features or None if no loan data exists.
        """
        customer_id = self.customer_data.get('customer_ID', 'unknown')
        loans = self.customer_data.get('loans', [])
        
        if not loans:
            return None

        # Performance: Single-pass variable initialization
        total_amt = 0.0
        total_fees = 0.0
        default_count = 0
        valid_loan_count = 0

        # Efficient O(n) processing loop
        for l in loans:
            amt = l.get('amount', 0.0)
            fee = l.get('fee', 0.0)
            
            total_amt += amt
            total_fees += fee
            
            # Binary status check for default rate calculation
            if str(l.get('loan_status')) == "1":
                default_count += 1
            
            valid_loan_count += 1

        if valid_loan_count == 0:
            return None

        # Derived Feature Mapping
        features = {
            "total_loan_amount": round(total_amt, 2),
            "total_fees": round(total_fees, 2),
            "loan_count": valid_loan_count,
            "default_rate": round(default_count / valid_loan_count, 4)
        }

        # Quality Control: Vector-like zero-value counting
        zero_count = list(features.values()).count(0)
        features["zero_value_count"] = zero_count

        # Observability: Update Prometheus telemetry for data quality tracking
        ZERO_FEATURES_COUNTER.labels(endpoint="/generate-features").inc(zero_count)

        return features