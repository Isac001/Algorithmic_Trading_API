# Use an official lightweight Python image as a parent image.
FROM python:3.11-slim

# Update system packages to patch security vulnerabilities.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container to /app.
WORKDIR /app

# Ensure that Python output is sent straight to the terminal without buffering.
ENV PYTHONUNBUFFERED=1

# Copy the dependency file first to leverage Docker's build cache.
COPY requirements.txt .
# Install any needed packages specified in requirements.txt.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Alembic configuration file into the container.
COPY alembic.ini .

# Copy the application source code into the container at /app/trading_api.
COPY ./trading_api /app/trading_api

# Command to run the Uvicorn server when the container launches.
# Este CMD será sobrescrito pelo comando definido no docker-compose.yaml.
CMD ["uvicorn", "trading_api.main:app", "--host", "0.0.0.0", "--port", "8000"]