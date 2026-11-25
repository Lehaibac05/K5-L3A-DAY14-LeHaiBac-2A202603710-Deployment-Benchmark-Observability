# Deployment Information

## Public URL

https://agent-production-8f74b50f.up.railway.app

## Platform

Railway: service `agent` (build từ `06-lab-complete/Dockerfile`) và một Redis trong cùng project.

## Test Commands

```bash
BASE=https://agent-production-8f74b50f.up.railway.app   # AGENT_API_KEY lấy từ biến môi trường
curl -sS -o /dev/null -w '%{http_code}
' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}
' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}
' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -sS -o /dev/null -w '%{http_code}
' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'
```

```text
200
200
401
200
```

## Environment Variables Set

Đặt trên Railway, không ghi trong code:

- `AGENT_API_KEY`: chuỗi ngẫu nhiên 32 byte
- `REDIS_URL`: tham chiếu `${{Redis.REDIS_URL}}`
- `ENVIRONMENT=production`
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`

`PORT` không đặt tay: Railway cấp, `Dockerfile` đọc `${PORT:-8000}`.

## Screenshots

- [Dashboard](screenshots/dashboard.png)
- [Service đang chạy](screenshots/running.png)
- [Kết quả test](screenshots/test.png)
