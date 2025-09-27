# trading_api/modules/backtests/services.py

# Python and Library Imports
import backtrader as bt
from datetime import datetime, date, timezone
from sqlalchemy.orm import Session, joinedload # joinedload for eager loading in listing
from sqlalchemy.exc import SQLAlchemyError 
import pandas as pd
import logging
from typing import Dict, Any, List, Optional

# FastAPI Dependencies
from fastapi import HTTPException, Query 

# Project Imports (Adjustments for your structure)
from trading_api.database.models.market_data import Price, Symbol 
from trading_api.database.models.backtest import Backtest, Trade, DailyPosition, Metric
from trading_api.strategies.sma_cross import SMACross 
from trading_api.database.session import SessionLocal 
from trading_api.modules.backtests.schemas import (
    MetricSchema, TradeSchema, DailyPositionSchema, BacktestListItem # Output and listing schemas
)


# Basic logging configuration for job tracking
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) 

# Maps strategy names (strings from API request) to their corresponding Backtrader classes
STRATEGY_MAPPING = {
    "sma_cross": SMACross,
}

# ----------------------------------------------------------------------
# Core Logic: Backtesting Service
# ----------------------------------------------------------------------
class BacktestingService:

    def __init__(self, db: Session):
        # Session injected by FastAPI dependency
        self.db = db

    # =========================================================
    # CREATE BACKTEST RECORD
    # =========================================================
    def create_pending_backtest(self, backtest_params: Dict[str, Any]) -> int:
        """
        Creates the initial backtest record in the database with status 'PENDING'.
        This step must be synchronous to return the backtest_id immediately (Requirement 17).
        """
        backtest_record = Backtest(
            ticker=backtest_params["ticker"],
            start_date=backtest_params["start_date"],
            end_date=backtest_params["end_date"],
            strategy_type=backtest_params["strategy_type"],
            strategy_params_json=backtest_params.get("strategy_params", {}),
            initial_cash=backtest_params.get("initial_cash", 100000.0),
            commission=backtest_params.get("commission", 0.001),
            status="PENDING"
        )
        self.db.add(backtest_record)
        self.db.commit()
        self.db.refresh(backtest_record)
        return backtest_record.id

    # =========================================================
    # BACKGROUND JOB EXECUTION
    # =========================================================
    def execute_backtest_job_safe(self, backtest_id: int):
        """
        Safe wrapper for background task execution. 
        It creates a new database session and handles exceptions safely.
        """
        logger.debug(f"[{backtest_id}] Safe job wrapper started. Creating new DB session.")
        # Crucial: Create a new session for the background thread/task
        db_job = SessionLocal()
        try:
            self.execute_backtest_job(backtest_id, db_job)
        except Exception as e:
            # Catch all exceptions to log them and prevent the background task from crashing silently
            logger.error(f"[{backtest_id}] Unhandled exception in safe wrapper: {e}", exc_info=True)
            db_job.rollback() 
        finally:
            logger.debug(f"[{backtest_id}] Closing job DB session.")
            db_job.close()


    def execute_backtest_job(self, backtest_id: int, db: Session):
        """
        Executes the actual backtest logic using Backtrader and persists results.
        This runs in a background task with its own database session.
        """
        backtest_record = None
        
        try:
            logger.debug(f"[{backtest_id}] Backtest execution started.")
            # Retrieve the backtest record from the database
            backtest_record = db.query(Backtest).filter(Backtest.id == backtest_id).first()
            
            # 1. Update status to RUNNING
            backtest_record.status = "RUNNING"
            db.commit()
            logger.debug(f"[{backtest_id}] Status updated to RUNNING in DB.")

            # 2. Get data from the database
            backtest_params = {
                "ticker": backtest_record.ticker,
                "start_date": backtest_record.start_date,
                "end_date": backtest_record.end_date,
            }
            data_feed = self._get_data_from_db(backtest_params, db)
            
            # 3. Backtrader Configuration and Execution
            cerebro = bt.Cerebro()
            cerebro.adddata(data_feed)
            cerebro.broker.setcash(backtest_record.initial_cash)
            cerebro.broker.setcommission(commission=backtest_record.commission)
            
            StrategyClass = STRATEGY_MAPPING[backtest_record.strategy_type]
            cerebro.addstrategy(StrategyClass, **backtest_record.strategy_params_json)

            # Add required analyzers
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')
            cerebro.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')

            the_result = cerebro.run(runonce=False) 
            logger.debug(f"[{backtest_id}] Backtrader executed. Starting persistence.")

            # 4. Persistence of Results
            self._save_results(the_result[0], backtest_record.id, db)
            
            # 5. Finalization: Update status to COMPLETED
            backtest_record.status = "COMPLETED"
            db.add(backtest_record) 
            
            logger.debug(f"[{backtest_id}] Attempting final COMMIT of all data.")
            db.commit()
            logger.debug(f"[{backtest_id}] Final COMMIT successful. Backtest COMPLETED.")

        except Exception as e:
            logger.error(f"[{backtest_id}] CRITICAL ERROR in job. Performing ROLLBACK. Error: {e}", exc_info=True)
            
            # Rollback the session to undo any partial changes
            db.rollback()
            
            # Attempt to save the FAILED status, even after a rollback
            if backtest_record: 
                try:
                    backtest_record.status = "FAILED"
                    db.add(backtest_record) 
                    db.commit()
                    logger.debug(f"[{backtest_id}] Failure status (FAILED) saved successfully.")
                except Exception as save_err:
                    logger.error(f"[{backtest_id}] Failed to save FAILED status: {save_err}", exc_info=True)
            
            # Re-raise the exception for external logging/monitoring
            raise e
            
    # ---------------------------------------------------------
    # HELPER METHODS (Data & Persistence)
    # ---------------------------------------------------------
    def _get_data_from_db(self, backtest_params: Dict[str, Any], db: Session):
        """Fetches price data from the 'prices' table and formats it for Backtrader (PandasData)."""
        symbol_record = db.query(Symbol).filter(Symbol.ticker == backtest_params["ticker"]).first()
        if not symbol_record:
            # Use ValueError as this is a backend failure, which execute_backtest_job handles
            raise ValueError(f"Ticker '{backtest_params['ticker']}' not found in the Symbol table.")
        
        # Build the query for price data within the specified date range
        query = db.query(Price).filter(
            Price.symbol_id == symbol_record.id,
            Price.date >= backtest_params["start_date"],
            Price.date <= backtest_params["end_date"]
        ).order_by(Price.date)
        
        # Read the SQL results directly into a Pandas DataFrame
        df = pd.read_sql(query.statement, db.bind)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Convert the DataFrame into a Backtrader data feed
        data_feed = bt.feeds.PandasData(dataname=df)
        return data_feed

    def _save_results(self, strategy_instance, backtest_id: int, db: Session):
        """Extracts results from Backtrader analyzers and persists them to the database."""
        
        # Extract data from Backtrader Analyzers
        metrics = strategy_instance.analyzers.sharpe.get_analysis()
        trade_analyzer = strategy_instance.analyzers.trade_analyzer 
        trade_data = trade_analyzer.get_analysis()
        drawdown_data = strategy_instance.analyzers.drawdown.get_analysis()
        pyfolio_analyzer = strategy_instance.analyzers.pyfolio
        
        # Calculate total return from the PyFolio returns series
        returns_series = pyfolio_analyzer.get_analysis().get('returns')
        total_return = returns_series.iloc[-1] if returns_series is not None and isinstance(returns_series, pd.Series) and not returns_series.empty else 0.0
        
        # 1. Persistence of Metrics (Metric table)
        # Calculate win_rate safely to avoid division by zero
        total_closed_trades = trade_data.get('total', {}).get('closed', 0)
        total_won_trades = trade_data.get('won', {}).get('total', 0)
        win_rate = total_won_trades / total_closed_trades if total_closed_trades > 0 else 0.0
        
        metrics_record = Metric(
            backtest_id=backtest_id,
            total_return=total_return,
            sharpe=metrics.get('sharperatio', 0.0),
            max_drawdown=drawdown_data.get('max', {}).get('drawdown', 0.0), 
            win_rate=win_rate,
            avg_trade_return=trade_data.get('pnl', {}).get('average', 0.0)
        )
        db.add(metrics_record) 
        logger.debug(f"[{backtest_id}] Performance metric added to session.")

        # --- 2. Trade Persistence (Trade table) ---
        trades_list = []
        closed_trades = trade_data.get('closed', {})
        
        logger.debug(f"[{backtest_id}] Attempting to process {len(closed_trades)} closed trades.")

        for trade_num, trade_info in closed_trades.items():
            
            # Robust error handling for trade data extraction
            try:
                exit_info = trade_info['exit']
                entry_info = trade_info['entry']
                
                # Use safe lookups with defaults (or check for required keys)
                if 'dt' not in exit_info or exit_info.get('price') is None:
                    logger.warning(f"[{backtest_id}] Trade {trade_num} skipped: Incomplete exit data.")
                    continue
                
                # PnL and Commission handling
                gross_pnl = trade_info['pnl'].get('gross') or 0.0
                commission_final = trade_info['pnl'].get('commission') or 0.0
                pnl_total = float(gross_pnl) - float(commission_final)
                
                trade = Trade(
                    backtest_id=backtest_id,
                    # bt.num2date converts Backtrader's internal float date to datetime
                    date=bt.num2date(exit_info['dt']), 
                    side='BUY' if entry_info['size'] > 0 else 'SELL',
                    price=float(exit_info['price']), 
                    size=float(abs(entry_info['size'])), # Use absolute size
                    commission=float(commission_final),
                    pnl=pnl_total
                )
                trades_list.append(trade)

            except (KeyError, TypeError, AttributeError) as e:
                logger.warning(f"[{backtest_id}] Trade {trade_num} skipped: Error processing trade data: {e}")
            except Exception as e:
                logger.error(f"[{backtest_id}] Unknown failure while processing Trade {trade_num}: {e}", exc_info=True)


        db.add_all(trades_list)
        logger.debug(f"[{backtest_id}] {len(trades_list)} Trades added to session via add_all.")


        # --- 3. Daily Position Persistence (daily_positions table) ---
        daily_positions_list = []
        # Assumes the strategy class stores daily equity data in an attribute named 'daily_position_data'
        daily_data_from_strategy = getattr(strategy_instance, 'daily_position_data', [])
        
        logger.debug(f"[{backtest_id}] Attempting to process {len(daily_data_from_strategy)} daily positions.")

        for data in daily_data_from_strategy:
            daily_positions_list.append(DailyPosition(
                backtest_id=backtest_id,
                date=data['date'], 
                position_size=data['position_size'],
                cash=data['cash'],
                equity=data['equity'], # Equity is usually calculated as cash + position_size * price
                drawdown=data['drawdown']
            ))
            
        db.add_all(daily_positions_list)
        logger.debug(f"[{backtest_id}] {len(daily_positions_list)} Daily Positions added to session.")


    # =========================================================
    # GET RESULTS (Requirement 18)
    # =========================================================
    def get_backtest_results(self, backtest_id: int, db: Session) -> Dict[str, Any]:
        """
        Fetches all results (Backtest, Metrics, Trades, Daily Positions) for a specific ID 
        and validates the status before returning data.
        """
        # 1. Load the Main Backtest Record
        backtest = db.query(Backtest).filter(Backtest.id == backtest_id).first()
        
        if not backtest:
            # Raise 404 Not Found if the record doesn't exist
            raise HTTPException(status_code=404, detail=f"Backtest ID {backtest_id} not found.")

        if backtest.status != "COMPLETED":
            # Raise 409 Conflict if results are not final
            raise HTTPException(
                status_code=409, 
                detail=f"Backtest ID {backtest_id} is still in status: {backtest.status}. Results not finalized."
            )
            
        # 2. Load Related Data (Metrics, Trades, and Positions)
        # Note: If relationships were defined with lazy='joined', a single query would suffice.
        # Here we perform explicit queries.
        metrics = db.query(Metric).filter(Metric.backtest_id == backtest_id).first()
        trades = db.query(Trade).filter(Trade.backtest_id == backtest_id).all()
        daily_positions = db.query(DailyPosition).filter(DailyPosition.backtest_id == backtest_id).all()
        
        # 3. Format results using Pydantic models for safe serialization
        # Use .model_validate() to create the Pydantic instance from the ORM object
        return {
            "backtest_id": backtest.id,
            "status": backtest.status,
            "ticker": backtest.ticker,
            "metrics": MetricSchema.model_validate(metrics).model_dump() if metrics else {},
            "trades": [TradeSchema.model_validate(t).model_dump() for t in trades],
            "daily_positions": [DailyPositionSchema.model_validate(d).model_dump() for d in daily_positions],
        }

    # =========================================================
    # LIST BACKTESTS (Requirement 19)
    # =========================================================
    def list_backtests(
        self,
        db: Session,
        ticker: Optional[str] = None,
        strategy_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        size: int = 10
    ) -> Dict[str, Any]:
        """
        Lists backtests with pagination and filtering. 
        Uses joinedload to efficiently retrieve the related Metric for total_return.
        """
        # Start query, eagerly loading the related 'metrics' to avoid N+1 queries later
        query = db.query(Backtest).options(joinedload(Backtest.metrics))

        # Apply filters conditionally
        if ticker:
            query = query.filter(Backtest.ticker == ticker)
        if strategy_type:
            query = query.filter(Backtest.strategy_type == strategy_type)
        if status:
            query = query.filter(Backtest.status == status)
        
        # Apply ordering by creation date (newest first)
        query = query.order_by(Backtest.created_at.desc())

        # Get total count before applying pagination limits
        total_count = query.count()
        
        # Apply pagination (offset and limit)
        offset = (page - 1) * size
        backtests = query.offset(offset).limit(size).all()
        
        # Format the output using the BacktestListItem schema
        items = []
        for backtest in backtests:
            # Validate the core fields against the schema
            item_data = BacktestListItem.model_validate(backtest).model_dump()
            
            # Explicitly include the total_return from the eager-loaded Metric object
            if backtest.metrics and backtest.metrics.total_return is not None:
                item_data['total_return'] = backtest.metrics.total_return
            else:
                 item_data['total_return'] = None

            # created_at is included automatically by .model_validate if it's in the schema
            
            items.append(item_data)
        
        # Return the final paginated response structure
        return {
            "total": total_count,
            "page": page,
            "size": size,
            "items": items
        }