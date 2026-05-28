# Radio Alerting Service

A containerized monitoring and alerting service for radio station operations. This service monitors Live365 station status and provides endpoints for silence detection alerts via PagerDuty.

## Features

- **Live365 Monitoring**: Checks Live365 station status every 5 minutes
- **Silence Detection**: API endpoints to trigger alerts when silence is detected
- **PagerDuty Integration**: Automatic incident creation and resolution
- **Health Checks**: Built-in health check endpoint for monitoring

## Tech Stack

- **FastAPI**: Modern, fast web framework for building APIs
- **Redis**: State management and persistence
- **APScheduler**: Scheduled task execution
- **Docker**: Containerization for easy deployment

## Local Development

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Redis (if running without Docker)

### Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Copy environment variables:

```bash
cp .env.example .env
```

3. Edit `.env` with your credentials

### Running Locally

**With Docker Compose (recommended):**

```bash
docker-compose up
```

**Without Docker:**

```bash
# Start Redis
redis-server

# Run the application
python main.py
```

The API will be available at `http://localhost:8000`

## Deployment with Coolify

### Option 1: Docker Compose Deployment

1. In Coolify, create a new service
2. Select "Docker Compose" as the deployment type
3. Point to this repository
4. Add environment variables in Coolify:
   - `LIVE365_EMAIL`
   - `LIVE365_PASSWORD`
   - `PAGERDUTY_ROUTING_KEY`
   - `SILENCE_KEY`
5. Deploy

### Option 2: Dockerfile Deployment

1. In Coolify, create a new service
2. Select "Dockerfile" as the deployment type
3. Point to this repository
4. Add a Redis service in Coolify
5. Set environment variables:
   - `REDIS_URL=redis://redis:6379`
   - `LIVE365_EMAIL`
   - `LIVE365_PASSWORD`
   - `PAGERDUTY_ROUTING_KEY`
   - `SILENCE_KEY`
6. Deploy

## API Endpoints

- `GET /healthz` - Health check endpoint
- `GET /silence?secret=<key>` - Trigger silence detection alert
- `GET /returned?secret=<key>` - Resolve silence alert

## Environment Variables

See `.env.example` for required environment variables.
