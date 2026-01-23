# python 3.11 as per cortexa env
FROM python:3.11-slim

# working dir
WORKDIR /app

# copy requirements
COPY requirements.txt .

# default to docker mode
ENV RUN_MODE=docker

# Install dependencies
# --no-cache-dir reduces image size by removing temporarily download files
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the appliction code
COPY . .

# Expose the port
EXPOSE 8000

# start the application
# we use "0.0.0.0" to ensure it is accessible from outside the container
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]