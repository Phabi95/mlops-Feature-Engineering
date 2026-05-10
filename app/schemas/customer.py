"""
Data Validation Schemas
-----------------------
This module defines the Pydantic models used for strict schema validation.
It enforces the business logic and constraints provided by Optasia, including:
- Customer ID identification (ASCII & Length constraints).
- Loan-level numerical boundaries.
- Complex creditworthiness arithmetic rules based on income brackets.
"""

from typing import List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator


class LoanSchema(BaseModel):
    """
    Schema for individual loan records.
    Validates transactional details and enforces creditworthiness constraints.
    """
    loan_date: datetime
    # Constraints based on assignment requirements
    amount: float = Field(ge=100, le=1000, description="Loan amount must be between 100 and 1000")
    fee: float = Field(ge=10, le=50, description="Transaction fee must be between 10 and 50")
    loan_status: str = Field(pattern="^[01]$", description="0 for Repaid, 1 for Defaulted")
    term: str = Field(pattern="^(short|long)$", description="Term must be 'short' or 'long' (case-sensitive)")
    annual_income: float = Field(ge=100, le=10000000, description="Income must be within the specified range")

    @field_validator('loan_date', mode='before')
    @classmethod
    def parse_date(cls, v: str) -> datetime:
        """
        Custom parser to handle string-to-datetime conversion.
        Expected format: DD/MM/YYYY
        """
        if isinstance(v, str):
            try:
                return datetime.strptime(v, "%d/%m/%Y")
            except ValueError:
                raise ValueError("Invalid date format. Expected DD/MM/YYYY")
        return v

    @field_validator('amount', 'fee', 'annual_income', mode='before')
    @classmethod
    def to_float(cls, v) -> float:
        """Ensures numerical string inputs are correctly cast to floats before validation."""
        if isinstance(v, str):
            return float(v)
        return v

    @model_validator(mode='after')
    def validate_creditworthiness(self) -> 'LoanSchema':
        """
        Implements the mandatory Arithmetic Statement for credit evaluation.
        Verifies if the total commitment (amount + fee) exceeds the allowed 
        threshold per income bracket.
        """
        total_commitment = self.amount + self.fee
        income = self.annual_income

        # Rule 1: Income 100 - 1,000 -> Max 110
        if 100 <= income <= 1000 and total_commitment > 110:
            raise ValueError(f"Total commitment ({total_commitment}) exceeds 110 for low income bracket.")
            
        # Rule 2: Income 1,000 - 10,000 -> Max 220
        if 1000 < income <= 10000 and total_commitment > 220:
            raise ValueError(f"Total commitment ({total_commitment}) exceeds 220 for mid-low income bracket.")
            
        # Rule 3: Income 10,000 - 100,000 -> Max 550
        if 10000 < income <= 100000 and total_commitment > 550:
            raise ValueError(f"Total commitment ({total_commitment}) exceeds 550 for mid-high income bracket.")
            
        # Rule 4: Income 100,000 - 10,000,000 -> Max 1,050
        if 100000 < income <= 10000000 and total_commitment > 1050:
            raise ValueError(f"Total commitment ({total_commitment}) exceeds 1050 for high income bracket.")
        
        return self


class CustomerSchema(BaseModel):
    """
    Schema for customer-level data validation.
    Enforces ID length and character set restrictions.
    """
    customer_ID: str = Field(
        min_length=10, 
        max_length=20, 
        pattern="^[ -~]+$", 
        description="ID must be 10-20 characters long and contain only ASCII printable characters"
    )
    loans: List[LoanSchema]


class DataPayload(BaseModel):
    """
    Root payload schema for the /generate-features endpoint.
    Expects a wrapper 'data' field containing a list of customers.
    """
    data: List[CustomerSchema]