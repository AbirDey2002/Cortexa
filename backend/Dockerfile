# python 3.11 as per cortexa env
FROM python:3.11-slim

# working dir
WORKDIR /app

# Copy requirements
# We prefer using requirements.lock if it exists for repeatable builds
COPY requirements.txt requirements.lock* ./

# Default to docker mode
ENV RUN_MODE=docker

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    if [ -f requirements.lock ]; then \
        pip install --no-cache-dir -r requirements.lock; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# Create non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app

# Copy the application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose the port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]