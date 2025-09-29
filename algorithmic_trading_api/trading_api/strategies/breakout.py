# Python and Library Imports
import backtrader as bt
from datetime import datetime
import logging

# Basic logging configuration for job tracking
logger = logging.getLogger(__name__)

class BreakoutStrategy(bt.Strategy):
    """
    Breakout Strategy based on Donchian Channel with comprehensive trade tracking and risk management.
    Implements trend-following strategy using price breakouts of N-period highs/lows.
    """
    
    # Strategy parameters with default values
    params = (
        ("breakout_period", 20),         # Period for breakout detection (Donchian channel)
        ("period_high", 20),             # Period for high breakout (Donchian high) - maintained for backward compatibility
        ("period_low", 10),              # Period for low breakout (Donchian low)  
        ("atr_period", 14),              # ATR period for volatility calculation
        ("stop_multiplier", 2.0),        # Multiplier for ATR-based stop loss
        ("risk_per_trade_percent", 1.0), # Maximum risk per trade as percentage of capital
        ("use_close_for_breakout", True), # Use close price instead of high/low for breakouts
        ("printlog", True)               # Enable/disable trading log output
    )

    def __init__(self):
        """
        Initialize strategy indicators, trackers, and control variables.
        """
        
        # Use breakout_period for both high and low if not specified separately
        period_high = self.p.breakout_period
        period_low = self.p.period_low if hasattr(self.p, 'period_low') else self.p.breakout_period
        
        # Technical indicators for breakout signals
        # Donchian Channel - highest high and lowest low over periods
        self.donchian_high = bt.indicators.Highest(self.data.high, period=period_high)
        self.donchian_low = bt.indicators.Lowest(self.data.low, period=period_low)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        
        # Order management and position tracking
        self.order = None                # Current pending order
        self.stop_order = None           # Stop loss order reference
        self.entry_price = None          # Price at position entry
        self.entry_size = None           # Size at position entry
        
        # Trade tracking and data collection
        self.trades_list = []            # Completed trades for persistence
        self.current_trade = None        # Currently open trade
        self.trade_counter = 0           # Unique trade identifier counter
        
        # Portfolio performance tracking
        self.daily_position_data = []    # Daily portfolio snapshot
        
        # Breakout state tracking
        self.breakout_high = None        # Current breakout high level
        self.breakout_low = None         # Current breakout low level
        self.in_breakout_zone = False    # Whether price is in breakout zone
        
        logger.info(f'Breakout Strategy initialized with breakout_period={self.p.breakout_period}')

    def log(self, txt, dt=None):
        """
        Log trading activity with timestamp if logging is enabled.
        
        Args:
            txt: Message to log
            dt: Optional datetime, uses current bar if not provided
        """
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def notify_order(self, order):
        """
        Handle order status updates and manage trade lifecycle.
        Trades are tracked from entry to exit with PnL calculation.
        
        Args:
            order: Backtrader order object with execution details
        """
        
        # Skip order updates for submitted/accepted states
        if order.status in [order.Submitted, order.Accepted]:
            return

        # Handle completed orders (both entry and exit)
        if order.status == order.Completed:
            if order.isbuy():
                # Record new long position
                self.entry_price = order.executed.price
                self.entry_size = order.executed.size
                
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size}')
                
                # Create new trade record
                trade_id = f"breakout_trade_{self.trade_counter}"
                self.current_trade = {
                    'trade_id': trade_id,
                    'entry_date': self.data.datetime.datetime(0),
                    'entry_price': float(order.executed.price),
                    'size': float(order.executed.size),
                    'entry_commission': float(order.executed.comm),
                    'side': 'BUY',
                    'status': 'OPEN',
                    'breakout_type': 'HIGH',  # Track breakout type
                    'breakout_period': self.p.breakout_period  # Include breakout period in trade data
                }
                self.trade_counter += 1
                
                # Calculate and place stop loss order based on ATR
                stop_price = order.executed.price - (self.p.stop_multiplier * self.atr[0])
                self.stop_order = self.sell(
                    exectype=bt.Order.Stop,
                    price=stop_price,
                    size=order.executed.size
                )
                
            elif order.issell():
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size}')
                
                # If we have a current open trade, close it
                if self.current_trade and self.current_trade['status'] == 'OPEN':
                    # Calculate trade performance metrics
                    pnl_net = (order.executed.price - self.current_trade['entry_price']) * self.current_trade['size']
                    pnl_comm = pnl_net - order.executed.comm - self.current_trade['entry_commission']
                    
                    # Create complete trade record
                    completed_trade = {
                        'trade_id': self.current_trade['trade_id'],
                        'entry_date': self.current_trade['entry_date'],
                        'exit_date': self.data.datetime.datetime(0),
                        'entry_price': self.current_trade['entry_price'],
                        'exit_price': float(order.executed.price),
                        'size': self.current_trade['size'],
                        'entry_commission': self.current_trade['entry_commission'],
                        'exit_commission': float(order.executed.comm),
                        'total_commission': self.current_trade['entry_commission'] + float(order.executed.comm),
                        'pnl_gross': pnl_net,
                        'pnl_net': pnl_comm,
                        'side': self.current_trade['side'],
                        'status': 'CLOSED',
                        'breakout_type': self.current_trade.get('breakout_type', 'UNKNOWN'),
                        'breakout_period': self.current_trade.get('breakout_period', self.p.breakout_period)
                    }
                    
                    self.trades_list.append(completed_trade)
                    self.current_trade = None
                    self.log(f'BREAKOUT TRADE CLOSED: PnL Net: {pnl_comm:.2f}')
                
                # Cancel stop loss order if this was a regular exit (not stop triggered)
                if self.stop_order and order != self.stop_order:
                    self.cancel(self.stop_order)
                    self.stop_order = None

        # Log order failures for debugging
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order {order.status}')
            
        # Reset order reference to allow new orders
        self.order = None

    def notify_trade(self, trade):
        """
        Backup trade tracking using Backtrader's native trade analysis.
        Provides fallback mechanism for trade data collection.
        
        Args:
            trade: Backtrader trade object with trade details
        """
        if trade.isclosed:
            pnl = trade.pnl
            pnlcomm = trade.pnlcomm
            
            self.log(f'BACKTRADER BREAKOUT TRADE CLOSED, Gross PnL: {pnl:.2f}, Net PnL: {pnlcomm:.2f}')
            
            # Only create backup trade if we don't already have it in trades_list
            trade_exists = any(t['trade_id'] == f"breakout_backup_{len(self.trades_list)}" for t in self.trades_list)
            if not trade_exists:
                backup_trade = {
                    'trade_id': f"breakout_backup_{len(self.trades_list)}",
                    'entry_date': bt.num2date(trade.dtopen) if hasattr(trade, 'dtopen') else self.data.datetime.datetime(0),
                    'exit_date': bt.num2date(trade.dtclose) if hasattr(trade, 'dtclose') else self.data.datetime.datetime(0),
                    'entry_price': float(trade.price),
                    'exit_price': float(trade.price + (trade.pnl / abs(trade.size))) if trade.size != 0 else float(trade.price),
                    'size': float(abs(trade.size)),
                    'entry_commission': 0.0,
                    'exit_commission': float(trade.commission or 0.0),
                    'total_commission': float(trade.commission or 0.0),
                    'pnl_gross': float(trade.pnl or 0.0),
                    'pnl_net': float(trade.pnlcomm or 0.0),
                    'side': 'BUY' if trade.size > 0 else 'SELL',
                    'status': 'CLOSED',
                    'source': 'backtrader_notify',
                    'breakout_type': 'BACKUP',
                    'breakout_period': self.p.breakout_period
                }
                self.trades_list.append(backup_trade)

    def next(self):
        """
        Main strategy logic executed on each new bar.
        Generates breakout signals and manages position lifecycle.
        """
        
        # Calculate periods for Donchian channels
        period_high = self.p.breakout_period
        period_low = self.p.period_low if hasattr(self.p, 'period_low') else self.p.breakout_period
        
        # Skip processing if insufficient data or pending orders
        required_data = max(period_high, period_low, self.p.atr_period)
        if len(self.data) < required_data or self.order:
            return

        # Capture daily portfolio snapshot for performance tracking
        try:
            self.daily_position_data.append({
                'date': self.data.datetime.date(0),
                'position_size': self.position.size if self.position else 0,
                'cash': float(self.broker.getcash()),
                'equity': float(self.broker.getvalue()),
                'drawdown': 0.0,  # Calculated post-process in service layer
                'donchian_high': float(self.donchian_high[0]),
                'donchian_low': float(self.donchian_low[0]),
                'breakout_period': self.p.breakout_period
            })
        except Exception as e:
            logger.warning(f"Error in daily tracking: {e}")

        # Determine price to use for breakout detection
        if self.p.use_close_for_breakout:
            price_for_breakout = self.data.close[0]
        else:
            price_for_breakout = self.data.high[0]  # For long entries

        # Generate exit signal when price breaks below Donchian low
        if self.position and self.data.low[0] <= self.donchian_low[0]:
            self.log(f'SELL SIGNAL: Price {self.data.low[0]:.2f} <= Donchian Low {self.donchian_low[0]:.2f} (Period: {period_low})')
            self.order = self.close()
            return

        # Generate entry signal when price breaks above Donchian high
        if not self.position and price_for_breakout >= self.donchian_high[0]:
            # Calculate position size with risk management
            size = self.calculate_position_size()
            if size > 0:
                self.log(f'BUY SIGNAL: Price {price_for_breakout:.2f} >= Donchian High {self.donchian_high[0]:.2f} (Period: {period_high})')
                self.order = self.buy(size=size)

    def calculate_position_size(self):
        """
        Calculate position size based on risk management rules.
        Uses ATR for stop loss placement and limits risk per trade.
        
        Returns:
            int: Number of shares to trade, or 0 if no valid trade
        """
        try:
            entry_price = self.data.close[0]
            stop_price = entry_price - (self.p.stop_multiplier * self.atr[0])
            risk_per_share = entry_price - stop_price
            
            # Validate risk calculation
            if risk_per_share <= 0:
                return 0

            # Calculate position size based on risk tolerance
            risk_amount = (self.p.risk_per_trade_percent / 100.0) * self.broker.getvalue()
            size = int(risk_amount / risk_per_share)
            
            # Ensure position doesn't exceed available capital
            max_by_cash = int(self.broker.getcash() * 0.95 / entry_price)
            final_size = min(size, max_by_cash)
            
            # Log position sizing details
            self.log(f'Position sizing: Risk={risk_amount:.2f}, Size={final_size}, Entry={entry_price:.2f}, Stop={stop_price:.2f}, BreakoutPeriod={self.p.breakout_period}')
            
            return final_size
            
        except Exception as e:
            logger.error(f"Error in position sizing: {e}")
            return 0

    def stop(self):
        """
        Strategy cleanup method called at backtest completion.
        Ensures all positions are closed and trade records are finalized.
        """
        self.log('Breakout Strategy stopping - finalizing trade records')
        
        # Close any remaining open positions at strategy end
        if self.position:
            self.log(f'Closing remaining position: {self.position.size} shares')
            self.close()  # This will trigger notify_order and close the trade properly
            
        # If there's still an open trade (shouldn't happen if close() worked), close it manually
        if self.current_trade and self.current_trade['status'] == 'OPEN':
            self.log(f'Manual closing of open breakout trade: {self.current_trade["trade_id"]}')
            # Mark as closed with current price
            manual_close_trade = self.current_trade.copy()
            manual_close_trade.update({
                'exit_date': self.data.datetime.datetime(0),
                'exit_price': float(self.data.close[0]),
                'exit_commission': 0.0,
                'total_commission': manual_close_trade['entry_commission'],
                'pnl_gross': (self.data.close[0] - manual_close_trade['entry_price']) * manual_close_trade['size'],
                'pnl_net': (self.data.close[0] - manual_close_trade['entry_price']) * manual_close_trade['size'] - manual_close_trade['entry_commission'],
                'status': 'CLOSED'
            })
            self.trades_list.append(manual_close_trade)
            self.current_trade = None
        
        # Log final trade count for debugging
        self.log(f'Final breakout trades count: {len(self.trades_list)} (Breakout Period: {self.p.breakout_period})')
        for i, trade in enumerate(self.trades_list):
            self.log(f'Breakout Trade {i}: {trade["trade_id"]} - PnL: {trade.get("pnl_net", 0):.2f}')