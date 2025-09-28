# Python and Library Imports
import backtrader as bt
from datetime import datetime, date, timezone
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
import logging
from typing import Dict, Any, List, Optional
import json
from fastapi import HTTPException

# Project imports
from trading_api.database.models.market_data import Price, Symbol
from trading_api.database.models.backtest import Backtest, Trade, DailyPosition, Metric
from trading_api.strategies.sma_cross import SMACross
from trading_api.database.session import SessionLocal
from trading_api.modules.backtests.schemas import (
    MetricSchema, TradeSchema, DailyPositionSchema, BacktestListItem
)

# Basic logging configuration
logger = logging.getLogger(__name__)

# Mapping between strategy names and their corresponding Backtrader classes
STRATEGY_MAPPING = {
    "sma_cross": SMACross,
}

# Backtesting Service
class BacktestingService:

    """
    Service class responsible for managing backtest execution, data persistence, and results retrieval.
    Handles the complete lifecycle of backtesting operations from creation to results analysis.
    """

    # Constructor
    def __init__(self, db: Session):

        """
        Initialize the backtesting service with database session.
        
        Args:
            db: SQLAlchemy database session for data operations
        """

        self.db = db

    # Method to create initial backtest record
    def create_pending_backtest(self, backtest_params: Dict[str, Any]) -> int:

        """
        Create initial backtest record in database with PENDING status.
        This synchronous method ensures immediate return of backtest ID for API response.
        
        Args:
            backtest_params: Dictionary containing backtest configuration parameters
            
        Returns:
            int: Unique identifier of the created backtest record
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

    # Method to execute backtest in a background task
    def execute_backtest_job_safe(self, backtest_id: int):

        """
        Safe execution wrapper for background task processing.
        Creates isolated database session and ensures proper error handling and resource cleanup.
        
        Args:
            backtest_id: Identifier of the backtest to execute
        """

        logger.info(f"[{backtest_id}] Starting safe backtest execution")
        db_job = SessionLocal()
        try:
            self.execute_backtest_job(backtest_id, db_job)
        except Exception as e:
            logger.error(f"[{backtest_id}] Critical error in backtest: {e}", exc_info=True)
            db_job.rollback()
        finally:
            db_job.close()

    # Method to execute backtest job
    def execute_backtest_job(self, backtest_id: int, db: Session):

        """
        Core backtest execution logic using Backtrader framework.
        Manages complete backtest lifecycle from data loading to results persistence.
        
        Args:
            backtest_id: Identifier of the backtest to execute
            db: Database session for the background job
        """

        backtest_record = None
        
        try:
            logger.info(f"[{backtest_id}] Starting backtest execution")
            
            # Retrieve backtest configuration from database
            backtest_record = db.query(Backtest).filter(Backtest.id == backtest_id).first()
            if not backtest_record:
                logger.error(f"[{backtest_id}] Backtest record not found")
                return

            # Update backtest status to indicate active execution
            backtest_record.status = "RUNNING"
            db.commit()
            logger.debug(f"[{backtest_id}] Status updated to RUNNING")

            # Prepare parameters for data retrieval
            backtest_params = {
                "ticker": backtest_record.ticker,
                "start_date": backtest_record.start_date,
                "end_date": backtest_record.end_date,
            }
            
            # Load historical price data for backtesting
            data_feed = self._get_data_from_db(backtest_params, db)
            
            # Configure Backtrader cerebro engine with optimized settings
            cerebro = bt.Cerebro()
            cerebro.adddata(data_feed)
            cerebro.broker.setcash(backtest_record.initial_cash)
            cerebro.broker.setcommission(commission=backtest_record.commission)
            
            # Add trading strategy with specified parameters
            StrategyClass = STRATEGY_MAPPING[backtest_record.strategy_type]
            cerebro.addstrategy(StrategyClass, **backtest_record.strategy_params_json)
            
            # Add comprehensive performance analyzers for detailed metrics
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')
            cerebro.addanalyzer(bt.analyzers.Transactions, _name='transactions')
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
            cerebro.addanalyzer(bt.analyzers.Returns, _name='returns', timeframe=bt.TimeFrame.Days)
            cerebro.addanalyzer(bt.analyzers.VWR, _name='vwr')
            cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')

            # Execute backtest with realistic trading simulation settings
            logger.info(f"[{backtest_id}] Executing Backtrader...")
            results = cerebro.run(
                runonce=False,      # Sequential processing for realistic trade execution
                tradehistory=True,  # Enable detailed trade history tracking
                exactbars=False     # Optimize memory usage for larger datasets
            )
            
            strategy_instance = results[0]
            logger.info(f"[{backtest_id}] Backtrader execution completed")

            # Persist all backtest results to database
            self._save_comprehensive_results(strategy_instance, backtest_record.id, db, cerebro)
            
            # Mark backtest as successfully completed
            backtest_record.status = "COMPLETED"
            db.commit()
            logger.info(f"[{backtest_id}] Backtest COMPLETED successfully")

        except Exception as e:
            logger.error(f"[{backtest_id}] Backtest FAILED: {e}", exc_info=True)
            db.rollback()
            
            # Update backtest status to failed with error message
            if backtest_record:
                try:
                    backtest_record.status = "FAILED"
                    backtest_record.error_message = str(e)[:500]
                    db.commit()
                except Exception as save_err:
                    logger.error(f"[{backtest_id}] Failed to save error status: {save_err}")
            
            raise e
        
    # Method to retrieve historical price data from database
    def _get_data_from_db(self, backtest_params: Dict[str, Any], db: Session):

        """
        Retrieve historical price data from database for backtesting period.
        Validates data availability and prepares it for Backtrader consumption.
        
        Args:
            backtest_params: Dictionary containing ticker and date range parameters
            db: Database session for data retrieval
            
        Returns:
            bt.feeds.PandasData: Backtrader data feed object
            
        Raises:
            ValueError: If ticker not found or no data available for specified period
        """

        ticker = backtest_params["ticker"]
        
        # Verify ticker exists in database
        symbol_record = db.query(Symbol).filter(Symbol.ticker == ticker).first()
        if not symbol_record:
            raise ValueError(f"Ticker '{ticker}' not found")
        
        # Query price data for specified date range
        query = db.query(Price).filter(
            Price.symbol_id == symbol_record.id,
            Price.date >= backtest_params["start_date"],
            Price.date <= backtest_params["end_date"]
        ).order_by(Price.date)
        
        # Load data into pandas DataFrame for processing
        df = pd.read_sql(query.statement, db.bind)
        
        if df.empty:
            raise ValueError(f"No price data for {ticker} in specified period")
        
        # Prepare DataFrame for Backtrader compatibility
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.sort_index(inplace=True)
        
        return bt.feeds.PandasData(dataname=df)

    # Method to save comprehensive backtest results to database
    def _save_comprehensive_results(self, strategy_instance, backtest_id: int, db: Session, cerebro=None):

        """
        Extract and persist all backtest results including metrics, trades, and positions.
        Implements multi-layered data validation and error handling.
        
        Args:
            strategy_instance: Backtrader strategy instance with execution results
            backtest_id: Identifier for linking results to backtest record
            db: Database session for persistence operations
        """

        try:
            logger.info(f"[{backtest_id}] Starting comprehensive results persistence")
            
            # Extract performance metrics from Backtrader analyzers
            sharpe_analyzer = strategy_instance.analyzers.sharpe.get_analysis()
            trade_analyzer = strategy_instance.analyzers.trade_analyzer.get_analysis()
            drawdown_analyzer = strategy_instance.analyzers.drawdown.get_analysis()
            returns_analyzer = strategy_instance.analyzers.returns.get_analysis()
            
            # Calculate key performance indicators
            initial_cash = strategy_instance.broker.startingcash
            final_value = strategy_instance.broker.getvalue()
            total_return = (final_value - initial_cash) / initial_cash if initial_cash > 0 else 0.0
            
            # Compute trade statistics for performance analysis
            total_trades = trade_analyzer.get('total', {}).get('total', 0)
            won_trades = trade_analyzer.get('won', {}).get('total', 0)
            win_rate = won_trades / total_trades if total_trades > 0 else 0.0
            
            # Persist performance metrics to database
            metrics_record = Metric(
                backtest_id=backtest_id,
                total_return=float(total_return),
                sharpe=float(sharpe_analyzer.get('sharperatio', 0.0)),
                max_drawdown=float(abs(drawdown_analyzer.get('max', {}).get('drawdown', 0.0))),
                win_rate=float(win_rate),
                avg_trade_return=float(trade_analyzer.get('pnl', {}).get('net', {}).get('average', 0.0))
            )
            db.add(metrics_record)
            logger.debug(f"[{backtest_id}] Metrics saved")

            # Persist individual trades using multiple capture methods
            trades_saved = self._save_trades_comprehensive(strategy_instance, backtest_id, db, trade_analyzer)
            logger.info(f"[{backtest_id}] Saved {trades_saved} trades")

            # Persist daily portfolio snapshots for equity curve analysis
            positions_saved = self._save_daily_positions(strategy_instance, backtest_id, db)
            logger.info(f"[{backtest_id}] Saved {positions_saved} daily positions")

        except Exception as e:
            logger.error(f"[{backtest_id}] Error in results persistence: {e}", exc_info=True)
            raise

    # Method to save trades using multiple capture methods
    def _save_trades_comprehensive(self, strategy_instance, backtest_id: int, db: Session, trade_analyzer) -> int:

        """
        Persist trade records using multiple data capture methods for reliability.
        Implements fallback mechanisms to ensure no trades are lost.
        
        Args:
            strategy_instance: Strategy instance containing trade data
            backtest_id: Identifier for trade-backtest relationship
            db: Database session for persistence
            trade_analyzer: Backtrader trade analyzer results
            
        Returns:
            int: Number of trades successfully persisted
        """

        trades_to_save = []
        
        # Primary method: Use strategy's internal trade tracking (most reliable)
        strategy_trades = getattr(strategy_instance, 'trades_list', [])
        logger.info(f"[{backtest_id}] Found {len(strategy_trades)} trades in strategy trades_list")
        
        for trade_data in strategy_trades:
            try:
                if self._validate_trade_data(trade_data):
                    trade = Trade(
                        backtest_id=backtest_id,
                        date=trade_data.get('exit_date', datetime.now()),
                        side=trade_data.get('side', 'BUY'),
                        price=float(trade_data.get('exit_price', 0)),
                        size=float(trade_data.get('size', 0)),
                        commission=float(trade_data.get('total_commission', 0)),
                        pnl=float(trade_data.get('pnl_net', 0))
                    )
                    trades_to_save.append(trade)
            except Exception as e:
                logger.warning(f"[{backtest_id}] Invalid trade in strategy_list: {e}")

        # Fallback method: Extract trades from Backtrader's TradeAnalyzer
        if not trades_to_save:
            logger.info(f"[{backtest_id}] Using TradeAnalyzer fallback")
            trades_to_save.extend(self._extract_trades_from_analyzer(trade_analyzer, backtest_id))

        # Last resort: Attempt trade reconstruction from transaction records
        if not trades_to_save:
            logger.info(f"[{backtest_id}] Attempting transaction reconstruction")
            transactions_analyzer = getattr(strategy_instance.analyzers, 'transactions', None)
            if transactions_analyzer:
                transactions_data = transactions_analyzer.get_analysis()
                trades_to_save.extend(self._reconstruct_trades_from_transactions(transactions_data, backtest_id))

        # Bulk persist valid trades to database
        if trades_to_save:
            db.add_all(trades_to_save)
            logger.info(f"[{backtest_id}] Successfully saved {len(trades_to_save)} trades to database")
            return len(trades_to_save)
        else:
            logger.warning(f"[{backtest_id}] No valid trades found to persist")
            return 0

    # Method to validate trade data before persistence
    def _validate_trade_data(self, trade_data: Dict) -> bool:

        """
        Validate trade data integrity before database persistence.
        Ensures all required fields are present and contain valid values.
        
        Args:
            trade_data: Dictionary containing trade information
            
        Returns:
            bool: True if trade data passes all validation checks
        """

        required_fields = ['exit_date', 'exit_price', 'size', 'side']
        
        # Check presence of all required fields
        for field in required_fields:
            if field not in trade_data or trade_data[field] is None:
                return False
        
        # Validate numerical values for logical consistency
        if trade_data['size'] <= 0:
            return False
            
        if trade_data['exit_price'] <= 0:
            return False
            
        return True

    # Method to extract trades from Backtrader's TradeAnalyzer
    def _extract_trades_from_analyzer(self, trade_analyzer, backtest_id: int) -> List[Trade]:

        """
        Extract trade records from Backtrader's TradeAnalyzer results.
        Handles different data structure formats returned by the analyzer.
        
        Args:
            trade_analyzer: Backtrader trade analyzer output
            backtest_id: Identifier for trade association
            
        Returns:
            List[Trade]: List of validated trade objects for persistence
        """

        trades = []
        
        try:
            closed_trades = trade_analyzer.get('closed', [])
            if not closed_trades:
                closed_trades = trade_analyzer  # Handle non-nested analyzer format
                
            for trade_info in closed_trades:
                try:
                    if isinstance(trade_info, dict):
                        entry = trade_info.get('entry', {})
                        exit_info = trade_info.get('exit', {})
                        
                        if exit_info and entry:
                            trade = Trade(
                                backtest_id=backtest_id,
                                date=bt.num2date(exit_info.get('dt', 0)),
                                side='BUY' if entry.get('size', 0) > 0 else 'SELL',
                                price=float(exit_info.get('price', 0)),
                                size=float(abs(entry.get('size', 0))),
                                commission=float(trade_info.get('pnl', {}).get('commission', 0)),
                                pnl=float(trade_info.get('pnl', {}).get('net', 0))
                            )
                            trades.append(trade)
                except Exception as e:
                    continue
                    
        except Exception as e:
            logger.warning(f"Error extracting trades from analyzer: {e}")
            
        return trades

    # Method to reconstruct trades from transaction history
    def _reconstruct_trades_from_transactions(self, transactions_data, backtest_id: int) -> List[Trade]:

        """
        Reconstruct trade records from transaction history (complex fallback).
        Placeholder for advanced trade reconstruction logic if needed.
        
        Args:
            transactions_data: Backtrader transactions analyzer output
            backtest_id: Identifier for trade association
            
        Returns:
            List[Trade]: Empty list - method requires implementation
        """

        trades = []
        return trades

    # Method to persist daily portfolio position snapshots
    def _save_daily_positions(self, strategy_instance, backtest_id: int, db: Session) -> int:

        """
        Persist daily portfolio position snapshots for equity curve analysis.
        Captures portfolio composition and value for each trading day.
        
        Args:
            strategy_instance: Strategy instance containing position data
            backtest_id: Identifier for position-backtest relationship
            db: Database session for persistence
            
        Returns:
            int: Number of daily positions successfully persisted
        """

        positions_to_save = []
        
        daily_data = getattr(strategy_instance, 'daily_position_data', [])
        logger.info(f"[{backtest_id}] Processing {len(daily_data)} daily positions")
        
        for data in daily_data:
            try:
                position = DailyPosition(
                    backtest_id=backtest_id,
                    date=data['date'],
                    position_size=float(data.get('position_size', 0)),
                    cash=float(data.get('cash', 0)),
                    equity=float(data.get('equity', 0)),
                    drawdown=float(data.get('drawdown', 0))
                )
                positions_to_save.append(position)
            except Exception as e:
                logger.warning(f"[{backtest_id}] Invalid daily position: {e}")
        
        if positions_to_save:
            db.add_all(positions_to_save)
            return len(positions_to_save)
        return 0

    # Method to retrieve comprehensive backtest results
    def get_backtest_results(self, backtest_id: int, db: Session) -> Dict[str, Any]:

        """
        Retrieve comprehensive results for a completed backtest.
        Validates backtest status and aggregates all related data.
        
        Args:
            backtest_id: Identifier of the backtest to retrieve
            db: Database session for data retrieval
            
        Returns:
            Dict[str, Any]: Structured results including metrics, trades, and positions
            
        Raises:
            HTTPException: If backtest not found, failed, or not completed
        """

        backtest = db.query(Backtest).filter(Backtest.id == backtest_id).first()
        
        if not backtest:
            raise HTTPException(status_code=404, detail=f"Backtest ID {backtest_id} not found.")

        if backtest.status == "FAILED":
            error_detail = backtest.error_message or "Unknown error"
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Backtest ID {backtest_id} failed.",
                    "error": error_detail
                }
            )
        
        if backtest.status != "COMPLETED":
            raise HTTPException(
                status_code=409, 
                detail=f"Backtest ID {backtest_id} status: {backtest.status}. Results not ready."
            )
            
        # Aggregate all related data for comprehensive results
        metrics = db.query(Metric).filter(Metric.backtest_id == backtest_id).first()
        trades = db.query(Trade).filter(Trade.backtest_id == backtest_id).all()
        daily_positions = db.query(DailyPosition).filter(DailyPosition.backtest_id == backtest_id).all()
        
        return {
            "backtest_id": backtest.id,
            "status": backtest.status,
            "ticker": backtest.ticker,
            "metrics": MetricSchema.model_validate(metrics).model_dump() if metrics else {},
            "trades": [TradeSchema.model_validate(t).model_dump() for t in trades],
            "daily_positions": [DailyPositionSchema.model_validate(d).model_dump() for d in daily_positions],
        }

    # Method to retrieve paginated list of backtests
    def list_backtests(self, db: Session, ticker: Optional[str] = None, 
                      strategy_type: Optional[str] = None, status: Optional[str] = None,
                      page: int = 1, size: int = 10) -> Dict[str, Any]:
        
        """
        Retrieve paginated list of backtests with filtering options.
        Includes performance metrics for each backtest in results.
        
        Args:
            db: Database session for query execution
            ticker: Filter by stock ticker symbol
            strategy_type: Filter by trading strategy type
            status: Filter by backtest execution status
            page: Page number for pagination (1-based)
            size: Number of items per page
            
        Returns:
            Dict[str, Any]: Paginated response with backtest list and metadata
        """

        query = db.query(Backtest).options(joinedload(Backtest.metrics))

        # Apply optional filters for targeted results
        if ticker:
            query = query.filter(Backtest.ticker == ticker)
        if strategy_type:
            query = query.filter(Backtest.strategy_type == strategy_type)
        if status:
            query = query.filter(Backtest.status == status)
        
        # Order by creation date (newest first) for logical presentation
        query = query.order_by(Backtest.created_at.desc())

        # Calculate pagination metadata
        total_count = query.count()
        offset = (page - 1) * size
        backtests = query.offset(offset).limit(size).all()
        
        # Format response data with performance metrics
        items = []
        for backtest in backtests:
            item_data = BacktestListItem.model_validate(backtest).model_dump()
            
            # Include error details for failed backtests
            if backtest.status == "FAILED" and backtest.error_message:
                item_data['error_message'] = backtest.error_message
            
            # Include performance metric for completed backtests
            if backtest.metrics and backtest.metrics.total_return is not None:
                item_data['total_return'] = backtest.metrics.total_return
            else:
                item_data['total_return'] = None

            items.append(item_data)
        
        return {
            "total": total_count,
            "page": page,
            "size": size,
            "items": items
        }