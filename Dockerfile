# --- build the dashboard
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- runtime
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FIELDSCRIBE_DATA=/data FIELDSCRIBE_DIST=/app/frontend/dist
WORKDIR /app
COPY backend/requirements.txt backend/requirements-asr.txt backend/requirements-hub.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt -r backend/requirements-asr.txt -r backend/requirements-hub.txt
COPY backend/ backend/
COPY --from=web /web/dist frontend/dist
WORKDIR /app/backend
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
