# Python and Library Imports
from pydantic_settings import BaseSettings

# Database Settings
class  Settings(BaseSettings):

    # Project Settings
    PROJECT_NAME: str = "Algorithmic Trading API"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "API for Algorithmic Trading"
    ENVIRONMENT: str = "development"

    # Logging Settings
    LOG_LEVEL: str = "INFO"

    # Database URL
    DATABASE_URL: str

    # .env Config
    class Config:

        env_file = ".env"

# Initialize Settings
settings = Settings()