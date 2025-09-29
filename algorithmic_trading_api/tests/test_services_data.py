# Python and Library Imports
import pytest
import pandas as pd
import numpy as np

# Import the helper functions from your data sourcing service
from trading_api.modules.data_sourcing.services import calculate_sma, calculate_atr

@pytest.fixture
def sample_price_data():
    """Provides a controlled DataFrame for calculation tests."""
    # Define simple mock price data
    data = {
        'Close': [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0],
        'High':  [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0],
        'Low':   [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0],
    }
    # Create a simple time-series index
    index = pd.to_datetime(pd.Series(range(10), name='Date'))
    return pd.DataFrame(data, index=index)

def test_calculate_sma_correctness(sample_price_data):
    """Tests if the SMA calculation is mathematically accurate for a given window."""
    df = sample_price_data
    
    # Calculate SMA with length 3
    sma_series = calculate_sma(df, length=3)
    
    # Check a known calculated value (index 4 should be 13.0)
    assert np.isclose(sma_series.iloc[4], 13.0)
    # Check that initial values are NaN (insufficient data)
    assert pd.isna(sma_series.iloc[1])

def test_calculate_atr_output_format(sample_price_data):
    """Tests if the ATR calculation returns a valid series of the expected length."""
    df = sample_price_data
    
    # Calculate ATR with length 14
    atr_series = calculate_atr(df, length=14)
    
    # Check that the final value is not NaN
    assert not pd.isna(atr_series.iloc[-1])
    # Check that the output series length matches the input DataFrame length
    assert len(atr_series) == len(df)