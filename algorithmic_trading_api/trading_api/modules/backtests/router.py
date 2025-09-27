# Python and Library Imports
from fastapi import APIRouter, Depends, status, BackgroundTasks, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

# Project imports
from .schemas import (
    BacktestRunRequest, 
    BacktestRunResponse, 
    BacktestResultResponse,
    BacktestListResponse, # Response for paginated backtest listing
    BacktestListItem      # Individual item model in the list
)

from .services import BacktestingService 
from trading_api.database.session import get_db 

# --- Router Configuration ---
router = APIRouter(
    prefix="/backtests",
    tags=["Backtests"],
)

# ----------------------------------------------------
# Endpoint 1: Start Backtest (Asynchronous)
# ----------------------------------------------------
@router.post(
    "/run", 
    response_model=BacktestRunResponse, 
    status_code=status.HTTP_202_ACCEPTED, # 202: Accepted status indicates asynchronous processing
    summary="Triggers a trading strategy backtest."
)
def run_backtest(
    request_data: BacktestRunRequest,
    background_tasks: BackgroundTasks, # Dependency for asynchronous simulation execution
    db: Session = Depends(get_db)
):
    """
    Schedules the execution of a long-running backtest in the background.
    
    1. Creates an initial record in the database with 'PENDING' status.
    2. Adds the backtest simulation execution to a background task queue.
    3. Immediately returns the ID and 'PENDING' status to the client.
    """
    
    service = BacktestingService(db)
    
    # 1. Create the initial backtest record in the DB, returning its ID.
    # The initial status is set to PENDING.
    backtest_id = service.create_pending_backtest(request_data.model_dump())
    
    # 2. Schedule the execution of the long-duration simulation. 
    # This prevents the HTTP request from being blocked by processing time.
    background_tasks.add_task(service.execute_backtest_job_safe, backtest_id)

    # 3. Return the initial response (202 Accepted).
    return BacktestRunResponse(
        backtest_id=backtest_id, 
        status="PENDING"
    )

# ----------------------------------------------------
# Endpoint 2: List Backtests (With Pagination and Filters)
# ----------------------------------------------------
@router.get(
    "", # Root path: /backtests
    response_model=BacktestListResponse,
    summary="Lists backtests with pagination and filters."
)
def list_backtests(
    db: Session = Depends(get_db),
    # Filter parameters for the query string
    ticker: Optional[str] = Query(None, description="Filter by asset ticker."),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type."),
    status: Optional[str] = Query(None, description="Filter by status (PENDING, COMPLETED, FAILED)."),
    # Pagination parameters
    page: int = Query(1, ge=1, description="Page number (starts at 1)."),
    size: int = Query(10, ge=1, le=100, description="Page size (max. 100).")
):
    """
    Returns a paginated list of all backtests, with the option to filter 
    by criteria such as asset, strategy, or status.
    """
    service = BacktestingService(db)
    
    # Delegates the listing logic (filters and pagination) to the service layer.
    return service.list_backtests(
        db=db,
        ticker=ticker,
        strategy_type=strategy_type,
        status=status,
        page=page,
        size=size
    )

# ----------------------------------------------------
# Endpoint 3: Get Detailed Results
# ----------------------------------------------------
@router.get(
    "/{backtest_id}/results",
    response_model=BacktestResultResponse,
    summary="Returns the detailed results and equity curve of a completed backtest."
)
def get_backtest_results(
    backtest_id: int,
    db: Session = Depends(get_db)
):
    """
    Fetches performance metrics, trade list, and the equity curve for a backtest. 
    Raises HTTPException if the backtest does not exist or is not completed.
    """
    service = BacktestingService(db)
    
    # The service method handles business rules: 404 (not found) and 
    # 409 (in progress - results not yet available).
    return service.get_backtest_results(backtest_id, db)