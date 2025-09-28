# modules/health_check/routers.py

# Python and Library Imports
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

# Project Imports
from trading_api.database.session import get_db
from .schemas import HealthCheckResponse
from .services import HealthCheckService

# --- Router Configuration ---
# Note: No prefix is set here; it is included at the root ("/") in main.py
router = APIRouter(
    tags=["Health & Infrastructure"],
)

# ----------------------------------------------------
# Endpoint: Get Service Health Status (Requirement 21)
# ----------------------------------------------------
@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Returns the status of the service and database connectivity (Requirement 21)."
)
def get_health_check(
    db: Session = Depends(get_db)
):
    """
    Checks the connectivity status for external monitoring tools. 
    
    1. Tests the active connection to the PostgreSQL database (Requirement 60).
    2. Returns 503 Service Unavailable if any critical component (like the DB) fails.
    """
    service = HealthCheckService(db)
    status_data = service.get_health_status()
    
    # If the database or any critical check fails, raise 503 (Requirement 64)
    if status_data["status"] == "ERROR":
        # Raise HTTP exception with the detailed status data
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=status_data
        )
    
    # Return 200 OK with the health status data
    return status_data