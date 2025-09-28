# Python and Library Imports
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine
from sqlalchemy import text 
from typing import Dict, Any
import logging

# Project Imports (Database Engine)
from trading_api.database.session import engine as db_engine 

# Basic logging configuration for job tracking
logger = logging.getLogger(__name__)

# Log level will be controlled by main.py, but set to DEBUG here for consistency
logger.setLevel(logging.DEBUG) 

# Health Check Service
class HealthCheckService:

    def __init__(self, db: Session):

        # The session is injected by FastAPI dependency but the engine is used for the direct check

        self.db = db 

    def get_health_status(self) -> Dict[str, str]:

        """
        Tests connectivity to the PostgreSQL database and returns the overall service health.
        (Requirement 21 & 60: Basic status and Postgres connection check).
        """

        db_status = "ERROR"
        db_message = ""
        
        # Test the PostgreSQL database connection
        try:
            # CORRECTION: Executes a simple SQL query (SELECT 1) to force an active connection check.
            # This forces the connection pool to discard stale/broken connections.
            with db_engine.connect() as connection:

                connection.execute(text("SELECT 1")) 
                db_status = "OK"
                db_message = "PostgreSQL connection is healthy."

        except Exception as e:
            
            # This exception is raised when the SELECT 1 fails due to a broken connection
            db_status = "ERROR"
            db_message = f"Failed to connect to PostgreSQL: {str(e)}"
            logger.error(f"Health Check DB Failure: {db_message}")
            
        # Determine the overall status
        overall_status = "OK" if db_status == "OK" else "ERROR"
        
        return {
            "status": overall_status,
            "database_status": db_status,
            "message": db_message,
        }