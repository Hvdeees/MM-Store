FROM python:3.12-slim

# Don't write .pyc files; print logs immediately (useful in Docker logs).
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Use the timezone rules from the pinned `tzdata` Python package, never the (possibly outdated) system copy:
# Morocco changed its time zone in Sept 2026 and old data would put sales on the wrong day.
ENV PYTHONTZPATH=

WORKDIR /code
# Copy requirements first: Docker caches this layer, so code changes don't reinstall every package.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# Run as a normal user, not root: limits the damage if the app is ever compromised.
RUN useradd --create-home appuser && mkdir -p /code/media && chown appuser /code/media
USER appuser

EXPOSE 8000
# Apply any pending database migrations, then start the server.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
