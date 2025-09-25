# Python and Library Imports
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

# Project Imports
from trading_api.database.session import get_db
from trading_api.modules.data_sourcing.services import fetch_and_store_historical_data
from trading_api.modules.data_sourcing.schemas import DataIngestionRequest

# Set Router
router = APIRouter()

# Endpoint
@router.post("/ingest-historical-data", status_code=202)
def ingest_historical_data_endpoint(
    request: DataIngestionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Ingest historical OHLCV data for a list of tickers.

    This endpoint starts a background task to fetch and store market data,
    allowing the API to respond immediately.

    Args:
        request (DataIngestionRequest): The request body containing a list of tickers.
        background_tasks (BackgroundTasks): The FastAPI object to manage background tasks.
        db (Session): The SQLAlchemy database session.

    Returns:
        dict: A message confirming the background job has started.
    """
    background_tasks.add_task(fetch_and_store_historical_data, db, request.tickers)
    return {"message": "Data ingestion job started in the background."}