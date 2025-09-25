# Python and Library Imports
from pydantic import BaseModel
from typing import List

# Request Models
class DataIngestionRequest(BaseModel):

    # Attributes
    tickers: List[str]

    # Config
    class Config:
        schema_extra = {
            "example": {
                "tickers": ["AAPL", "GOOGL", "MSFT"]
            }
        }