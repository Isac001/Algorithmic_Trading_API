# Algorithmic_Trading_API
Repositório destinado a armazenar API back-end simples focada em mercado financeiro (Fin Tech)

{
  "tickers": [
    "MERC3.SA",
    "AAPL34.SA",
    "ITUB4.SA"
  ],
  "start_date": "2020-01-01",
  "end_date": "2024-12-31",
  "calculate_indicators": true
}


{
  "ticker": "ITUB4.SA",
  "start_date": "2021-01-01",
  "end_date": "2024-12-31",
  "strategy_type": "sma_cross",
  "strategy_params": {
    "fast": 50,
    "slow": 200,
    "atr_period": 14,
    "stop_multiplier": 2.0,
    "risk_per_trade_percent": 1.0 
  },
  "initial_cash": 100000.00,
  "commission": 0.001,
  "timeframe": "1d"
}

{
  "ticker": "AAPL34.SA",
  "start_date": "2021-01-01",
  "end_date": "2024-12-31",
  "strategy_type": "breakout",
  "strategy_params": {
    "breakout_period": 20,
    "atr_period": 14,
    "stop_multiplier": 3.0,
    "risk_per_trade_percent": 1.0
  },
  "initial_cash": 100000.00,
  "commission": 0.001,
  "timeframe": "1d"
}

docker compose run --rm app pytest tests/test_strategies_risk.py -v -s