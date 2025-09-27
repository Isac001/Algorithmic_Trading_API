# Python and Library Imports
from pydantic import BaseModel, Field, ConfigDict
from datetime import date, datetime
from typing import Optional, Dict, Any, List

# =======================================================
# 1. Backtest Run Schemas (POST /backtests/run)
# =======================================================
class BacktestRunRequest(BaseModel):
    """Schema to validate the request for initiating a new backtest simulation."""
    
    # Required Core Parameters
    ticker: str = Field(..., description="Asset symbol (e.g., PETR4.SA or AAPL).")
    start_date: date = Field(..., description="Start date (YYYY-MM-DD format).")
    end_date: date = Field(..., description="End date (YYYY-MM-DD format).")
    strategy_type: str = Field(..., description="The type of strategy to run (e.g., 'sma_cross').")
    
    # Optional/Default Parameters
    strategy_params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Dictionary of parameters specific to the strategy.")
    initial_cash: float = Field(default=100000.0, ge=1.0, description="Starting cash for the simulation.")
    commission: float = Field(default=0.001, ge=0.0, description="Commission per trade (e.g., 0.001 = 0.1%).")
    timeframe: str = Field(default="1d", description="Data frequency (e.g., '1d' for daily, '1h' for hourly).")
    
class BacktestRunResponse(BaseModel):
    """Schema for the initial response after triggering a backtest."""
    
    backtest_id: int = Field(..., description="Unique identifier for the initiated backtest.")
    status: str = Field(..., description="Current status (expected: 'PENDING').")

# =======================================================
# 2. Detailed Result Schemas (GET /backtests/{id}/results)
# =======================================================

class MetricSchema(BaseModel):
    """Consolidated performance metrics."""
    total_return: Optional[float] = None
    sharpe: Optional[float] = None
    win_rate: Optional[float] = None
    avg_trade_return: Optional[float] = None
    
    # Configuration to allow mapping from SQLAlchemy models
    model_config = ConfigDict(from_attributes=True) 

class TradeSchema(BaseModel):
    """Represents a single closed trade executed during the backtest."""
    date: datetime = Field(..., description="Date and time the trade was closed.")
    side: str = Field(..., description="Operation side (e.g., 'BUY' or 'SELL').")
    price: float
    size: float = Field(..., description="Amount of asset traded.")
    commission: float
    pnl: float = Field(..., description="Net Profit/Loss for this specific trade.")

    model_config = ConfigDict(from_attributes=True) 

class DailyPositionSchema(BaseModel):
    """Portfolio state at the end of a trading day (Equity Curve data)."""
    date: date
    position_size: float = Field(..., description="Current size of the asset position.")
    cash: float = Field(..., description="Available cash balance.")
    drawdown: float = Field(..., description="Maximum cumulative loss from a peak.")

    model_config = ConfigDict(from_attributes=True) 

class BacktestResultResponse(BaseModel):
    """Main response schema for detailed backtest results."""
    backtest_id: int
    status: str
    ticker: str
    metrics: MetricSchema = Field(..., description="Summary performance statistics.")
    trades: List[TradeSchema] = Field(..., description="List of all closed trades.")
    daily_positions: List[DailyPositionSchema] = Field(..., description="Data points for the equity curve and daily portfolio state.")

    model_config = ConfigDict(from_attributes=True) 

# =======================================================
# 3. Listing Schemas (GET /backtests)
# =======================================================

class BacktestListItem(BaseModel):
    """Schema for an individual item in the list of backtests."""
    id: int
    created_at: datetime
    ticker: str
    start_date: date
    end_date: date
    strategy_type: str
    status: str
    total_return: Optional[float] = Field(None, description="Final total return of the backtest, if completed.")

    model_config = ConfigDict(from_attributes=True) 

class BacktestListResponse(BaseModel):
    """Schema for the paginated response of the backtest list endpoint."""
    total: int = Field(..., description="Total number of backtests found across all pages.")
    page: int = Field(..., description="Current page number.")
    size: int = Field(..., description="Page size used.")
    items: List[BacktestListItem] = Field(..., description="List of backtest summary items for the current page.")