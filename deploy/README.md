# Deployment Guide

This directory contains deployment configurations for the Polymarket Trading Bot.

## Deployment Options

### Option 1: Docker Compose (Recommended)

The simplest deployment method. All services run in containers with automatic restart.

```bash
# Production deployment
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f bot

# Stop all services
docker-compose -f docker-compose.prod.yml down
```

**Services:**
- `bot` - Main trading bot (ingestion + engine)
- `dashboard` - Monitoring dashboard on port 5050
- `postgres` - PostgreSQL database
- `redis` - Redis cache (optional)

### Option 2: systemd (Bare Metal)

For traditional Linux server deployment with systemd.

```bash
# 1. Create service user
sudo useradd -r -s /bin/false trading

# 2. Install application
sudo mkdir -p /opt/polymarket-bot
sudo cp -r . /opt/polymarket-bot/
sudo chown -R trading:trading /opt/polymarket-bot

# 3. Create virtual environment
sudo -u trading python3 -m venv /opt/polymarket-bot/.venv
sudo -u trading /opt/polymarket-bot/.venv/bin/pip install -r /opt/polymarket-bot/requirements.txt

# 4. Create environment file
sudo cp .env.example /opt/polymarket-bot/.env
sudo nano /opt/polymarket-bot/.env  # Edit configuration

# 5. Install systemd services
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# 6. Enable and start services
sudo systemctl enable polymarket-bot polymarket-dashboard
sudo systemctl start polymarket-bot polymarket-dashboard

# 7. Check status
sudo systemctl status polymarket-bot
sudo journalctl -u polymarket-bot -f
```

**Services:**
- `polymarket-bot.service` - Main bot (all-in-one)
- `polymarket-dashboard.service` - Dashboard only
- `polymarket-ingestion.service` - Ingestion only (for scaling)

### Option 3: Supervisor

Alternative process manager, useful if systemd is not available.

```bash
# 1. Install supervisor
sudo apt install supervisor

# 2. Create log directory
sudo mkdir -p /var/log/polymarket
sudo chown trading:trading /var/log/polymarket

# 3. Install configuration
sudo cp deploy/supervisor/polymarket.conf /etc/supervisor/conf.d/

# 4. Reload and start
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start polymarket:*

# 5. Check status
sudo supervisorctl status polymarket:*
```

## Configuration

### Environment Variables

Create a `.env` file with:

```bash
# Database
DATABASE_URL=postgresql://predict:predict@localhost:5432/predict

# Trading
DRY_RUN=true                    # Set to 'false' for live trading
PRICE_THRESHOLD=0.95
POSITION_SIZE=20
MAX_POSITIONS=50

# Monitoring
DASHBOARD_ENABLED=true
DASHBOARD_PORT=5050

# Alerts (optional)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Logging
LOG_LEVEL=INFO
```

### Polymarket Credentials

For live trading, create `polymarket_api_creds.json`:

```json
{
  "api_key": "your-api-key",
  "api_secret": "your-api-secret",
  "api_passphrase": "your-passphrase",
  "private_key": "0x...",
  "funder": "0x...",
  "signature_type": 2,
  "host": "https://clob.polymarket.com",
  "chain_id": 137
}
```

## Health Checks

### Dashboard Endpoints

- `http://localhost:5050/health` - Overall health status
- `http://localhost:5050/api/positions` - Current positions
- `http://localhost:5050/api/metrics` - Trading metrics

### Manual Health Check

```bash
# Check if services are running
curl -s http://localhost:5050/health | jq .

# Check database connectivity
psql $DATABASE_URL -c "SELECT 1"
```

## Troubleshooting

### Bot won't start

1. Check logs: `journalctl -u polymarket-bot -n 50`
2. Verify database connection: `psql $DATABASE_URL -c "SELECT 1"`
3. Check environment file: `cat /opt/polymarket-bot/.env`

### Dashboard not accessible

1. Check if port 5050 is open: `ss -tlnp | grep 5050`
2. Kill orphan processes: `fuser -k 5050/tcp`
3. Check firewall: `sudo ufw allow 5050/tcp`

### WebSocket disconnections

1. Check internet connectivity
2. Verify Polymarket API is up: `curl https://gamma-api.polymarket.com/markets`
3. Check logs for rate limiting

### Database issues

1. Check PostgreSQL status: `systemctl status postgresql`
2. Verify schema: `psql $DATABASE_URL -c "\dt"`
3. Re-run migrations: `psql $DATABASE_URL < seed/01_schema.sql`

## Scaling

### Horizontal Scaling

For high-volume processing, run ingestion separately:

```bash
# Server 1: Ingestion only
python -m polymarket_bot.main --mode ingestion

# Server 2: Engine only
python -m polymarket_bot.main --mode engine

# Server 3: Monitor only
python -m polymarket_bot.main --mode monitor
```

### Resource Recommendations

| Service | CPU | Memory | Disk |
|---------|-----|--------|------|
| Bot (all) | 2 cores | 2GB | 10GB |
| Dashboard | 0.5 cores | 512MB | 1GB |
| PostgreSQL | 1 core | 1GB | 50GB |

## Backup

### Database Backup

```bash
# Daily backup (add to cron)
0 2 * * * pg_dump $DATABASE_URL > /backups/predict_$(date +\%Y\%m\%d).sql

# Keep last 7 days
find /backups -name "predict_*.sql" -mtime +7 -delete
```

### Restore

```bash
psql $DATABASE_URL < /backups/predict_20250101.sql
```
