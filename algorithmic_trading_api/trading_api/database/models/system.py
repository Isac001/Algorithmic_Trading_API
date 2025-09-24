# Python and Library Imports
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from .base import Base

# Database Models
class JobRun(Base):
    """
    Model to log the execution of background routines (cron jobs).
    """
    __tablename__ = 'job_runs'

    # Columns of the table  
    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    status = Column(String, nullable=False)  
    message = Column(String)