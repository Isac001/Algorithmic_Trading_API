# # Python and Library Imports
import backtrader as bt
from datetime import datetime, date

class SMACross(bt.Strategy):
    """
    Moving Average Cross (SMA Cross) Strategy with Risk Management 
    (ATR Stop Loss and Position Sizing).
    
    Includes daily Equity/Cash data collection for persistence (daily_positions).
    """
    params = (
        ("fast", 50),
        ("slow", 200),
        ("atr_period", 14),             
        ("stop_multiplier", 2.0),       
        ("risk_per_trade_percent", 1.0) # Maximum 1% risk per trade (Requirement)
    )

    def __init__(self):
        # --- 1. Indicators ---
        self.fast_sma = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.slow_sma = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        
        # --- 2. Control Attributes ---
        self.buy_order = None # Tracks the pending/active BUY order
        self.stop_order = None # Tracks the pending/active SELL STOP order (Stop Loss)
        self.entry_stop_price = 0.0 # Calculated stop loss price for the current trade
        self.entry_size = 0 # Calculated size for the current trade
        
        # --- 3. Data Collection ---
        # List to store the daily portfolio state (Equity Curve/Daily Positions)
        self.daily_position_data = [] 
        
        # NOTE: Removed self.log('INIT', ...) as self.data.datetime is not ready in __init__
        print('Strategy initialized.') 

    def notify_trade(self, trade):
        """Notification method for trade status (used for logging and debug)."""
        if trade.isclosed:
            pnl_comm = trade.pnlcomm if trade.pnlcomm is not None else 0.0
            self.log('TRADE CLOSED', f'PNL: {pnl_comm:.2f}, Size: {trade.size}.')

    def next(self):
        
        # 0. Check for sufficient data (required for indicators like SMA and ATR)
        if len(self.data) < max(self.p.fast, self.p.slow, self.p.atr_period):
            return

        # 1. Daily Portfolio State Capture
        # This data is collected every bar/day to build the equity curve later
        current_date = self.data.datetime.date(0)
        daily_equity = self.broker.getvalue()
        
        self.daily_position_data.append({
            'date': current_date,
            'position_size': self.position.size if self.position else 0,
            'cash': self.broker.getcash(),
            'equity': daily_equity,
            'drawdown': 0.0 # Placeholder: actual drawdown is often calculated by an Analyzer post-run
        })
        # END OF DAILY CAPTURE

        # Prevent a new order if one is already pending/active
        if self.buy_order and self.buy_order.status < self.buy_order.Completed:
            return

        # 2. Closing/Sell Logic
        if self.position:
            # Check for a SELL signal (Fast SMA crosses below Slow SMA)
            if self.crossover < 0:
                self.log('SELL SIGNAL', f'SMA CrossDown. Closing position at {self.data.close[0]:.2f}.')
                self.close()
                # Cancel the pending Stop Loss order if it hasn't been hit/completed
                if self.stop_order and self.stop_order.status < self.stop_order.Completed:
                    self.cancel(self.stop_order)
            return

        # 3. Buy Logic (Position Opening)
        if self.crossover > 0:
            
            # --- RISK AND SIZING CALCULATION (1% Risk Requirement) ---
            entry_price = self.data.close[0]
            
            # Calculate Stop Loss price (ATR * Multiplier)
            stop_price = entry_price - (self.p.stop_multiplier * self.atr[0])
            risk_per_share = entry_price - stop_price
            
            if risk_per_share <= 0: return # Skip trade if risk is non-positive

            total_equity = self.broker.getvalue() 
            risk_per_trade_percent = self.p.risk_per_trade_percent / 100.0
            # Risk amount is 1% of total portfolio equity
            risk_amount = risk_per_trade_percent * total_equity 
            
            # Position Sizing: Size = (Risk Amount) / (Risk per Share)
            size = int(risk_amount / risk_per_share)
            
            if size == 0: return # Cannot buy a position of size zero
            
            # 4. Execute Buy Order
            self.log('ORDER', f'BUY {size} shares @ {entry_price:.2f}. Stop: {stop_price:.2f}')
            
            self.buy_order = self.buy(size=size)
            self.entry_stop_price = stop_price
            self.entry_size = size


    def notify_order(self, order):
        """Handles order status updates, primarily for placing the Stop Loss after a BUY executes."""
        
        # If the BUY order is completed, place the corresponding SELL Stop Loss
        if order.status in [order.Completed] and order.isbuy():
            # Only create the Stop Loss order if one isn't already active/pending
            if not self.stop_order or self.stop_order.status >= self.stop_order.Completed:
                self.stop_order = self.sell(
                    exectype=bt.Order.Stop, # Ensures the order executes at stop_price or lower
                    price=self.entry_stop_price, 
                    size=self.entry_size        
                )
            
        # Clear control attributes when orders are finalized (Completed, Canceled, Rejected)
        elif order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            if self.buy_order and order == self.buy_order: self.buy_order = None 
            if self.stop_order and order == self.stop_order: self.stop_order = None

            
    def stop(self):
        """CRITICAL METHOD: Executed at the end of the backtest. Closes any remaining open positions."""
        if self.position:
            self.log('END OF BACKTEST', 'Closing all remaining positions.')
            self.close()
            # Ensure any pending stop loss orders are canceled
            if self.stop_order and self.stop_order.status < self.stop_order.Completed:
                 self.cancel(self.stop_order)

    def log(self, tag, txt):
        """Custom logging function for easy debug tracing."""
        dt = self.data.datetime.date(0)
        print(f'{dt:%Y-%m-%d}, {tag}: {txt}')