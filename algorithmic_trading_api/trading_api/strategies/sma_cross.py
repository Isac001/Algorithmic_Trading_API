# Python and Library Imports
import backtrader as bt
from datetime import datetime
import logging

# Basic logging configuration for job tracking
logger = logging.getLogger(__name__)

class SMACross(bt.Strategy):
    """
    Moving Average Cross Strategy with comprehensive trade tracking and risk management.
    Implements trend-following strategy using SMA crossover signals with ATR-based stops.
    """
    
    # Strategy parameters with default values
    params = (
        ("fast", 50),                    # Fast moving average period
        ("slow", 200),                   # Slow moving average period  
        ("atr_period", 14),              # ATR period for volatility calculation
        ("stop_multiplier", 2.0),        # Multiplier for ATR-based stop loss
        ("risk_per_trade_percent", 1.0), # Maximum risk per trade as percentage of capital
        ("printlog", True)               # Enable/disable trading log output
    )

    def __init__(self):
        """
        Initialize strategy indicators, trackers, and control variables.
        """
        
        # Technical indicators for signal generation
        self.fast_sma = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.slow_sma = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)
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
        
        logger.info('SMACross Strategy initialized with complete trade tracking')

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
                trade_id = f"trade_{self.trade_counter}"
                self.current_trade = {
                    'trade_id': trade_id,
                    'entry_date': self.data.datetime.datetime(0),
                    'entry_price': float(order.executed.price),
                    'size': float(order.executed.size),
                    'entry_commission': float(order.executed.comm),
                    'side': 'BUY',
                    'status': 'OPEN'
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
                        'status': 'CLOSED'
                    }
                    
                    self.trades_list.append(completed_trade)
                    self.current_trade = None
                    self.log(f'TRADE CLOSED: PnL Net: {pnl_comm:.2f}')
                
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
            
            self.log(f'BACKTRADER TRADE CLOSED, Gross PnL: {pnl:.2f}, Net PnL: {pnlcomm:.2f}')
            
            # Only create backup trade if we don't already have it in trades_list
            trade_exists = any(t['trade_id'] == f"backup_{len(self.trades_list)}" for t in self.trades_list)
            if not trade_exists:
                backup_trade = {
                    'trade_id': f"backup_{len(self.trades_list)}",
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
                    'source': 'backtrader_notify'
                }
                self.trades_list.append(backup_trade)

    def next(self):
        """
        Main strategy logic executed on each new bar.
        Generates trading signals and manages position lifecycle.
        """
        
        # Skip processing if insufficient data or pending orders
        if len(self.data) < max(self.p.fast, self.p.slow, self.p.atr_period) or self.order:
            return

        # Capture daily portfolio snapshot for performance tracking
        try:
            self.daily_position_data.append({
                'date': self.data.datetime.date(0),
                'position_size': self.position.size if self.position else 0,
                'cash': float(self.broker.getcash()),
                'equity': float(self.broker.getvalue()),
                'drawdown': 0.0  # Calculated post-process in service layer
            })
        except Exception as e:
            logger.warning(f"Error in daily tracking: {e}")

        # Generate exit signal when fast SMA crosses below slow SMA
        if self.position and self.crossover < 0:
            self.log(f'SELL SIGNAL: Closing {self.position.size} shares @ {self.data.close[0]:.2f}')
            self.order = self.close()
            return

        # Generate entry signal when fast SMA crosses above slow SMA
        if not self.position and self.crossover > 0:
            # Calculate position size with risk management
            size = self.calculate_position_size()
            if size > 0:
                self.log(f'BUY SIGNAL: {size} shares @ {self.data.close[0]:.2f}')
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
            return min(size, max_by_cash)
            
        except Exception as e:
            logger.error(f"Error in position sizing: {e}")
            return 0

    def stop(self):
        """
        Strategy cleanup method called at backtest completion.
        Ensures all positions are closed and trade records are finalized.
        """
        self.log('Strategy stopping - finalizing trade records')
        
        # Close any remaining open positions at strategy end
        if self.position:
            self.log(f'Closing remaining position: {self.position.size} shares')
            self.close()  # This will trigger notify_order and close the trade properly
            
        # If there's still an open trade (shouldn't happen if close() worked), close it manually
        if self.current_trade and self.current_trade['status'] == 'OPEN':
            self.log(f'Manual closing of open trade: {self.current_trade["trade_id"]}')
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
        self.log(f'Final trades count: {len(self.trades_list)}')
        for i, trade in enumerate(self.trades_list):
            self.log(f'Trade {i}: {trade["trade_id"]} - PnL: {trade.get("pnl_net", 0):.2f}')