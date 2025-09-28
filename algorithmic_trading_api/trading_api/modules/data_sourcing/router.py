# Python and Library Imports
from fastapi import APIRouter, Depends, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import List

# Project Imports
from trading_api.database.session import get_db
from trading_api.modules.data_sourcing.services import ingest_and_update_market_data 
from trading_api.modules.data_sourcing.schemas import IndicatorUpdateConfig, IndicatorUpdateResponse 

# --- Router Configuration ---
router = APIRouter() # Prefix is typically set in main.py, e.g., /data-sourcing

# ----------------------------------------------------
# Endpoint 1: Update Market Data and Indicators (Asynchronous)
# ----------------------------------------------------
@router.post(
    "/indicators/update",
    response_model=IndicatorUpdateResponse,
    status_code=status.HTTP_202_ACCEPTED, 
    summary="Triggers the download of market data and calculation of technical indicators."
)
def update_indicators_endpoint(
    config: IndicatorUpdateConfig, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """
    Schedules a background task to fetch historical OHLCV data from Yahoo Finance, 
    calculate technical indicators (SMA, ATR, etc.), and store them in the database.
    
    1. Receives configuration details (tickers, dates, indicator flag).
    2. Schedules the long-running data ingestion and calculation in a background task.
    3. Returns the initial scheduling status immediately.
    """
    
    # Schedule the data ingestion and calculation job, passing the full config object.
    background_tasks.add_task(
        ingest_and_update_market_data, 
        db, 
        config 
    )

    # Return the initial scheduled status (202 Accepted).
    return IndicatorUpdateResponse(
        status="SCHEDULED", 
        message=f"Ingestion and calculation for {len(config.tickers)} tickers started in the background."
    )