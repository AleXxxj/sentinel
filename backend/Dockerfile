# Sentinel backend container.
FROM python:3.12-slim

# Don't buffer stdout/stderr (so logs show up immediately), and don't write
# .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first (this layer is cached unless requirements change).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code.
COPY . .

# On start: apply DB migrations, then launch the server. Uses $PORT if the host
# provides one (most PaaS platforms do), defaulting to 8000.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
