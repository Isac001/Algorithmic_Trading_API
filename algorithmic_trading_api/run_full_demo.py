# Python and Library Imports
import requests
import json
import time
import logging

# --- CONFIGURATION ---
API_URL = "http://localhost:8000"

# List of tickers for data ingestion (diverse set for robust testing)
INGESTION_TICKERS = [
    "PETR4.SA",    # Oil/Gas
    "VALE3.SA",    # Mining
    "ITUB4.SA",    # Banking
    "EMBR3.SA",    # Aviation/Industry
    "MERC3.SA",    # Mercedes-Benz (BDR)
    "VISA34.SA"    # Visa (BDR)
]

# Setup Logging for the script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- PAYLOADS FOR DATA INGESTION ---

INGESTION_PAYLOAD = {
  "tickers": INGESTION_TICKERS,
  "start_date": "2020-01-01",
  "end_date": "2024-12-31",
  "calculate_indicators": True
}

# --- PAYLOADS FOR BACKTEST EXECUTION (PHASE 2) ---

# 1. SMA Cross Payload (PETR4.SA)
SMA_PETR4_PAYLOAD = {
  "ticker": "PETR4.SA",
  "start_date": "2021-01-01",
  "end_date": "2024-12-31",
  "strategy_type": "sma_cross",
  "strategy_params": {
    "fast": 50, "slow": 200, "atr_period": 14, "stop_multiplier": 2.0, "risk_per_trade_percent": 1.0 
  },
  "initial_cash": 100000.00,
  "commission": 0.001,
  "timeframe": "1d"
}

# 2. Breakout Payload (VALE3.SA)
BREAKOUT_VALE3_PAYLOAD = {
  "ticker": "VALE3.SA",
  "start_date": "2021-01-01",
  "end_date": "2024-12-31",
  "strategy_type": "breakout",
  "strategy_params": {
    "breakout_period": 20, "atr_period": 14, "stop_multiplier": 3.0, "risk_per_trade_percent": 1.0 
  },
  "initial_cash": 100000.00,
  "commission": 0.001,
  "timeframe": "1d"
}

# 3. SMA Cross Payload (ITUB4.SA)
SMA_ITUB4_PAYLOAD = {
  "ticker": "ITUB4.SA",
  "start_date": "2021-01-01",
  "end_date": "2024-12-31",
  "strategy_type": "sma_cross",
  "strategy_params": {
    "fast": 50, "slow": 200, "atr_period": 14, "stop_multiplier": 2.0, "risk_per_trade_percent": 1.0 
  },
  "initial_cash": 100000.00,
  "commission": 0.001,
  "timeframe": "1d"
}

# 4. Breakout Payload (EMBR3.SA)
BREAKOUT_EMBR3_PAYLOAD = {
  "ticker": "EMBR3.SA",
  "start_date": "2021-01-01",
  "end_date": "2024-12-31",
  "strategy_type": "breakout",
  "strategy_params": {
    "breakout_period": 20, "atr_period": 14, "stop_multiplier": 2.5, "risk_per_trade_percent": 1.0 
  },
  "initial_cash": 100000.00,
  "commission": 0.001,
  "timeframe": "1d"
}


# --- CORE FUNCTIONS ---

def wait_for_service():
    """Waits a short period to allow the FastAPI service and DB to initialize."""
    logger.info("Waiting for API service to become available...")
    time.sleep(5) 

def trigger_job(endpoint: str, payload: dict) -> dict:
    """Sends a POST request to trigger an asynchronous job (Data Ingestion or Backtest)."""
    url = f"{API_URL}{endpoint}"
    response = requests.post(url, json=payload)
    
    if response.status_code == 202:
        logger.info(f"Job scheduled successfully via {endpoint}.")
        return response.json()
    else:
        logger.error(f"Job scheduling FAILED for {endpoint}. Status: {response.status_code}")
        logger.error(f"Details: {response.text}")
        raise Exception(f"API failed to schedule job at {endpoint}")

def verify_job_status(job_id: int):
    """Polls the Backtest results endpoint to wait for the job to complete or fail."""
    endpoint = f"/backtests/{job_id}/results"
    max_checks = 20 # Maximum number of status checks
    check_interval = 2 # seconds

    logger.info(f"Monitoring backtest ID {job_id}. Checking status every {check_interval}s...")

    for i in range(max_checks):
        time.sleep(check_interval)
        response = requests.get(f"{API_URL}{endpoint}")
        
        if response.status_code == 200:
            status = response.json().get('status', 'N/A')
            logger.info(f"Backtest ID {job_id} status: {status}. Success!")
            return response.json()
        elif response.status_code == 409:
            # Status 409 means the job is still running
            status_detail = response.json().get('detail', '').split(': ')[1].split('.')[0]
            logger.warning(f"Backtest ID {job_id} still RUNNING. Attempt {i+1}/{max_checks}. Current status: {status_detail}")
            continue
        elif response.status_code == 400:
            # Status 400 means the job failed internally (e.g., no data, Ticker error)
            logger.error(f"Backtest ID {job_id} FAILED with an internal error (Status 400).")
            return response.json()
        else:
            logger.error(f"Failed to retrieve results for {job_id}. Status: {response.status_code}")
            return None
    
    logger.error(f"Backtest ID {job_id} timed out after {max_checks * check_interval} seconds.")
    return None

def main_demo():
    """Executes the entire end-to-end demonstration flow."""
    logger.info("--- Starting Full Project Demonstration ---")
    
    try:
        wait_for_service()
        
        # --- PHASE 1: DATA INGESTION (Requirement 20) ---
        logger.info(f"\n--- PHASE 1: DATA INGESTION for {len(INGESTION_TICKERS)} TICKERS ---")
        
        # 1. Trigger Data Ingestion Job
        ingestion_result = trigger_job("/data-sourcing/indicators/update", INGESTION_PAYLOAD)
        
        logger.info("Ingestion job triggered. Waiting 15s for data download and calculation to complete...")
        time.sleep(15) 
        
        
        # --- PHASE 2: BACKTEST EXECUTION ---
        
        results_list = []
        
        # 2. Backtest 1: SMA Cross (PETR4.SA)
        logger.info("\n--- PHASE 2.1: RUNNING SMA CROSS (PETR4.SA) ---")
        sma_petr4_result = trigger_job("/backtests/run", SMA_PETR4_PAYLOAD)
        results_list.append(verify_job_status(sma_petr4_result['backtest_id']))

        # 3. Backtest 2: Breakout (VALE3.SA)
        logger.info("\n--- PHASE 2.2: RUNNING BREAKOUT (VALE3.SA) ---")
        breakout_vale3_result = trigger_job("/backtests/run", BREAKOUT_VALE3_PAYLOAD)
        results_list.append(verify_job_status(breakout_vale3_result['backtest_id']))
        
        # 4. Backtest 3: SMA Cross (ITUB4.SA)
        logger.info("\n--- PHASE 2.3: RUNNING SMA CROSS (ITUB4.SA) ---")
        sma_itub4_result = trigger_job("/backtests/run", SMA_ITUB4_PAYLOAD)
        results_list.append(verify_job_status(sma_itub4_result['backtest_id']))

        # 5. Backtest 4: Breakout (EMBR3.SA)
        logger.info("\n--- PHASE 2.4: RUNNING BREAKOUT (EMBR3.SA) ---")
        breakout_embr3_result = trigger_job("/backtests/run", BREAKOUT_EMBR3_PAYLOAD)
        results_list.append(verify_job_status(breakout_embr3_result['backtest_id']))

        # 6. Check if all backtests were executed and verified        
        logger.info("\n--- DEMONSTRAÇÃO CONCLUÍDA ---")
        logger.info(f"Total Backtests Executed and Verified: {len([r for r in results_list if r])}/4")
        logger.info("Próxima Ação: Execute o script visualize_results.py para gerar a Curva de Equity.")
        
    # Handle exceptions
    except Exception as e:
        logger.critical(f"Demo failed: {e}")

# Execute the demo
if __name__ == "__main__":
    main_demo()