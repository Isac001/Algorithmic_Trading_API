# Python and Library Imports
from pydantic_settings import BaseSettings

# Database Settings
class  Settings(BaseSettings):

    # Database URL
    DATABASE_URL: str

    # .env Config
    class Config:

        env_file = ".env"

# Initialize Settings
settings = Settings()