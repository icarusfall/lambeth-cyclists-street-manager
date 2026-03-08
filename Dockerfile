FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir "fastapi>=0.115.0" "uvicorn[standard]>=0.34.0" \
    "httpx>=0.28.0" "shapely>=2.0" "pyproj>=3.7" "notion-client>=2.2.0" \
    "anthropic>=0.42.0" "pydantic-settings>=2.7" "python-dotenv>=1.0"

COPY data/ data/
COPY src/ src/

ENV PORT=8000
EXPOSE ${PORT}

CMD sh -c "uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"
