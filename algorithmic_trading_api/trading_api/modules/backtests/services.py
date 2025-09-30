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
from trading_api.strategies.breakout import BreakoutStrategy
from trading_api.database.session import SessionLocal
from trading_api.modules.backtests.schemas import (
    MetricSchema, TradeSchema, DailyPositionSchema, BacktestListItem
)

# Basic logging configuration
logger = logging.getLogger(__name__)

# Mapping between strategy names and their corresponding Backtrader classes
STRATEGY_MAPPING = {
    "sma_cross": SMACross,
    "breakout": BreakoutStrategy,
}

# Backtesting Service
class BacktestingService:

    def __init__(self, db: Session):
        """
        Initialize the backtesting service with database session.
        
        Args:
            db: SQLAlchemy database session for data operations
        """
        self.db = db

    def create_pending_backtest(self, backtest_params: Dict[str, Any]) -> int:
        """
        Create initial backtest record in database with PENDING status.
        
        Args:
            backtest_params: Dictionary containing backtest configuration parameters
            
        Returns:
            int: Unique identifier of the created backtest record
        """
        # Create new backtest record with PENDING status
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
        # Persist record to database and return ID
        self.db.add(backtest_record)
        self.db.commit()
        self.db.refresh(backtest_record)
        return backtest_record.id

    def execute_backtest_job_safe(self, backtest_id: int):
        """
        Safe execution wrapper for background task processing.
        Creates isolated database session and ensures proper error handling.
        
        Args:
            backtest_id: Identifier of the backtest to execute
        """
        logger.info(f"[{backtest_id}] Starting safe backtest execution")
        # Create isolated database session for background job
        db_job = SessionLocal()
        try:
            self.execute_backtest_job(backtest_id, db_job)
        except Exception as e:
            logger.error(f"[{backtest_id}] Critical error in backtest: {e}", exc_info=True)
            db_job.rollback()
        finally:
            # Always close database connection
            db_job.close()

    def execute_backtest_job(self, backtest_id: int, db: Session):
        """
        Core backtest execution logic using Backtrader framework.
        
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
            
            # Configure Backtrader cerebro engine
            cerebro = bt.Cerebro()
            cerebro.adddata(data_feed)
            cerebro.broker.setcash(backtest_record.initial_cash)
            cerebro.broker.setcommission(commission=backtest_record.commission)
            
            # Add trading strategy with specified parameters
            StrategyClass = STRATEGY_MAPPING[backtest_record.strategy_type]
            cerebro.addstrategy(StrategyClass, **backtest_record.strategy_params_json)
            
            # Add comprehensive performance analyzers
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')
            cerebro.addanalyzer(bt.analyzers.Transactions, _name='transactions')
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
            cerebro.addanalyzer(bt.analyzers.Returns, _name='returns', timeframe=bt.TimeFrame.Days)
            cerebro.addanalyzer(bt.analyzers.VWR, _name='vwr')
            cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')

            # Execute backtest with trading simulation settings
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

        except ValueError as e:
            # CORREÇÃO: Tratamento específico para "Ticker not found"
            error_message = str(e)
            if "Ticker" in error_message and "not found" in error_message:
                logger.error(f"[{backtest_id}] Ticker not found error: {error_message}")
                db.rollback()
                
                # Update backtest status to failed with specific error message
                if backtest_record:
                    try:
                        backtest_record.status = "FAILED"
                        # Armazena a mensagem de erro específica
                        backtest_record.error_message = f"Ticker '{backtest_record.ticker}' not found in database"
                        db.commit()
                    except Exception as save_err:
                        logger.error(f"[{backtest_id}] Failed to save error status: {save_err}")
                
                # Não relança a exceção para evitar logs duplicados
                return
            else:
                # Para outros ValueErrors, mantém o comportamento original
                logger.error(f"[{backtest_id}] Backtest FAILED: {error_message}", exc_info=True)
                db.rollback()
                
                if backtest_record:
                    try:
                        backtest_record.status = "FAILED"
                        backtest_record.error_message = error_message
                        db.commit()
                    except Exception as save_err:
                        logger.error(f"[{backtest_id}] Failed to save error status: {save_err}")
                
                raise e

        except Exception as e:
            logger.error(f"[{backtest_id}] Backtest FAILED: {e}", exc_info=True)
            db.rollback()
            
            # Update backtest status to failed without error_message field
            if backtest_record:
                try:
                    backtest_record.status = "FAILED"
                    backtest_record.error_message = str(e)
                    db.commit()
                except Exception as save_err:
                    logger.error(f"[{backtest_id}] Failed to save error status: {save_err}")
            
            raise e

    def _get_data_from_db(self, backtest_params: Dict[str, Any], db: Session):
        """
        Retrieve historical price data from database for backtesting period.
        
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

    def _save_comprehensive_results(self, strategy_instance, backtest_id: int, db: Session, cerebro=None):
        """
        Extract and persist all backtest results including metrics, trades, and positions.
        
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

    def _validate_trade_data(self, trade_data: Dict) -> bool:
        """
        Validate trade data with support for both entry and exit formats.
        
        Args:
            trade_data: Dictionary containing trade information
            
        Returns:
            bool: True if trade data passes all validation checks
        """
        # Check basic required fields
        required_fields = ['size', 'side']
        for field in required_fields:
            if field not in trade_data or trade_data[field] is None:
                return False
        
        # Validate numerical values for logical consistency
        if trade_data['size'] <= 0:
            return False
        
        # For closed trades, we need exit information
        if trade_data.get('status') == 'CLOSED':
            if 'exit_date' not in trade_data or 'exit_price' not in trade_data:
                return False
            if trade_data['exit_price'] <= 0:
                return False
        # For open trades, we need entry information  
        elif trade_data.get('status') == 'OPEN':
            if 'entry_date' not in trade_data or 'entry_price' not in trade_data:
                return False
            if trade_data['entry_price'] <= 0:
                return False
        
        return True

    def _save_trades_comprehensive(self, strategy_instance, backtest_id: int, db: Session, trade_analyzer) -> int:
        """
        Persist trade records with improved validation and error handling.
        
        Returns:
            int: Number of trades successfully saved
        """
        trades_to_save = []
        
        # Primary method: Use strategy's internal trade tracking
        strategy_trades = getattr(strategy_instance, 'trades_list', [])
        logger.info(f"[{backtest_id}] Found {len(strategy_trades)} trades in strategy trades_list")
        
        # Debug logging for troubleshooting
        logger.info(f"[{backtest_id}] DEBUG - Trades list sample: {strategy_trades[:2] if strategy_trades else 'Empty'}")
        
        # Process each trade from strategy tracking
        for trade_data in strategy_trades:
            try:
                if self._validate_trade_data(trade_data):
                    # Use exit_date for closed trades, entry_date for open trades
                    trade_date = trade_data.get('exit_date') or trade_data.get('entry_date')
                    
                    # For closed trades, use exit price; for open trades, use entry price
                    if trade_data.get('status') == 'CLOSED':
                        price = trade_data.get('exit_price')
                        pnl = trade_data.get('pnl_net', 0)
                    else:
                        price = trade_data.get('entry_price') 
                        pnl = 0.0
                    
                    # Create trade record for database
                    trade = Trade(
                        backtest_id=backtest_id,
                        date=trade_date,
                        side=trade_data.get('side', 'BUY'),
                        price=float(price),
                        size=float(trade_data.get('size', 0)),
                        commission=float(trade_data.get('total_commission', 0)),
                        pnl=float(pnl)
                    )
                    trades_to_save.append(trade)
                    logger.info(f"[{backtest_id}] Valid trade added: {trade_data.get('trade_id', 'unknown')}")
            except Exception as e:
                logger.warning(f"[{backtest_id}] Invalid trade in strategy_list: {e} - Data: {trade_data}")

        # Fallback method: Extract trades from Backtrader's TradeAnalyzer
        if not trades_to_save:
            logger.info(f"[{backtest_id}] Using TradeAnalyzer fallback")
            analyzer_trades = self._extract_trades_from_analyzer(trade_analyzer, backtest_id)
            trades_to_save.extend(analyzer_trades)
            logger.info(f"[{backtest_id}] TradeAnalyzer found {len(analyzer_trades)} trades")

        # Bulk persist valid trades to database
        if trades_to_save:
            db.add_all(trades_to_save)
            db.flush()  # Ensure trades are persisted
            logger.info(f"[{backtest_id}] Successfully saved {len(trades_to_save)} trades to database")
            return len(trades_to_save)
        else:
            logger.warning(f"[{backtest_id}] No valid trades found to persist")
            return 0

    def _extract_trades_from_analyzer(self, trade_analyzer, backtest_id: int) -> List[Trade]:
        """
        Extract trade records from Backtrader's TradeAnalyzer results.
        
        Args:
            trade_analyzer: Backtrader trade analyzer output
            backtest_id: Identifier for trade association
            
        Returns:
            List[Trade]: List of validated trade objects for persistence
        """
        trades = []
        
        try:
            # Handle different analyzer data structures
            closed_trades = trade_analyzer.get('closed', [])
            if not closed_trades:
                closed_trades = trade_analyzer  # Handle non-nested analyzer format
                
            # Process each trade from analyzer
            for trade_info in closed_trades:
                try:
                    if isinstance(trade_info, dict):
                        entry = trade_info.get('entry', {})
                        exit_info = trade_info.get('exit', {})
                        
                        # Only process trades with complete entry and exit data
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
                    # Skip invalid trade entries
                    continue
                    
        except Exception as e:
            logger.warning(f"Error extracting trades from analyzer: {e}")
            
        return trades

    def _reconstruct_trades_from_transactions(self, transactions_data, backtest_id: int) -> List[Trade]:
        """
        Reconstruct trade records from transaction history (complex fallback).
        
        Args:
            transactions_data: Backtrader transactions analyzer output
            backtest_id: Identifier for trade association
            
        Returns:
            List[Trade]: Empty list - method requires implementation
        """
        trades = []
        return trades

    def _save_daily_positions(self, strategy_instance, backtest_id: int, db: Session) -> int:
        """
        Persist daily portfolio position snapshots for equity curve analysis.
        
        Args:
            strategy_instance: Strategy instance containing position data
            backtest_id: Identifier for position-backtest relationship
            db: Database session for persistence
            
        Returns:
            int: Number of daily positions successfully persisted
        """
        positions_to_save = []
        
        # Get daily position data from strategy
        daily_data = getattr(strategy_instance, 'daily_position_data', [])
        logger.info(f"[{backtest_id}] Processing {len(daily_data)} daily positions")
        
        # Process each daily position snapshot
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
        
        # Bulk persist positions to database
        if positions_to_save:
            db.add_all(positions_to_save)
            return len(positions_to_save)
        return 0

    def get_backtest_results(self, backtest_id: int, db: Session) -> Dict[str, Any]:
        """
        Retrieve comprehensive results for a completed backtest.
        
        Args:
            backtest_id: Identifier of the backtest to retrieve
            db: Database session for data retrieval
            
        Returns:
            Dict[str, Any]: Structured results including metrics, trades, and positions
            
        Raises:
            HTTPException: If backtest not found, failed, or not completed
        """
        # Retrieve backtest record from database
        backtest = db.query(Backtest).filter(Backtest.id == backtest_id).first()
        
        if not backtest:
            raise HTTPException(status_code=404, detail=f"Backtest ID {backtest_id} not found.")

        # Handle failed backtests with safe error message access
        if backtest.status == "FAILED":
            # Use getattr to safely access error_message field if it exists
            error_detail = getattr(backtest, 'error_message', None) or "Error during backtest execution"
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Backtest ID {backtest_id} failed.",
                    "error": error_detail
                }
            )
        
        # Check if backtest is ready for results retrieval
        if backtest.status != "COMPLETED":
            raise HTTPException(
                status_code=409, 
                detail=f"Backtest ID {backtest_id} status: {backtest.status}. Results not ready."
            )
            
        # Aggregate all related data for comprehensive results
        metrics = db.query(Metric).filter(Metric.backtest_id == backtest_id).first()
        trades = db.query(Trade).filter(Trade.backtest_id == backtest_id).all()
        daily_positions = db.query(DailyPosition).filter(DailyPosition.backtest_id == backtest_id).all()
        
        # Return structured results
        return {
            "backtest_id": backtest.id,
            "status": backtest.status,
            "ticker": backtest.ticker,
            "metrics": MetricSchema.model_validate(metrics).model_dump() if metrics else {},
            "trades": [TradeSchema.model_validate(t).model_dump() for t in trades],
            "daily_positions": [DailyPositionSchema.model_validate(d).model_dump() for d in daily_positions],
        }

    def list_backtests(self, db: Session, ticker: Optional[str] = None, 
                  strategy_type: Optional[str] = None, status: Optional[str] = None,
                  page: int = 1, size: int = 10) -> Dict[str, Any]:
        """
        Retrieve paginated list of backtests with filtering options.
        
        Args:
            db: Database session
            ticker: Filter by ticker symbol
            strategy_type: Filter by strategy type
            status: Filter by backtest status
            page: Page number for pagination
            size: Number of items per page
            
        Returns:
            Dict[str, Any]: Paginated results with metadata
        """
        # Build base query with metrics relationship
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
            
            # Safe error message access for failed backtests
            if backtest.status == "FAILED":
                error_msg = getattr(backtest, 'error_message', None)
                if error_msg:
                    item_data['error_message'] = error_msg
            
            # Include performance metric for completed backtests
            if backtest.metrics and backtest.metrics.total_return is not None:
                item_data['total_return'] = backtest.metrics.total_return
            else:
                item_data['total_return'] = None

            items.append(item_data)
        
        # Return paginated response
        return {
            "total": total_count,
            "page": page,
            "size": size,
            "items": items
        }