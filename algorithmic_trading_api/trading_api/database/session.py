# Python and Library Imports
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from ..core.config import settings
from sqlalchemy.orm import sessionmaker

# Set Database Engine
# Creates the core database 'engine' by connecting to the URL specified in the settings.
# The engine is the central source of connectivity to a particular database.
engine = create_engine(settings.DATABASE_URL)

# Set Database Session Factory
# Creates a 'SessionLocal' class, which will serve as a factory for new Session objects.
# A Session is a temporary "conversation" with the database.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Set Declarative Base
# Creates a base class that all of our ORM models (classes that map to tables) will inherit from.
Base = declarative_base()


# Database Dependency for FastAPI
def get_db():

    # Create a new database session instance from our factory.
    db = SessionLocal()

    # The 'try...finally' block ensures that the database connection is always closed,
    # even if an error occurs during the request.
    try:

        # 'yield' provides the database session to the API endpoint that needs it.
        # The code of the endpoint will run here.
        yield db

    finally:

        # After the endpoint has finished its work (or an error occurred),
        # this code will run and close the session, releasing the connection.
        db.close()