# Python and Library Imports
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


# Symbol Table
class Symbol(Base):

    """Represents a financial asset (e.g., a stock ticker)."""

    __tablename__ = 'symbols'

    # Columns
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    exchange = Column(String)
    currency = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    prices = relationship("Price", back_populates="symbol")
    indicators = relationship("Indicator", back_populates="symbol")

# Price Table
class Price(Base):

    """Represents the historical OHLCV data for a symbol on a specific date."""

    __tablename__ = 'prices'

    # Columns
    id = Column(Integer, primary_key=True, index=True)
    symbol_id = Column(Integer, ForeignKey('symbols.id'), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)

    # Relationship
    symbol = relationship("Symbol", back_populates="prices")

    # Ensures a unique price entry per symbol per day.
    __table_args__ = (UniqueConstraint('symbol_id', 'date', name='_symbol_date_uc'),)

# Indicator Table
class Indicator(Base):

    """Represents a calculated technical indicator value for a symbol on a specific date."""

    __tablename__ = 'indicators'

    # Columns
    id = Column(Integer, primary_key=True, index=True)
    symbol_id = Column(Integer, ForeignKey('symbols.id'), nullable=False)
    date = Column(Date, nullable=False)
    name = Column(String, nullable=False)  # E.g., 'SMA', 'EMA', 'RSI'
    value = Column(Float, nullable=False)
    params_hash = Column(String, nullable=False)  # A hash of the indicator's parameters (e.g., window size).

    # Relationship
    symbol = relationship("Symbol", back_populates="indicators")
    
    # Ensures a unique indicator value per symbol, date, name, and parameter hash.
    __table_args__ = (UniqueConstraint('symbol_id', 'date', 'name', 'params_hash', name='_indicator_uc'),)