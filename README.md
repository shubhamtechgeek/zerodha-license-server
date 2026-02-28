# License Server — Zerodha Portfolio Dashboard

## Quick Start (Local Development)

### 1. Start PostgreSQL with Docker

```bash
cd license_server
docker-compose up db -d
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set:
#   DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/licenses
#   LICENSE_JWT_SECRET=<random-64-char-string>
#   ADMIN_API_KEY=<your-admin-key>
```

### 3. Install dependencies & run

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Access

- **API docs:** http://localhost:8000/docs
- **Admin panel:** http://localhost:8000/admin/dashboard
- **Health check:** http://localhost:8000/health

## Deployment (Railway / Render)

1. Push the `license_server/` folder to a Git repo
2. Connect to Railway or Render
3. Set environment variables from `.env.example`
4. Deploy — it auto-detects the Dockerfile

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/license/activate` | Activate license on a machine |
| POST | `/api/license/verify` | Verify license (heartbeat) |
| POST | `/api/webhook/razorpay` | Razorpay payment webhook |
| GET | `/admin/dashboard` | Admin panel (HTML) |
| GET | `/admin/api/licenses` | List all licenses |
| POST | `/admin/api/license/create` | Create a license manually |
| POST | `/admin/api/license/toggle` | Enable/disable a license |
| POST | `/admin/api/license/reset-hw` | Reset hardware binding |
| GET | `/admin/api/stats` | Dashboard statistics |
