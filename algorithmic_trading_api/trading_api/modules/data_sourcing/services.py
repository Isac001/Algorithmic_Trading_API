# Python and Library Imports
import yfinance as yf
from datetime import date, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import pandas as pd
import numpy as np
import logging

# Project Imports
from trading_api.database.models.market_data import Symbol, Price, Indicator
from trading_api.database.models.system import JobRun
# Import configuration schema from router module
from trading_api.modules.data_sourcing.schemas import IndicatorUpdateConfig 

# Basic logging configuration for job tracking
logger = logging.getLogger(__name__)
# Set log level to INFO by default
logger.setLevel(logging.INFO) 

# =========================================================
# HELPER FUNCTIONS FOR INDICATOR CALCULATION
# =========================================================

def calculate_sma(df: pd.DataFrame, length: int) -> pd.Series:
    """Calculates the Simple Moving Average (SMA - Requirement 24)."""
    # Calculate rolling mean on the 'Close' column
    return df['Close'].rolling(window=length).mean()

def calculate_atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Calculates the Average True Range (ATR - Requirement 26)."""
    
    # 1. Calculate True Range (TR) components
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())

    # TR is the maximum of the three components
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    # 2. Calculate Average True Range (EMA of TR)
    atr = tr.ewm(span=length, adjust=False).mean()
    return atr

# =========================================================
# CORE SERVICE LOGIC (Requirement 20)
# =========================================================
def ingest_and_update_market_data(db: Session, config: IndicatorUpdateConfig):
    
    # Extract tickers from configuration
    tickers = config.tickers
    
    # Create initial job record in the database
    job_run = JobRun(
        job_name="historical_data_ingestion",
        status="PENDING",
        message=f"Starting ingestion for tickers: {', '.join(tickers)}"
    )
    db.add(job_run)
    # Commit immediately to ensure job start is recorded
    db.commit()
    db.refresh(job_run)

    try:
        # List to collect all new indicator objects for bulk saving
        all_new_indicators = []
        
        # Determine start and end dates based on configuration or default (5 years)
        end_date = config.end_date if config.end_date else date.today()
        start_date = config.start_date if config.start_date else end_date - timedelta(days=5 * 365)


        for ticker_symbol in tickers:
            logger.info(f"Processing ticker: {ticker_symbol}")
            
            try:
                # 1. Get ticker info and find/create the symbol in the database (Requirement 50)
                ticker_info = yf.Ticker(ticker_symbol)
                info = ticker_info.info

                db_symbol = db.query(Symbol).filter(Symbol.ticker == ticker_symbol).first()

                if not db_symbol:
                    # Create symbol record if it doesn't exist
                    db_symbol = Symbol(
                        ticker=ticker_symbol,
                        name=info.get('longName', ticker_symbol),
                        exchange=info.get('exchange', 'N/A'),
                        currency=info.get('currency', 'N/A')
                    )
                    db.add(db_symbol)
                    db.commit() 
                    db.refresh(db_symbol)
                    logger.info(f"Created new symbol record: {ticker_symbol}")
                
                # 2. Fetch historical price data (OHLCV - Requirement 28)
                hist_data = ticker_info.history(start=start_date, end=end_date)
                
                if hist_data.empty:
                    logger.warning(f"No historical data found for {ticker_symbol}. Skipping persistence.")
                    continue

                # 3. Calculate Indicators
                if config.calculate_indicators:
                    hist_data['SMA_50'] = calculate_sma(hist_data, 50)
                    hist_data['SMA_200'] = calculate_sma(hist_data, 200)
                    hist_data['ATR_14'] = calculate_atr(hist_data, 14)


                # ===========================================================
                # BATCH FILTERING AND PERSISTENCE (Solving UniqueViolation)
                # ===========================================================
                
                # --- A. Filter Existing Prices ---
                # Retrieve all existing dates for this symbol ID
                existing_prices = db.query(Price.date).filter(Price.symbol_id == db_symbol.id).all()
                existing_dates_set = {p.date for p in existing_prices} 
                
                # Convert the DataFrame index dates (datetime.date objects) into a Pandas Series
                hist_dates_series = pd.Series(hist_data.index.normalize().date)
                
                # Create a boolean mask for NEW dates (where date is NOT in the existing set)
                mask = ~hist_dates_series.isin(existing_dates_set).values
                
                # Apply the mask to the DataFrame to get only new records
                new_hist_data = hist_data[mask]

                if new_hist_data.empty:
                    logger.info(f"No new price data found for {ticker_symbol}. Skipping persistence.")
                    continue
                    
                # --- B. Build Lists of Objects for BULK INSERT ---
                current_prices = []
                new_indicators = []

                for index, row in new_hist_data.iterrows(): 
                    price_date = index.date()
                    
                    if not np.isnan(row['Close']):
                        
                        # Create Price object (Requirement 51)
                        db_price = Price(
                            symbol_id=db_symbol.id,
                            date=price_date,
                            open=row['Open'].item(),
                            high=row['High'].item(),
                            low=row['Low'].item(),
                            close=row['Close'].item(),
                            volume=row['Volume'].item()
                        )
                        current_prices.append(db_price)
                        
                        # Persist Indicators (Requirement 52)
                        if config.calculate_indicators:
                            indicators_to_save = [
                                ('SMA', 'SMA_50', 50), 
                                ('SMA', 'SMA_200', 200), 
                                ('ATR', 'ATR_14', 14),
                            ]
                            
                            for name, col_name, length in indicators_to_save:
                                indicator_value = row.get(col_name)

                                if indicator_value is not None and not np.isnan(indicator_value):
                                    db_indicator = Indicator(
                                        symbol_id=db_symbol.id,
                                        date=price_date,
                                        name=name,
                                        value=indicator_value.item(),
                                        params_hash=f"{name}_{length}"
                                    )
                                    new_indicators.append(db_indicator)
                
                # --- C. Bulk Save (Final Step for the Ticker) ---
                if current_prices:

                    # Bulk save new price records
                    db.bulk_save_objects(current_prices)
                    logger.info(f"Bulk saved {len(current_prices)} NEW price records for {ticker_symbol}.")

                if new_indicators:

                    # Bulk save new indicator records
                    db.bulk_save_objects(new_indicators)
                    logger.info(f"Bulk saved {len(new_indicators)} NEW indicator records for {ticker_symbol}.")


            except Exception as e:

                logger.error(f"Error processing ticker {ticker_symbol}: {e}", exc_info=True)

                # Rollback current changes for this ticker and proceed to the next
                db.rollback() 
                continue

        # 6. Finalization: Commit JobRun Status
        job_run.status = "SUCCESS"
        job_run.message = "Historical data and indicator calculation completed successfully."
        db.commit()
        logger.info("Data ingestion and indicator calculation complete.")
        return {"status": "success", "message": "Data ingestion and indicator calculation complete."}

    except Exception as e:

        # Capture unexpected critical errors (e.g., DB connection failure)
        logger.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        db.rollback()
        job_run.status = "FAILURE"
        job_run.message = f"An unexpected critical error occurred: {str(e)}"
        db.commit()
        return {"status": "error", "message": job_run.message}