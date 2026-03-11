FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ /app/

# Expose port
EXPOSE 8081

# Run server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8081"]
