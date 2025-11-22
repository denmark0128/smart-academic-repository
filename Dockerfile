# ---------- build stage ----------
FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install pip-tools / wheels if you use them (optional)
COPY requirements.txt /app/
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt -i https://pypi.org/simple --timeout 100


# ---------- final stage ----------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 gettext tzdata \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy project files
COPY . /app

# Make entrypoint executable
COPY ./entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Set environment
ENV PATH="/app:$PATH"

# Expose port for gunicorn
EXPOSE 8000

# Use entrypoint to run migrations/collectstatic, then start Gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "project_name.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--log-level", "info"]
