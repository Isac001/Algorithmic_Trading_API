# trading_api/main.py
from fastapi import FastAPI

# Esta é a linha crucial que estava faltando ou tinha um nome diferente
app = FastAPI(
    title="Algorithmic Trading API",
    description="API para backtests de estratégias de trading.",
    version="0.1.0"
)

# Exemplo de endpoint
@app.get("/")
def read_root():
    return {"message": "Welcome to the Algorithmic Trading API"}

