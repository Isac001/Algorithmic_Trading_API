# Python and Library Imports
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

# Backtest Table
class Backtest(Base):

    """Represents a single backtest execution and its parameters."""

    __tablename__ = 'backtests'

    # Columns
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ticker = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    strategy_type = Column(String, nullable=False)
    strategy_params_json = Column(JSON)
    initial_cash = Column(Float, nullable=False)
    commission = Column(Float, nullable=False)
    status = Column(String, default='PENDING') 

    # Relationships
    trades = relationship("Trade", back_populates="backtest")
    daily_positions = relationship("DailyPosition", back_populates="backtest")
    metrics = relationship("Metric", uselist=False, back_populates="backtest")  

# Trade Table
class Trade(Base):

    """Represents a single trade (buy or sell) executed during a backtest."""

    __tablename__ = 'trades'

    # Columns
    id = Column(Integer, primary_key=True, index=True)
    backtest_id = Column(Integer, ForeignKey('backtests.id'), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    side = Column(String, nullable=False)  
    price = Column(Float, nullable=False)
    size = Column(Float, nullable=False)
    commission = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False) 

    # Relationship
    backtest = relationship("Backtest", back_populates="trades")

# Daily Position Table
class DailyPosition(Base):

    """Represents the state of the portfolio at the end of a single day during a backtest."""

    __tablename__ = 'daily_positions'

    # Columns
    id = Column(Integer, primary_key=True, index=True)
    backtest_id = Column(Integer, ForeignKey('backtests.id'), nullable=False)
    date = Column(Date, nullable=False)
    position_size = Column(Float)
    cash = Column(Float)
    equity = Column(Float)
    drawdown = Column(Float)

    # Relationship
    backtest = relationship("Backtest", back_populates="daily_positions")

# Metric Table
class Metric(Base):

    """Represents the consolidated performance metrics for a completed backtest."""

    __tablename__ = 'metrics'

    # Columns
    id = Column(Integer, primary_key=True, index=True)
    backtest_id = Column(Integer, ForeignKey('backtests.id'), unique=True, nullable=False)
    total_return = Column(Float)
    sharpe = Column(Float)
    max_drawdown = Column(Float)
    win_rate = Column(Float)
    avg_trade_return = Column(Float)

    # Relationship
    backtest = relationship("Backtest", back_populates="metrics")