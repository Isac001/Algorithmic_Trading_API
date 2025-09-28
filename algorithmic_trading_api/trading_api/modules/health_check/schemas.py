
# Python and Library Imports
from pydantic import BaseModel, Field
from typing import Optional

# Health Check Response
class HealthCheckResponse(BaseModel):

    """Schema for the basic service health check response"""
    
    status: str = Field(..., description="Overall service status (OK or ERROR).")
    database_status: str = Field(..., description="Status of the connection to PostgreSQL.")
    message: str = Field(..., description="A simple status message.")