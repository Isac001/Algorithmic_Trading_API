# Python and Library Imports
import requests
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import time
import sys

# --- CONFIGURATION ---
# Base URL for the FastAPI API service running in the Docker container
API_URL = "http://localhost:8000"

def calculate_drawdown(equity_series: pd.Series) -> pd.Series:

    """
    Calculates the Drawdown percentage relative to the previous peak.
    This is necessary for the detailed drawdown plot (Requirement R104).
    """

    # 1. Calculate the running maximum (peak) of the equity curve
    running_max = equity_series.cummax()
    
    # 2. Calculate the Drawdown percentage relative to the running maximum
    drawdown = (equity_series - running_max) / running_max
    return drawdown * 100 # Return as percentage

def discover_backtest_ids():

    """
    Attempts to discover and list existing backtest IDs by querying the /results endpoint.
    This provides the user with available data to visualize.
    """

    print("Discovering existing backtest IDs...")
    
    backtest_ids = []
    
    # Test IDs from 1 to 20 (a reasonable range for discovery)
    for backtest_id in range(1, 21):
        results_url = f"{API_URL}/backtests/{backtest_id}/results"
        
        try:
            response = requests.get(results_url)

            # Check for 200 OK (results ready)
            if response.status_code == 200:
                results = response.json()
                ticker = results.get('ticker', 'Unknown')

                # Only list backtests that are completed and have data
                if results.get('status') == 'COMPLETED':

                    backtest_ids.append({'id': backtest_id, 'ticker': ticker})

            elif response.status_code == 404:

                # Stop checking once IDs are no longer found
                pass 

            # Note: 409 Conflict (RUNNING) is ignored but not listed
                
        except Exception as e:

            # Handle connectivity errors (e.g., API is down)
            print(f"Error checking ID {backtest_id}: {e}")
    
    return backtest_ids

def get_user_selection(backtest_ids):

    """Handles user interaction to select which backtest(s) to visualize."""
    if not backtest_ids:
        return []
    
    print("\n" + "="*60)
    print("AVAILABLE COMPLETED BACKTESTS")
    print("="*60)
    
    # List all discovered backtests
    for bt_info in backtest_ids:
        print(f"ID: {bt_info['id']} | Symbol: {bt_info['ticker']}")
    
    print("\nOPTIONS:")
    print("1. Enter specific backtest ID")
    print("2. View ALL backtests")
    print("3. Exit")
    
    while True:
        try:
            choice = input(f"\nSelect option (1-3): ").strip()
            
            if not choice: continue
                
            choice_num = int(choice)
            
            if choice_num == 1:

                # Select a specific backtest by ID
                while True:
                    try:
                        backtest_id = int(input("Enter backtest ID: ").strip())
                        if any(bt['id'] == backtest_id for bt in backtest_ids):
                            return [backtest_id]
                        else:
                            print(f"Backtest ID {backtest_id} not found.")
                    except ValueError:
                        print("Please enter a valid number")

            elif choice_num == 2:
                # View all available backtests
                return [bt['id'] for bt in backtest_ids]
            
            elif choice_num == 3:
                # Exit the script
                return []
            else:
                print("Please enter a number between 1 and 3")
                
        except ValueError:
            print("Please enter a valid number")
        except KeyboardInterrupt:
            print("\nExiting...")
            return []

def fetch_and_plot_results(backtest_id: int):

    """Fetches results and delegates to the plotting function."""
    
    results_url = f"{API_URL}/backtests/{backtest_id}/results"
    
    print(f"\nFetching results for Backtest #{backtest_id}...")
    print(f"URL: {results_url}")
    
    try:
        response = requests.get(results_url)
        if response.status_code == 200:
            results = response.json()
            print("Results fetched successfully!")
            plot_results(results, backtest_id)
            return True
        else:
            print(f"Failed to fetch results: {response.status_code}")
            print(f"Detail: {response.json().get('detail', 'Unknown error')}")
            return False
                
    except Exception as e:
        print(f"Error fetching results: {e}")
        return False

def plot_results(results, backtest_id: int):

    """Plots the comprehensive backtest results including Equity Curve and Drawdown."""
    
    daily_data = results.get("daily_positions", [])
    trades_data = results.get("trades", [])
    metrics = results.get("metrics", {})
    
    if not daily_data:
        print("No daily position data to plot.")
        return
    
    # --- Data Preparation ---
    df = pd.DataFrame(daily_data)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df.sort_index(inplace=True)
    
    # Calculate Drawdown for the plot (Requisito R104)
    df['drawdown_pct'] = calculate_drawdown(df['equity'])
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True, 
                                   gridspec_kw={'height_ratios': [3, 1]})
    
    # --- AXIS 1: EQUITY CURVE (R105) ---
    ax1.plot(df.index, df['equity'], label='Equity Curve', linewidth=2, color='#1f77b4')
    ax1.set_title(f"Portfolio Equity Curve | Backtest #{backtest_id} - Ticker: {results.get('ticker', 'N/A')}", 
                  fontsize=14, fontweight='bold')
    ax1.set_ylabel('Portfolio Value (USD)', fontsize=12)
    ax1.grid(True, alpha=0.3)
    
    # Mark BUY/SELL trades on the equity curve
    if trades_data:
        trades_df = pd.DataFrame(trades_data)
        trades_df['date'] = pd.to_datetime(trades_df['date'])
        
        buy_trades = trades_df[trades_df['side'] == 'BUY']
        sell_trades = trades_df[trades_df['side'] == 'SELL']
        
        # Plot markers on the corresponding equity value
        for idx, trade in buy_trades.iterrows():
            trade_date = trade['date']
            if trade_date in df.index:
                equity_value = df.loc[trade_date, 'equity']
                ax1.scatter(trade_date, equity_value, color='green', marker='^', 
                           s=80, label='BUY' if idx == 0 else "", zorder=5)
        
        for idx, trade in sell_trades.iterrows():
            trade_date = trade['date']
            if trade_date in df.index:
                equity_value = df.loc[trade_date, 'equity']
                ax1.scatter(trade_date, equity_value, color='red', marker='v', 
                           s=80, label='SELL' if idx == 0 else "", zorder=5)
        
        ax1.legend(fontsize=10)
    
    # Add metrics annotation (R103, R104)
    total_return = metrics.get('total_return', 0) * 100
    sharpe_ratio = metrics.get('sharpe', 0)
    max_drawdown = metrics.get('max_drawdown', 0)
    win_rate = metrics.get('win_rate', 0) * 100
    
    metrics_text = f"Total Return: {total_return:.1f}%\nSharpe Ratio: {sharpe_ratio:.2f}\nMax Drawdown: {max_drawdown:.1f}%\nWin Rate: {win_rate:.1f}%"
    ax1.text(0.02, 0.98, metrics_text, transform=ax1.transAxes, 
             verticalalignment='top', fontsize=10,
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
    
    # --- AXIS 2: DRAWDOWN (R104) ---
    ax2.fill_between(df.index, df['drawdown_pct'], 0, alpha=0.3, color='red')
    ax2.plot(df.index, df['drawdown_pct'], color='red', linewidth=1)
    ax2.set_ylabel('Drawdown (%)', fontsize=12, color='red')
    ax2.set_xlabel('Date', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(axis='y', labelcolor='red')
    
    # Highlight maximum drawdown point
    max_dd_idx = df['drawdown_pct'].idxmin()
    max_dd_value = df['drawdown_pct'].min()
    ax2.scatter(max_dd_idx, max_dd_value, color='darkred', s=60, zorder=5)
    
    plt.gcf().autofmt_xdate()
    plt.tight_layout()
    plt.show()
    
    # Print detailed statistics
    print("\n" + "="*50)
    print(f"BACKTEST #{backtest_id} - STATISTICS SUMMARY")
    print("="*50)
    print(f"Symbol: {results.get('ticker')}")
    print(f"Period: {df.index.min().strftime('%Y-%m-%d')} to {df.index.max().strftime('%Y-%m-%d')}")
    print(f"Final Equity: ${df['equity'].iloc[-1]:,.2f}")
    print(f"Total Trades: {len(trades_data)}")

def main():
    """Main execution function to run the visualization script."""
    print("=== Trading Algorithmic API - Results Visualization ===\n")
    
    # 1. Discover existing backtests
    backtest_ids = discover_backtest_ids()
    
    if not backtest_ids:
        print("\nNo completed backtests found with results available.")
        print("Please run POST /backtests/run first.")
        return
    
    print(f"\nFound {len(backtest_ids)} backtest(s) with results")
    
    # 2. Get user selection
    selected_ids = get_user_selection(backtest_ids)
    
    if not selected_ids:
        print("Exiting...")
        return
    
    # 3. Plot selected backtests
    for i, backtest_id in enumerate(selected_ids, 1):
        print("\n" + "="*60)
        print(f"VISUALIZING BACKTEST #{backtest_id} ({i}/{len(selected_ids)})")
        print("="*60)
        
        success = fetch_and_plot_results(backtest_id)
        if not success:
            print(f"Failed to visualize backtest #{backtest_id}. Check API logs.")
        
        # Pause between visualizations
        if i < len(selected_ids):
            input("\nPress Enter to view next backtest...")

# --- EXECUTION PRINCIPAL ---
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nScript interrupted by user. Goodbye!")
    except Exception as e:
        print(f"\nUnexpected error during script execution: {e}")