# Python and Library Imports
from pydantic import BaseModel, Field
from datetime import date
from typing import List, Optional

# =======================================================
# INPUT SCHEMA (Input para POST /data/indicators/update - Requisito 20)
# =======================================================
class IndicatorUpdateConfig(BaseModel):

    """Schema for data update and indicator calculation configuration."""
    
    tickers: List[str] = Field(..., description="List of asset tickers to update (e.g., ['PETR4.SA']).")
    start_date: Optional[date] = Field(None, description="Optional start date for data download.")
    end_date: Optional[date] = Field(None, description="Optional end date for data download.")
    
    # Requirement: Ensure we calculate indicators
    calculate_indicators: bool = Field(True, description="Whether to calculate and save indicators after download.")


# =======================================================
# OutputStatus
# =======================================================
class IndicatorUpdateResponse(BaseModel):

    """Schema for the job status response (similar to backtest run)."""
    
    status: str = Field(..., description="Status of the ingestion request (e.g., 'SCHEDULED').")
    message: str
    job_id: Optional[int] = Field(None, description="ID of the job run record.")