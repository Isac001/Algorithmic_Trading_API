# Python and Library Imports
import yfinance as yf
from datetime import date, timedelta
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

# Project Imports
from trading_api.database.models.market_data import Symbol, Price
from trading_api.database.models.system import JobRun

# Main Function
def fetch_and_store_historical_data(db: Session, tickers: List[str]):

    """
    Fetches historical data from Yahoo Finance and stores it in the database.

    This routine is designed to be idempotent, meaning it can be run multiple times
    without causing errors, as it checks for existing data before insertion.

    Args:
        db (Session): The SQLAlchemy database session for database interactions.
        tickers (List[str]): A list of ticker symbols to fetch data for.
    
    Returns:
        dict: A dictionary with the status and a completion message for the job.
    """

    # Create an initial record in the `job_runs` table to monitor the routine's execution.
    job_run = JobRun(
        job_name="historical_data_ingestion",
        status="PENDING",
        message=f"Starting ingestion for tickers: {', '.join(tickers)}"
    )
    db.add(job_run)
    db.commit()
    db.refresh(job_run)

    try:
        # Iterate over each ticker provided in the request.
        for ticker_symbol in tickers:

            try:

                # 1. Get ticker info and find/create the symbol in the database.
                ticker_info = yf.Ticker(ticker_symbol)
                info = ticker_info.info

                # Retrieve the symbol from the database.
                db_symbol = db.query(Symbol).filter(Symbol.ticker == ticker_symbol).first()

                # Check if the symbol already exists in the database.
                if not db_symbol:

                    # If the symbol doesn't exist, create a new record in the `symbols` table.
                    db_symbol = Symbol(
                        ticker=ticker_symbol,
                        name=info.get('longName', ticker_symbol),
                        exchange=info.get('exchange', 'N/A'),
                        currency=info.get('currency', 'N/A')
                    )
                    db.add(db_symbol)
                    db.commit()
                    db.refresh(db_symbol)
                
                # 2. Fetch historical price data for a 5-year period.
                end_date = date.today()
                start_date = end_date - timedelta(days=5 * 365)
                hist_data = ticker_info.history(start=start_date, end=end_date)
                
                # Iterate over the historical data to insert each day's prices.
                for index, row in hist_data.iterrows():
                    price_date = index.date()
                    
                    # 3. Check if the price data for this date already exists to prevent duplicates.
                    price_exists = db.query(Price).filter_by(
                        symbol_id=db_symbol.id, 
                        date=price_date
                    ).first()

                    # If the price record doesn't exist, create a new one.
                    if not price_exists:

                        try:

                            # If the price record doesn't exist, create a new one.
                            db_price = Price(
                                symbol_id=db_symbol.id,
                                date=price_date,
                                # Convert Numpy types to native Python types before insertion.
                                open=row['Open'].item(),
                                high=row['High'].item(),
                                low=row['Low'].item(),
                                close=row['Close'].item(),
                                volume=row['Volume'].item()
                            )

                            # Add and commit the price record to the database.
                            db.add(db_price)
                            db.commit()

                        except IntegrityError:

                            # Handle concurrent requests trying to insert the same data.
                            db.rollback()
                            continue

            # Catch any unexpected errors for a specific ticker.
            except Exception as e:

                # If an error occurs with a specific ticker, mark the job as a failure.
                db.rollback()
                job_run.status = "FAILURE"
                job_run.message = f"Failed to ingest data for ticker {ticker_symbol}: {str(e)}"
                db.commit()

                # Return an error message to the client.
                return {"status": "error", "message": job_run.message}

        # If the loop completes successfully, update the job status.
        job_run.status = "SUCCESS"
        job_run.message = "Historical data ingestion completed successfully."
        db.commit()
        return {"status": "success", "message": "Data ingestion complete."}

    # Catch any unexpected errors, mark the job as a failure, and return an error.
    except Exception as e:

        # Catch any unexpected errors, mark the job as a failure, and return an error.
        db.rollback()
        job_run.status = "FAILURE"
        job_run.message = f"An unexpected error occurred: {str(e)}"
        db.commit()
        return {"status": "error", "message": job_run.message}