# Python and Library Imports
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import logging

# Project Imports
# 1. Configuration (assuming a Pydantic BaseSettings class)
from trading_api.core.config import settings 

# 2. Module Routers
from trading_api.modules.backtests.router import router as backtests_router
from trading_api.modules.data_sourcing.router import router as data_sourcing_router
from trading_api.modules.health_check.routers import router as health_router # Health Check Router

# --- Logging Setup ---
# Configure basic logging for the application using settings from the config file
logging.basicConfig(level=settings.LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# --- FastAPI Application Initialization ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    # Configure documentation access based on the environment (Requirement 47)
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None
)


# --- 1. Root Endpoint ---
@app.get("/", include_in_schema=False)
def root():
    """Redirects clients from the root URL to the OpenAPI documentation page."""
    return RedirectResponse(url="/docs")


# --- 2. Include Routers (Modular Monolith Pattern) ---

# A. BACKTESTS Router
# Exposes paths like: POST /backtests/run (Requirement 16)
app.include_router(
    backtests_router,
    prefix="/backtests",
    tags=["Backtests"],
)

# B. DATA SOURCING Router
# Exposes paths like: POST /data-sourcing/indicators/update (Requirement 20)
app.include_router(
    data_sourcing_router,
    prefix="/data-sourcing",
    tags=["Data Sourcing & Ingestion"],
)

# C. HEALTH CHECK Router
# Exposes the path: GET /health (Requirement 21)
app.include_router(
    health_router,
    tags=["Health & Infrastructure"],
    prefix="", # Placed at the root of the API
)

# --- 3. Optional: Lifespan Events (Database Initialization Logic is often placed here) ---
@app.on_event("startup")
async def startup_event():

    """Initial tasks to be run when the application starts, including logging start status."""

    logger.info(f"Starting {settings.PROJECT_NAME} API v{settings.VERSION}...")
    

@app.on_event("shutdown")
def shutdown_event():

    """Tasks to be run when the application shuts down."""
    
    logger.info(f"Shutting down {settings.PROJECT_NAME} API.")