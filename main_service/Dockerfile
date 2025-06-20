# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=True
ENV APP_HOME=/app
WORKDIR ${APP_HOME}

# Install system dependencies that might be needed by some Python packages
# (e.g., for cryptography, often a dependency of google-cloud libraries)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc libffi-dev musl-dev && rm -rf /var/lib/apt/lists/*

# Install pip requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the local code to the container
COPY main.py .
COPY dlp_config.yaml .

# Expose the port the app runs on
EXPOSE 8080

# Run the web service on container startup using Gunicorn
# CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
# For Cloud Run, the PORT environment variable is automatically set.
# For local development, set a default PORT. Cloud Run will override this.
ENV PORT=8080
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 main:app