# # Python and Library Imports
# from fastapi import FastAPI
# from trading_api.database.session import engine, Base

# # Import the router for the Data Sourcing module (existing)
# from trading_api.modules.data_sourcing.router import router as data_sourcing_router

# # =======================================================
# # NEW STEP: Import the router for the Backtests module
# # =======================================================
# from trading_api.modules.backtests.router import router as backtests_router 


# # --- Application Setup ---
# app = FastAPI(
#     title="Algorithmic Trading API",
#     description="An API for backtesting and analyzing trading strategies.",
#     version="1.0.0"
# )

# # =======================================================
# # Include API Routers
# # =======================================================

# # Include the Data Sourcing router
# app.include_router(
#     data_sourcing_router, 
#     prefix="/data-sourcing", 
#     tags=["Data Sourcing"]
# )

# # NEW STEP: Include the Backtests router
# # The internal router already uses the prefix "/backtests", so we use no prefix here.
# app.include_router(
#     backtests_router, 
#     tags=["Backtests"]
# )


# # --- Database Initialization ---
# # Create Database Tables on startup (development only)
# @app.on_event("startup")
# def on_startup():
#     """
#     Creates all database tables defined by SQLAlchemy Base metadata.
#     This is primarily used for local development environments.
#     """
#     # NOTE: Alembic (database migration tool) is typically used for production/staging environments.
#     Base.metadata.create_all(bind=engine)

# Python and Library Imports
from fastapi import FastAPI
from trading_api.database.session import engine, Base

# Import the router for the Data Sourcing module (existing)
from trading_api.modules.data_sourcing.router import router as data_sourcing_router

# Import the router for the Backtests module
from trading_api.modules.backtests.router import router as backtests_router 


# --- Application Setup ---
app = FastAPI(
    title="Algorithmic Trading API",
    description="An API for backtesting and analyzing trading strategies.",
    version="1.0.0"
)

# =======================================================
# Include API Routers
# =======================================================

# Include the Data Sourcing router
# This exposes the path: POST /data-sourcing/indicators/update (Requirement 20)
app.include_router(
    data_sourcing_router, 
    prefix="/data-sourcing", 
    tags=["Data Sourcing"]
)

# Include the Backtests router
# This exposes the paths: POST /backtests/run, GET /backtests, GET /backtests/{id}/results
app.include_router(
    backtests_router, 
    tags=["Backtests"]
)


# --- Database Initialization ---
@app.on_event("startup")
def on_startup():
    """
    Creates all database tables defined by SQLAlchemy Base metadata.
    This is primarily used for local development environments.
    (Alembic is generally used for production migrations).
    """
    Base.metadata.create_all(bind=engine)