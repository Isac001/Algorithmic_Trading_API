# Python and Library Imports
import logging

# Project Imports
from trading_api.database.session import SessionLocal
from trading_api.modules.data_sourcing.services import ingest_and_update_market_data
from trading_api.modules.data_sourcing.schemas import IndicatorUpdateConfig

# --- Logging Setup ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Main Function
def run_daily_ingestion_job():

    """
    Simulates the daily routine to update market data and recalculate indicators (Requirement 59).
    This function serves as the entry point for the Docker Compose 'daily_worker' service.
    """

    logger.info("Starting DAILY INDICATOR INGESTION routine...")

    # Create a new, isolated database session for this long-running job
    db = SessionLocal()
    
    # 1. Define tickers to update (In a real scenario, this would query the DB for all active symbols)
    # Using hardcoded tickers for testing purposes
    test_tickers = ["PETR4.SA", "VALE3.SA"] 

    # 2. Create the configuration object for the service
    ingest_config = IndicatorUpdateConfig(
        tickers=test_tickers,
        calculate_indicators=True
    )
    
    try:

        # 3. Call the core service logic to fetch data, calculate indicators, and persist them
        ingest_and_update_market_data(db, ingest_config)
        logger.info("Daily ingestion job completed successfully.")
        
    except Exception as e:

        # Handle exceptions and log them
        logger.error(f"Daily ingestion job failed: {e}", exc_info=True)
        
    finally:

        # Ensure the job's database session is always closed
        db.close()

if __name__ == "__main__":

    # Execute the job when the script is called directly by Docker's 'command'
    run_daily_ingestion_job()