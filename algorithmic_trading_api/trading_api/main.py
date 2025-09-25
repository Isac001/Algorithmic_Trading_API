# Python and Library Imports
from fastapi import FastAPI
from trading_api.database.session import engine, Base
from trading_api.modules.data_sourcing.router import router as data_sourcing_router

# Create App Instance
app = FastAPI(
    title="Algorithmic Trading API",
    description="An API for backtesting and analyzing trading strategies.",
    version="1.0.0"
)

# Include Routers
app.include_router(data_sourcing_router, prefix="/data-sourcing", tags=["Data Sourcing"])

# Create Database Tables on startup (development only)
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    