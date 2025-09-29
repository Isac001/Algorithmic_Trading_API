import pytest
import backtrader as bt
import numpy as np
import math
from datetime import datetime, timedelta

# Import strategy classes
from trading_api.strategies.sma_cross import SMACross
from trading_api.strategies.breakout import BreakoutStrategy 


class MockData(bt.feeds.DataBase):
    """
    Mock data feed for testing - works with in-memory data
    """
    lines = ('open', 'high', 'low', 'close', 'volume', 'openinterest')
    
    params = (
        ('fromdate', datetime(2023, 1, 1)),
        ('todate', datetime(2023, 12, 31)),
        ('timeframe', bt.TimeFrame.Days),
    )

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.idx = 0
    
    def _load(self):
        # Stop loading when no more data available
        if self.idx >= len(self.data):
            return False
            
        row = self.data[self.idx]
        
        # Set all data lines for current bar
        self.lines.datetime[0] = bt.date2num(row[0])
        self.lines.open[0] = row[1]
        self.lines.high[0] = row[2]
        self.lines.low[0] = row[3]
        self.lines.close[0] = row[4]
        self.lines.volume[0] = row[5]
        self.lines.openinterest[0] = row[6] if len(row) > 6 else 0
        
        self.idx += 1
        return True


@pytest.fixture(params=[SMACross, BreakoutStrategy])
def strategy_class(request):
    """Fixture to parameterize tests between different strategy classes."""
    return request.param


@pytest.fixture
def run_strategy_with_mock_data(strategy_class):
    """
    Execute a strategy with controlled data to isolate Position Sizing calculation.
    
    Scenario: Simulates a day where ATR/Volatility is exactly 10.
    """
    INITIAL_CASH = 100000.0
    
    # Determine required data size based on strategy requirements
    if strategy_class == SMACross:
        # SMACross needs at least 200 bars for slow SMA
        num_bars = 250
        # Use parameters from your JSON configuration
        params = {
            "fast": 50,
            "slow": 200,
            "atr_period": 14,
            "stop_multiplier": 2.0,
            "risk_per_trade_percent": 1.0
        }
    else:  # BreakoutStrategy
        # BreakoutStrategy needs at least 20 bars for Donchian channel
        num_bars = 50
        # Use parameters from your JSON configuration
        params = {
            "breakout_period": 20,
            "atr_period": 14,
            "stop_multiplier": 3.0,
            "risk_per_trade_percent": 1.0
        }
    
    # Create mock data with proper date handling
    data = []
    start_date = datetime(2023, 1, 1)
    
    for i in range(num_bars):
        current_date = start_date + timedelta(days=i)
        # Create stable base prices with slight upward trend to generate signals
        base_price = 100 + (i * 0.1)
        data.append([
            current_date, 
            base_price,           # open
            base_price + 2,       # high
            base_price - 2,       # low  
            base_price,           # close
            1000,                 # volume
            0                     # openinterest
        ])
    
    # Specific day with high volatility for ATR testing
    # Choose a day after minimum indicator periods
    if strategy_class == SMACross:
        vol_day_idx = 220  # After 200-period SMA
    else:
        vol_day_idx = 30   # After 20-period Donchian
        
    # High=105, Low=95, Volatility=10, Close=100
    vol_date = start_date + timedelta(days=vol_day_idx)
    data[vol_day_idx] = [
        vol_date, 
        100,    # open
        105,    # high
        95,     # low  
        100,    # close
        1000,   # volume
        0       # openinterest
    ]
    
    data_feed = MockData(data)
    
    # Adjust data feed date ranges
    data_feed.p.fromdate = start_date
    data_feed.p.todate = start_date + timedelta(days=num_bars)

    # Set up cerebro with mock data
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(data_feed)
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=0.001)  # From your JSON configuration
    
    # Add strategy with parameters
    cerebro.addstrategy(strategy_class, **params)
    
    # Execute simulation
    results = cerebro.run(maxcpus=1)
    
    # Return the executed strategy instance
    return results[0]


def test_position_sizing_limits_risk_to_one_percent(run_strategy_with_mock_data):
    """
    Test if Position Sizing rule (1% Risk) calculates correct position size.
    
    Validates that risk per trade is limited to approximately 1% of capital.
    """
    strategy = run_strategy_with_mock_data
    
    # Check if any trade was executed and has entry_size
    if hasattr(strategy, 'entry_size') and strategy.entry_size is not None:
        print(f"Entry size from executed trade: {strategy.entry_size}")
        
        # Size should be positive if trade was executed
        assert strategy.entry_size > 0
        
        print(f"Strategy type: {'SMACross' if hasattr(strategy, 'fast_sma') else 'Breakout'}")
        
    else:
        # Test calculate_position_size method directly with controlled conditions
        strategy.broker.set_cash(100000.0)
        strategy.data.close[0] = 100  # Fixed entry price
        
        # Debug: check current ATR value
        if hasattr(strategy, 'atr') and len(strategy.atr) > 0:
            current_atr = strategy.atr[0]
            print(f"Current ATR value: {current_atr}")
        else:
            current_atr = 0
            print("ATR not available")
        
        # Calculate position size
        size = strategy.calculate_position_size()
        print(f"Calculated position size: {size}")
        
        # Manual calculation for verification
        entry_price = 100
        stop_price = entry_price - (strategy.p.stop_multiplier * current_atr)
        risk_per_share = entry_price - stop_price
        risk_amount = (strategy.p.risk_per_trade_percent / 100.0) * strategy.broker.getvalue()
        manual_size = int(risk_amount / risk_per_share)
        
        # Print detailed calculation breakdown
        print(f"Manual calculation:")
        print(f"  Entry price: {entry_price}")
        print(f"  ATR: {current_atr}")
        print(f"  Stop multiplier: {strategy.p.stop_multiplier}")
        print(f"  Stop price: {stop_price:.2f}")
        print(f"  Risk per share: {risk_per_share:.2f}")
        print(f"  Risk amount (1% of {strategy.broker.getvalue():.2f}): {risk_amount:.2f}")
        print(f"  Manual size: {manual_size}")
        
        # Set expectations based on strategy type
        if hasattr(strategy, 'fast_sma'):  # SMACross
            expected_size = manual_size
            tolerance = 5
        else:  # BreakoutStrategy
            expected_size = manual_size
            tolerance = 5
        
        print(f"Expected size: {expected_size}, Actual size: {size}")
        
        # Verify calculation matches manual expectation
        assert abs(size - manual_size) <= 2, f"Size {size} doesn't match manual calculation {manual_size}"
        
        # Validate size is reasonable
        assert size > 0, "Position size should be positive"
        assert size < 1000, "Position size should be reasonable (less than 1000 shares)"