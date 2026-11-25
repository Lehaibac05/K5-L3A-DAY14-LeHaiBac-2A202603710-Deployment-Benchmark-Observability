# Day 14 Lab - Mission Answers

Môi trường: Ubuntu 24.04 trên WSL2, Python 3.12.3 (`os.name` = `posix`), Docker Compose v5.7.0.

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns trong `develop/app.py`

| # | Dòng | Vấn đề | Hậu quả | Cách sửa trong `production/` |
|---|---|---|---|---|
| 1 | 17–18 | Hardcode API key và mật khẩu database | Push lên GitHub là lộ; xoá đi vẫn còn trong lịch sử git | Đọc từ env: `config.py` dòng 27, 32 |
| 2 | 34 | In API key ra log | Ai đọc được log đều lấy được key | Chỉ log độ dài câu hỏi và IP: `app.py` dòng 111–115 |
| 3 | 33, 34, 38 | Dùng `print()` | Không có level, timestamp; khó lọc và cảnh báo | `logging` có cấu trúc: `app.py` dòng 28–31 |
| 4 | 21–22 | Hardcode `DEBUG`, `MAX_TOKENS` | Đổi môi trường phải sửa code | `config.py` dòng 19, 29 |
| 5 | 42–43 | Không có health check | Platform không biết app hỏng để restart | `/health`, `/ready`: `app.py` dòng 135–161 |
| 6 | 51 | Bind `localhost` | Bên ngoài container không gọi vào được | `0.0.0.0`: `config.py` dòng 17 |
| 7 | 52 | Cố định cổng 8000 | Không nhận `PORT` do Railway/Render cấp | `config.py` dòng 18 |
| 8 | 53 | Luôn bật `reload=True` | Thêm tiến trình theo dõi file, không hợp production | Chỉ reload khi `DEBUG=true`: `app.py` dòng 198 |

### Exercise 1.2: Chạy bản develop

Gọi agent:

```bash
curl -i -X POST "http://localhost:8000/ask?question=Hello"
```

```text
INFO:     127.0.0.1:57712 - "POST /ask?question=Hello HTTP/1.1" 200 OK
```

Gọi health check, endpoint này không tồn tại trong bản develop:

```bash
curl -i http://localhost:8000/health
```

```text
INFO:     127.0.0.1:56170 - "GET /health HTTP/1.1" 404 Not Found
```

Log server khi xử lý `/ask`:

```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.
```

**Nhận xét:** agent trả lời được nhưng chưa production-ready. Dòng 34 ghi API key vào log và app không có `/health`.

### Exercise 1.3: So sánh với bản production

Chuẩn bị và chạy:

```bash
cp .env.example .env
sed -i 's/^APP_NAME=.*/APP_NAME="AI Agent"/' .env
set -a; source .env; set +a
OPENAI_API_KEY=mock python app.py    # giá trị giả, app vẫn dùng mock LLM
```

Kết quả:

```bash
curl -i http://localhost:8000/health
curl -i http://localhost:8000/ready
curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{}'
```

```text
INFO:     127.0.0.1:58840 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:43094 - "GET /ready HTTP/1.1" 200 OK
{"time":"2026-11-25 17:08:46,311","level":"INFO","msg":"{"event": "agent_request", "question_length": 5, "client_ip": "127.0.0.1"}"}
{"time":"2026-11-25 17:08:46,442","level":"INFO","msg":"{"event": "agent_response", "response_length": 96}"}
INFO:     127.0.0.1:42048 - "POST /ask HTTP/1.1" 200 OK
INFO:     127.0.0.1:44486 - "POST /ask HTTP/1.1" 422 Unprocessable Entity
```

Log khi nhấn Ctrl+C:

```text
INFO:     Waiting for application shutdown.
{"time":"2026-11-25 17:11:09,515","level":"INFO","msg":"Agent shutting down gracefully — finishing in-flight requests..."}
{"time":"2026-11-25 17:11:09,616","level":"INFO","msg":"Shutdown complete"}
INFO:     Application shutdown complete.
INFO:     Finished server process [3547]
```

Đổi cổng bằng biến môi trường, không sửa code (`PORT=9000 python app.py`):

```text
INFO:     Uvicorn running on http://0.0.0.0:9000 (Press CTRL+C to quit)
INFO:     127.0.0.1:42282 - "GET /health HTTP/1.1" 200 OK
```

| Feature | Develop | Production | Tại sao quan trọng? |
|---|---|---|---|
| Config | Hardcode (dòng 17–22) | Env vars (`config.py` dòng 17–35) | Không lộ secret; một bản code chạy ở mọi môi trường |
| Health check | Không có | `/health` và `/ready` | `/health` giúp platform biết khi nào restart; `/ready` giúp load balancer biết khi nào gửi traffic |
| Logging | `print()`, lộ key | `logging` có cấu trúc, không log secret | Tìm kiếm, cảnh báo được; log không làm lộ dữ liệu |
| Shutdown | Chỉ dựa vào cơ chế mặc định của Uvicorn | Lifespan tắt cờ ready và có bước dọn dẹp (dòng 63–67) | Không cắt ngang request khi deploy lại |
| Host/Port | `localhost:8000` cố định | `0.0.0.0` và `PORT` từ env | Chạy được trong container và trên cloud |
| Input | `question` qua query | JSON body, thiếu `question` trả 422 (dòng 104–108) | Query string thường bị ghi vào access log và giới hạn độ dài |

**Điểm bản production vẫn chưa tốt (đọc từ code):**

1. `app.py` và `config.py` không gọi `load_dotenv()` dù có `python-dotenv` trong `requirements.txt`, nên phải tự nạp `.env` vào shell.
2. Khi thiếu `OPENAI_API_KEY`, `config.py` dòng 45 gọi `logging.warning()` trước `logging.basicConfig()` ở `app.py` dòng 28. Root logger đã có handler nên cấu hình JSON bị bỏ qua và log INFO không hiện.
3. `.env.example` có `APP_NAME=AI Agent` không ngoặc kép, nên `source .env` báo `Agent: command not found`.
4. Log ghép JSON vào chuỗi trong trường `msg` mà không escape dấu ngoặc kép, nên các dòng log này không phải JSON hợp lệ.

### Checkpoint 1

- **Hardcode secret nguy hiểm vì** key nằm vĩnh viễn trong lịch sử git; khi lộ phải thu hồi và tạo key mới.
- **Biến môi trường** tách cấu hình khỏi code, đổi giá trị không cần build lại.
- **Health check** cho platform biết app còn sống và sẵn sàng hay chưa.
- **Graceful shutdown** là ngừng nhận request mới, xử lý xong request đang chạy rồi mới đóng kết nối và thoát.

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (dòng 8), bản Python đầy đủ.
2. **Working directory:** `/app` (dòng 11).
3. **Tại sao COPY `requirements.txt` trước (dòng 14) rồi mới COPY code (dòng 20)?** Docker cache theo layer, một layer đổi thì các layer sau phải build lại. Khi chỉ sửa code, `requirements.txt` không đổi nên bước `pip install` (dòng 17) dùng lại cache, build nhanh hơn. Nếu đặt `COPY . .` lên trước, mỗi lần sửa code đều phải cài lại thư viện.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định, bị thay thế khi thêm lệnh vào cuối `docker run` (ví dụ `docker run my-agent:develop whoami`). `ENTRYPOINT` là lệnh cố định, phần thêm vào trở thành tham số của nó (chỉ đổi được bằng `--entrypoint`). Dockerfile này dùng `CMD ["python", "app.py"]` (dòng 30).

### Exercise 2.2: Build và run

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --rm --name agent-dev -p 8000:8000 my-agent:develop
curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
curl -i http://localhost:8000/health
docker exec agent-dev whoami
```

`POST /ask`:

```text
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:29:49 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

`GET /health`:

```text
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:29:59 GMT
server: uvicorn
content-length: 54
content-type: application/json

{"status":"ok","uptime_seconds":38.1,"container":true}
```

`docker exec agent-dev whoami`:

```text
root
```

Log server trong container:

```text
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     172.17.0.1:43246 - "POST /ask?question=What%20is%20Docker HTTP/1.1" 200 OK
INFO:     172.17.0.1:33568 - "GET /health HTTP/1.1" 200 OK
```

### Exercise 2.3: Image size comparison

```bash
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent
```

```text
IMAGE               ID             DISK USAGE   CONTENT SIZE
my-agent:advanced   17c6419c6c0a        240MB         57.4MB
my-agent:develop    174e3690cb51       1.67GB          426MB
```

- Develop: **1668 MB** (cột DISK USAGE; `docker image inspect` báo 1 667 796 586 byte)
- Production: **240 MB** (cột DISK USAGE; `docker image inspect` báo 239 815 469 byte)
- Difference: (1668 − 240) / 1668 × 100 = **giảm 85,6%**

**Stage 1 `builder` (dòng 16–29)** cài `gcc`, `libpq-dev` và thư viện Python vào `/root/.local`.

**Stage 2 `runtime` (dòng 36–72)** bắt đầu lại từ `python:3.11-slim`, chỉ copy thư viện đã cài (dòng 45) và code, rồi chạy bằng `appuser` (dòng 58).

**Tại sao nhỏ hơn:**

1. Base image là `slim` thay vì bản đầy đủ. Riêng mức chênh này đã là lý do lớn, vì develop cũng chỉ cài hai thư viện nhỏ.
2. `gcc`, `libpq-dev` chỉ nằm ở stage `builder`, không có trong image cuối.

Ngoài kích thước, bản production an toàn hơn vì không chạy bằng root (`Config.User` của image là `appuser`, bản develop để trống nên là root) và có `HEALTHCHECK`.

### Exercise 2.4: Docker Compose stack

```mermaid
flowchart LR
  C[Client] -->|":8088 → 80"| N[nginx]
  subgraph internal [network internal]
    N -->|"agent:8000"| A[agent FastAPI]
    A -.->|"redis:6379"| R[(redis)]
    A -.->|"qdrant:6333"| Q[(qdrant)]
  end
```

**Services được start:** `agent`, `redis`, `qdrant`, `nginx`.

- `agent` đợi `redis` và `qdrant` healthy rồi mới chạy (`depends_on` + `condition: service_healthy`).
- Các service gọi nhau bằng tên service (DNS nội bộ của Docker) trong network `internal`.
- Chỉ `nginx` mở cổng ra ngoài; agent, Redis và Qdrant không truy cập trực tiếp từ máy host.
- Nét đứt: agent được cấp `REDIS_URL` và `QDRANT_URL` nhưng `main.py` hiện chưa gọi hai service này.

**Lỗi gặp phải:** cổng 80 trên Windows đã bị IIS (W3SVC) sử dụng nên Nginx không publish được (`ports are not available: exposing port TCP 0.0.0.0:80`). Cách xử lý là file Compose override ánh xạ `8088:80`; Nginx vẫn lắng nghe cổng 80 bên trong container.

```yaml
# ~/cp2-ports.yml (ngoài repo)
services:
  nginx:
    ports: !override
      - "8088:80"
```

```bash
touch .env.local
docker compose -p k5-day14-docker up -d --build     # lỗi cổng 80
docker compose -p k5-day14-docker -f docker-compose.yml -f ~/cp2-ports.yml up -d
docker compose -p k5-day14-docker ps
```

Output `up -d` (lần chạy với file override):

```text
time="2026-11-25T21:32:15+07:00" level=warning msg="/home/haibac/day14/02-docker/production/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
 Network k5-day14-docker_internal Creating 
 Network k5-day14-docker_internal Creating 
 Network k5-day14-docker_internal Created 
 Network k5-day14-docker_internal Created 
 Container k5-day14-docker-qdrant-1 Creating 
 Container k5-day14-docker-redis-1 Creating 
 Container k5-day14-docker-redis-1 Created 
 Container k5-day14-docker-qdrant-1 Created 
 Container k5-day14-docker-agent-1 Creating 
 Container k5-day14-docker-agent-1 Created 
 Container k5-day14-docker-nginx-1 Creating 
 Container k5-day14-docker-nginx-1 Created 
 Container k5-day14-docker-qdrant-1 Starting 
 Container k5-day14-docker-redis-1 Starting 
 Container k5-day14-docker-qdrant-1 Started 
 Container k5-day14-docker-qdrant-1 Waiting 
 Container k5-day14-docker-redis-1 Started 
 Container k5-day14-docker-redis-1 Waiting 
 Container k5-day14-docker-qdrant-1 Healthy 
 Container k5-day14-docker-redis-1 Healthy 
 Container k5-day14-docker-agent-1 Starting 
 Container k5-day14-docker-agent-1 Started 
 Container k5-day14-docker-nginx-1 Starting 
 Container k5-day14-docker-nginx-1 Started
```

Output `ps`, cả 4 service đều `Up`, chỉ nginx publish cổng:

```text
NAME                       IMAGE                   COMMAND                  SERVICE   CREATED          STATUS                    PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   "uvicorn main:app --…"   agent     23 seconds ago   Up 10 seconds (healthy)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            "/docker-entrypoint.…"   nginx     22 seconds ago   Up 9 seconds              0.0.0.0:8088->80/tcp, [::]:8088->80/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    "./entrypoint.sh"        qdrant    23 seconds ago   Up 22 seconds (healthy)   6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          "docker-entrypoint.s…"   redis     23 seconds ago   Up 21 seconds (healthy)   6379/tcp
```

Test qua Nginx, và gọi thẳng agent ở cổng 8000 (không được mở ra ngoài):

```bash
curl -i http://localhost:8088/health
curl -i -X POST http://localhost:8088/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
curl -i http://localhost:8000/health
```

`GET /health` qua Nginx:

```text
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 14:32:49 GMT
Content-Type: application/json
Content-Length: 96
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":17.7,"version":"2.0.0","timestamp":"2026-11-25T14:32:49.625055"}
```

`POST /ask` qua Nginx:

```text
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 14:32:49 GMT
Content-Type: application/json
Content-Length: 95
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Gọi thẳng agent ở cổng 8000, kết nối bị từ chối vì chỉ Nginx mở cổng ra ngoài:

```text
curl: (7) Failed to connect to localhost port 8000 after 17 ms: Couldn't connect to server
```

### Checkpoint 2

- **Multi-stage** giảm dung lượng bằng cách bỏ công cụ build khỏi image chạy thật.
- **Compose** khai báo các service, network, volume và thứ tự khởi động trong một file.
- **Debug container:** `docker logs` xem log, `docker exec` chạy lệnh bên trong container đang chạy.

## Part 4: API Security

Trong các lệnh dưới đây: `B=http://localhost:8000`, `J='Content-Type: application/json'`, `D='{"question":"Hello"}'`. Key, mật khẩu và token đã che.

### Exercise 4.1: API key (`04-api-gateway/develop/app.py`)

- **Key được kiểm tra ở đâu:** `verify_api_key()` (dòng 39), gắn vào `/ask` bằng `Depends` (dòng 70). `/` và `/health` là public.
- **Sai key:** trả 403; thiếu key trả 401.
- **Rotate key:** đổi biến `AGENT_API_KEY` rồi restart, vì key chỉ đọc một lần lúc khởi động (dòng 35). App chỉ nhận một key nên key cũ mất hiệu lực ngay; muốn không gián đoạn thì phải tạm chấp nhận cả hai key.
- **Điểm yếu:** có key mặc định trong code (dòng 35), in key ra log (dòng 91–92), so sánh bằng `!=` (dòng 49) thay vì `secrets.compare_digest`.

```bash
AGENT_API_KEY=*** python app.py
curl -i $B/ask -X POST -H "$J" -d "$D"
curl -i $B/ask -X POST -H "$J" -H "X-API-Key: wrong" -d "$D"
curl -i $B/ask -X POST -H "$J" -H "X-API-Key: ***" -d "$D"
```

Thiếu key:

```text
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 14:41:17 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Sai key:

```text
HTTP/1.1 403 Forbidden
date: Wed, 25 Nov 2026 14:41:17 GMT
server: uvicorn
content-length: 29
content-type: application/json

{"detail":"Invalid API key."}
```

Đúng key (dòng cuối bị terminal cắt):

```text
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 14:41:17 GMT
server: uvicorn
content-length: 122
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạ…} 
```

### Exercise 4.2: JWT (`04-api-gateway/production/auth.py`)

1. Client gửi username/password tới `POST /auth/token`; `authenticate_user()` (dòng 70–75) kiểm tra.
2. `create_token()` (dòng 35–43) ký token HS256 chứa `sub`, `role`, `iat`, `exp` (60 phút).
3. Client gửi `Authorization: Bearer <token>`; `verify_token()` (dòng 46–67) kiểm tra chữ ký và hạn, không cần tra database. Thiếu hoặc hết hạn trả 401, token sai trả 403.

JWT được ký chứ không mã hóa: ai có token cũng đọc được payload, nên không được để secret trong đó.

```bash
JWT_SECRET=$(openssl rand -hex 32) python app.py
curl -i $B/ask -X POST -H "$J" -d "$D"
TOKEN=$(curl -s $B/auth/token -X POST -H "$J" \
  -d '{"username":"student","password":"***"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -i $B/ask -X POST -H "Authorization: Bearer $TOKEN" -H "$J" -d '{"question":"Explain JWT"}'
```

Không có token:

```text
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 14:42:21 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 76
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

Có token:

```text
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 14:42:21 GMT
server: uvicorn
content-length: 215
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}
```

### Exercise 4.3: Rate limiting (`rate_limiter.py`)

- **Thuật toán:** sliding window. Mỗi user có một `deque` timestamp; bỏ các timestamp cũ hơn 60 giây rồi đếm phần còn lại (dòng 38–45).
- **Limit:** 10 request/phút cho user (dòng 86).
- **Admin:** không bỏ qua hoàn toàn mà dùng limiter 100 request/phút (dòng 87), chọn theo `role` ở `app.py` dòng 141.
- **Hạn chế:** lưu trong RAM nên mất khi restart; chạy nhiều instance thì mỗi instance đếm riêng.

```bash
for i in {1..20}; do
  curl -s -o /dev/null -w "Request $i: %{http_code}\n" $B/ask -X POST \
    -H "Authorization: Bearer $TOKEN" -H "$J" -d "{\"question\":\"Test $i\"}"
done
curl -i $B/ask -X POST -H "Authorization: Bearer $TOKEN" -H "$J" -d "$D"
```

```text
Request 1: 200
Request 2: 200
Request 3: 200
Request 4: 200
Request 5: 200
Request 6: 200
Request 7: 200
Request 8: 200
Request 9: 200
Request 10: 200
Request 11: 429
Request 12: 429
Request 13: 429
Request 14: 429
Request 15: 429
Request 16: 429
Request 17: 429
Request 18: 429
Request 19: 429
Request 20: 429
```

Lệnh `curl -i` ngay sau vòng lặp (dòng cuối bị terminal cắt):

```text
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 14:43:47 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795617888
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_afte…}}
```

### Exercise 4.4: Cost guard

`cost_guard.py` có sẵn giới hạn $1/ngày mỗi user (402) và $10/ngày toàn hệ thống (503), lưu trong RAM. Bài yêu cầu $10/tháng mỗi user, lưu trong Redis: `04-api-gateway/production/budget_redis.py`.

```python
def check_budget(user_id: str, estimated_cost: float) -> bool:
    if not 0 <= estimated_cost < float("inf"):
        raise ValueError("estimated_cost must be finite and non-negative")
    key = f"budget:{user_id}:{datetime.now(timezone.utc):%Y-%m}"
    # Cộng trước rồi mới so sánh: hai request song song không thể cùng lọt qua.
    with r.pipeline() as p:
        p.incrbyfloat(key, estimated_cost)
        p.expire(key, 32 * 24 * 3600)
        total = p.execute()[0]
    if total > MONTHLY_BUDGET_USD:
        r.incrbyfloat(key, -estimated_cost)  # hoàn lại vì request bị chặn
        return False
    return True
```

- **Reset đầu tháng:** key chứa năm-tháng (UTC), sang tháng mới là key mới. TTL 32 ngày chỉ để dọn key cũ.
- **Chạy song song:** nếu đọc số dư rồi mới cộng, hai request cùng lúc có thể cùng lọt qua. Ở đây cộng trước bằng `INCRBYFLOAT` (atomic), vượt thì hoàn lại.
- **Đánh đổi:** khoản đang chờ hoàn có thể làm một request song song bị từ chối oan.
- **Giới hạn:** hàm chạy độc lập, chưa nối vào `app.py`; chi phí là số ước tính.

```bash
docker run -d --rm --name cp3-redis -p 6379:6379 redis:7-alpine
python budget_redis.py
docker stop cp3-redis
```

```text
(.venv) haibac@LeHaiBac:~/day14/04-api-gateway/production$ cd ~/day14 && source .venv/bin/activate && cd 04-api-gateway/production
cp /mnt/c/Users/ADMIN/OneDrive/M*t*nh/LLM/Lab_day14/K5-L3A-DAY14-*/04-api-gateway/production/budget_redis.py .
docker run -d --rm --name cp3-redis -p 6379:6379 redis:7-alpine
sleep 2
python budget_redis.py
docker stop cp3-redis
1a316575cdb6f407dbcff990c2e0c504b84b51bafca60e638b6e83d19b693490
[(6, True), (3, True), (2, False), (1, True)] spent = 10.0 ttl = 2764800
cp3-redis
```

**Vấn đề có sẵn trong code mẫu:**

1. `app.py` dòng 160 gán `budget_remaining_usd` bằng `usage.total_cost_usd`, tức số tiền đã dùng. Output ở 4.2 cho thấy `2.1e-05` ngay sau request đầu tiên, trong khi ngân sách còn gần $1.
2. `cost_guard.py`: `_global_cost` chỉ cộng dồn (dòng 104), không reset sang ngày mới; `_global_today` (dòng 50) không được dùng. Chạm $10 thì trả 503 tới khi restart.

### Checkpoint 4

- **Rate limit bảo vệ tốc độ:** chặn gọi dồn dập, nhưng không chặn được vài request rất đắt.
- **Cost guard bảo vệ tiền:** chặn khi hết ngân sách, nhưng không chặn được hàng loạt request rẻ làm quá tải server. Vì vậy cần cả hai.
- **Authentication** xác định người gọi, nhờ đó rate limit và cost guard tính được theo từng user.

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

| | `/health` (liveness) | `/ready` (readiness) |
|---|---|---|
| Câu hỏi | Tiến trình còn sống không? | Nhận traffic được chưa? |
| Khi lỗi | Platform restart container | Load balancer ngừng gửi request, không restart |
| Redis chết | Vẫn 200: restart agent không cứu được Redis | 503 |

**Bản develop** chỉ xem cờ `_is_ready`, không kiểm tra Redis. Log server khi gọi hai endpoint:

```bash
python app.py
curl -i http://localhost:8000/health
curl -i http://localhost:8000/ready
```

```text
INFO:     127.0.0.1:48994 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:48998 - "GET /ready HTTP/1.1" 200 OK
```

**Bản production** ping Redis (`production/app.py`: `health()` dòng 165, `ready()` dòng 181). Tắt Redis rồi gọi thẳng một instance, không qua Nginx:

```bash
DC="docker compose -p k5-day14-scaling"
$DC stop redis
for p in health ready; do
  docker exec k5-day14-scaling-agent-2 python -c "import http.client as h; c=h.HTTPConnection('localhost',8000); c.request('GET','/$p'); r=c.getresponse(); print('$p', r.status, r.read().decode())"
done
$DC start redis
```

```text
health 200 {"status":"degraded","instance_id":"instance-f083d9","uptime_seconds":79.0,"storage":"redis","redis_connected":false}
ready 503 {"detail":"Redis not available"}
```

### Exercise 5.2: Graceful shutdown

Khi nhận SIGTERM, Uvicorn ngừng nhận kết nối mới, đợi request đang chạy xong, chạy phần shutdown của `lifespan` rồi thoát. `handle_sigterm` chỉ ghi log, và log sau cùng vì Uvicorn dùng signal handler của nó trong lúc chạy.

Test: gửi hai request (mỗi request khoảng 3 giây), 0,5 giây sau gửi SIGTERM.

```bash
python app.py > ~/cp4.log 2>&1 & PID=$!
sleep 4
curl -s -w ' [1: %{http_code}]\n' -X POST "http://localhost:8000/ask?question=one" & C1=$!
curl -s -w ' [2: %{http_code}]\n' -X POST "http://localhost:8000/ask?question=two" & C2=$!
sleep 0.5; kill -TERM $PID
wait $C1; wait $C2; wait $PID; echo "exit $?"
cat ~/cp4.log
```

Trước khi sửa (`async def ask_agent`):

```text
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."} [1: 200]
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."} [2: 200]
exit 0
2026-11-25 22:02:10,446 INFO ✅ Agent is ready!
INFO:     Shutting down
INFO:     127.0.0.1:48700 - "POST /ask?question=one HTTP/1.1" 200 OK
INFO:     127.0.0.1:48706 - "POST /ask?question=two HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-25 22:02:19,830 INFO 🔄 Graceful shutdown initiated...
2026-11-25 22:02:19,830 INFO ✅ Shutdown complete
INFO:     Finished server process [7885]
2026-11-25 22:02:19,830 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

Sau khi sửa dòng 94 thành `def ask_agent`:

```text
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."} [2: 200]
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."} [1: 200]
exit 0
2026-11-25 22:05:52,489 INFO ✅ Agent is ready!
INFO:     Shutting down
INFO:     Waiting for connections to close. (CTRL+C to force quit)
INFO:     127.0.0.1:44694 - "POST /ask?question=two HTTP/1.1" 200 OK
INFO:     127.0.0.1:44696 - "POST /ask?question=one HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-25 22:05:59,131 INFO 🔄 Graceful shutdown initiated...
2026-11-25 22:05:59,131 INFO ✅ Shutdown complete
INFO:     Finished server process [7951]
2026-11-25 22:05:59,132 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

(Cả hai log đã lược vài dòng khởi động và dòng kết thúc của Uvicorn.)

- Cả hai lần, hai request đều xong và tiến trình thoát với mã 0.
- Từ lúc ready đến lúc shutdown: **9,4 giây** trước, **6,6 giây** sau, chênh khoảng 2,7 giây, gần bằng một request. Điều này phù hợp với việc bản `async def` chạy hai request lần lượt, còn bản `def` chạy song song.
- **Lý do sửa:** `time.sleep()` trong `async def` chặn event loop, nên trong lúc đó app không trả lời được cả `/health`. Với `def`, FastAPI chạy hàm trong threadpool.

### Exercise 5.3: Stateless design (`production/app.py`)

Bản gốc có ba vấn đề, thấy được khi đọc code:

1. Không kết nối được Redis lúc khởi động thì chuyển sang lưu trong RAM (`_memory_store`). Instance đó vẫn báo ready nhưng các instance khác không thấy session của nó.
2. History được đọc ra, sửa rồi ghi đè cả khối, nên hai request song song cùng session có thể làm mất message.
3. `chat()` là `async def` nhưng gọi hàm chặn.

Đã sửa:

| Vấn đề | Cách sửa |
|---|---|
| State trong RAM | Bỏ hẳn `_memory_store`; mọi session nằm trong Redis, timeout 2 giây (dòng 37–38) |
| Ghi đè history | `append_to_history()` (dòng 60–71) dùng `RPUSH`, `LTRIM` (giữ 20 message) và `EXPIRE` (1 giờ) trong một pipeline |
| Chặn event loop | `def chat` (dòng 110) |
| `turn` đếm dư 1 | Bỏ `+ 1`, vì history đã gồm câu hỏi hiện tại |

```bash
grep -c "USE_REDIS" production/app.py
```

```text
0
```

**Vì sao state trong RAM hỏng khi scale:** RAM của mỗi instance là riêng, nên request sang instance khác hoặc sau khi restart sẽ mất history. Đánh đổi: Redis trở thành điểm hỏng duy nhất của stack này.

### Exercise 5.4: Load balancing

```bash
touch .env.local
DC="docker compose -p k5-day14-scaling"
$DC up -d --build --scale agent=3
$DC ps
for i in {1..10}; do
  curl -s localhost:8080/chat -X POST -H 'Content-Type: application/json' \
    -d "{\"question\":\"Request $i\"}" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["served_by"], d["storage"])'
done
$DC logs agent | grep "POST /chat" | cut -d'|' -f1 | sort | uniq -c
```

```text
NAME                       IMAGE                    COMMAND                  SERVICE   CREATED          STATUS                    PORTS
k5-day14-scaling-agent-1   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     30 seconds ago   Up 18 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     30 seconds ago   Up 18 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     30 seconds ago   Up 18 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   nginx:alpine             "/docker-entrypoint.…"   nginx     30 seconds ago   Up 17 seconds             0.0.0.0:8080->80/tcp, [::]:8080->80/tcp
k5-day14-scaling-redis-1   redis:7-alpine           "docker-entrypoint.s…"   redis     30 seconds ago   Up 29 seconds (healthy)   6379/tcp
```

```text
instance-3c95ba redis
instance-b46411 redis
instance-f083d9 redis
instance-3c95ba redis
instance-b46411 redis
instance-f083d9 redis
instance-3c95ba redis
instance-b46411 redis
instance-f083d9 redis
instance-3c95ba redis
      4 agent-1  
      3 agent-2  
      3 agent-3  
```

Nginx chia 10 request theo round-robin: 4 / 3 / 3. Chỉ Nginx mở cổng ra ngoài (8080).

### Exercise 5.5: Test stateless

`python3 test_stateless.py` (lược phần câu hỏi và câu trả lời):

```text
Session ID: 892ba09a-87d1-4751-a13f-51bbd7db45d1

Request 1: [instance-b46411]
Request 2: [instance-f083d9]
Request 3: [instance-3c95ba]
Request 4: [instance-b46411]
Request 5: [instance-f083d9]

Total requests: 5
Instances used: {'instance-3c95ba', 'instance-f083d9', 'instance-b46411'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10

✅ Session history preserved across all instances via Redis!
```

Một session đi qua 3 instance mà vẫn đủ 10 message (5 câu hỏi, 5 câu trả lời).

Script không tự tắt instance nào, nên thử thêm: tạo session, tắt `agent-1`, gửi tiếp 6 request cùng session.

```bash
S=$(curl -s localhost:8080/chat -X POST -H 'Content-Type: application/json' -d '{"question":"Before"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["session_id"])')
docker stop k5-day14-scaling-agent-1
for i in {1..6}; do
  curl -s -o /dev/null -w "After $i: %{http_code} %{time_total}s\n" localhost:8080/chat -X POST \
    -H 'Content-Type: application/json' -d "{\"question\":\"After $i\",\"session_id\":\"$S\"}"
done
curl -s localhost:8080/chat/$S/history | python3 -c 'import sys,json; print("messages", json.load(sys.stdin)["count"])'
```

```text
After 1: 200 0.148298s
After 2: 200 2.047512s
After 3: 200 0.134497s
After 4: 200 0.138186s
After 5: 200 0.120040s
After 6: 200 0.116377s
messages 14
```

- Cả 6 request trả 200 và session còn đủ 14 message (7 lượt × 2).
- Request thứ hai mất 2,05 giây, khớp với `proxy_connect_timeout 2s` (`nginx.conf` dòng 25): Nginx thử instance đã tắt, hết 2 giây thì chuyển sang instance khác. Nếu không đặt, mặc định của Nginx là 60 giây.

### Checkpoint 5

- **Liveness** quyết định restart, **readiness** quyết định có gửi traffic hay không.
- **Graceful shutdown** là ngừng nhận request mới và xử lý xong request đang chạy trước khi thoát.
- **Stateless** là đưa state ra Redis để instance nào cũng phục vụ được, và mất một instance không mất dữ liệu.

## Part 6: Final Project

Code nằm trong `06-lab-complete/`. Chạy script chấm trong WSL Ubuntu, có Docker:

```bash
python check_production_ready.py
```

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 41/41 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Kết quả đo trong cùng lần chạy:

| Kiểm tra | Kết quả |
|---|---|
| Docker image | 238 MB, build 23 giây |
| Rate limit (`RATE_LIMIT_PER_MINUTE=5`) | 429 sau 5 request thành công; restart agent vẫn 429 |
| Cost guard (ngân sách 0,000001 USD) | 402 ở request thứ 1 |
| Log | 12 dòng, đều là JSON hợp lệ |
| SIGTERM khi đang có request | request vẫn 200, exit code 0 |
| `docker stop` | exit code 0, 1,0 giây |

Cost guard chặn ngay request thứ 1 vì các lượt test trước dùng chung Redis và đã cộng chi phí vào cùng ngày.

### Thử tay với Docker Compose

```bash
echo "AGENT_API_KEY=dev-key" > .env
docker compose -p k5-day14-final up -d --build
docker compose -p k5-day14-final ps
ask() { curl -s -w ' [%{http_code}]
' -X POST localhost:8000/ask -H 'Content-Type: application/json' "$@"; }
curl -s -w ' [%{http_code}]
' localhost:8000/ready
ask -d '{"question":"Hello"}'
ask -H 'X-API-Key: dev-key' -d '{"question":"What is docker?"}'
ask -H 'X-API-Key: dev-key' -d '{"question":"   "}'
docker compose -p k5-day14-final stop redis
curl -s -w ' [%{http_code}]
' localhost:8000/health
curl -s -w ' [%{http_code}]
' localhost:8000/ready
docker compose -p k5-day14-final down -v
```

```text
NAME                     IMAGE                  COMMAND                  SERVICE   CREATED          STATUS                    PORTS
k5-day14-final-agent-1   k5-day14-final-agent   "sh -c 'exec uvicorn…"   agent     16 seconds ago   Up 10 seconds (healthy)   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
k5-day14-final-redis-1   redis:7-alpine         "docker-entrypoint.s…"   redis     16 seconds ago   Up 16 seconds (healthy)   6379/tcp
{"status":"ready"} [200]
{"detail":"Invalid or missing API key"} [401]
{"question":"What is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","cost_usd":1.1999999999999999e-05} [200]
{"detail":[{"type":"string_too_short","loc":["body","question"],"msg":"String should have at least 1 character","input":"   ","ctx":{"min_length":1}}]} [422]
{"status":"ok"} [200]
{"detail":"Redis not available"} [503]
```

(Đã lược log build và các dòng trạng thái của Compose.) Hai dòng cuối là sau khi tắt Redis.

### Cách làm

| Phần | Cách làm và lý do |
|---|---|
| `POST /ask` | Thứ tự: API key → rate limit → ngân sách → LLM → ghi chi phí. Dùng `def` để lời gọi chặn chạy trong threadpool |
| `auth.py` | So sánh bằng `compare_digest`. Chưa đặt `AGENT_API_KEY` thì từ chối tất cả |
| `rate_limiter.py` | Sorted set trong Redis, `ZADD` trước rồi `ZCARD` trong một `MULTI/EXEC`, nên hai request song song không thể cùng lọt qua. Key được băm SHA-256 |
| `cost_guard.py` | Cộng chi phí bằng `INCRBYFLOAT` vào key theo ngày (UTC), sang ngày mới là key mới |
| Lỗi input | Pydantic trả 422 khi câu hỏi rỗng, toàn khoảng trắng hoặc quá 2000 ký tự. Lỗi Redis trả 503, không lộ stack trace |
| Shutdown | Uvicorn xử lý SIGTERM, `lifespan` đóng Redis. `exec` trong `CMD` để uvicorn là PID 1 và nhận được tín hiệu |

**Vì sao Redis chết mà `/health` vẫn 200 còn `/ready` là 503:** `/health` quyết định restart, mà restart agent không cứu được Redis. `/ready` quyết định nhận traffic, và agent thiếu Redis thì không kiểm tra được rate limit và ngân sách.

**Vì sao state phải ở Redis:** container chạy 2 worker, mỗi worker có RAM riêng. Đếm trong RAM thì giới hạn bị nhân đôi và mất khi restart.

**Giới hạn:**

- Chi phí được ghi sau khi gọi LLM, nên nhiều request song song có thể vượt ngân sách một chút.
- Token được ước tính theo số ký tự (4 ký tự một token).
- Ngân sách tính chung cho cả agent, không tách theo user.
- Redis là điểm hỏng duy nhất: mất Redis thì `/ask` trả 503.

## AI log

| Phần | Hỏi gì | Nhận gì | Tự sửa / tự kiểm tra thế nào |
|---|---|---|---|
| CP0 | Docker không chạy trong WSL | Claude chỉ ra chưa bật WSL integration và cách bật | Bật tích hợp, Docker chạy được trong Ubuntu |
| Part 1 | Hướng dẫn CP1 và soạn báo cáo | Claude giải thích lệnh, soạn bản nháp phần phân tích của Part 1 (bảng anti-pattern, bảng so sánh, nhận xét) | Kiểm tra lại log trong ubuntu và đối chiếu với file .md |
| Part 2 | Hướng dẫn CP2, lỗi cổng 80, soạn báo cáo | Claude tìm ra IIS chiếm cổng 80, đưa file override `8088:80`; chạy `docker images` để lấy kích thước hai image đã build; soạn bản nháp phần phân tích | [TỰ GHI: đã đối chiếu và sửa gì] |
| Part 4 | Hướng dẫn CP3, soạn báo cáo | Claude chạy thử trước trên bản sao tạm, đưa lệnh curl, viết `budget_redis.py`, soạn bản nháp Part 4 từ output tôi đã chạy | [ đã đối chiếu và log] |
| Part 5 | Hướng dẫn CP4, sửa code 5.3, soạn báo cáo | Claude chạy thử trên bản sao tạm, chỉ ra các vấn đề của code mẫu, sửa `production/app.py` và `nginx.conf`, soạn bản nháp Part 5 từ output tôi đã chạy | Tự sửa `develop/app.py` dòng 94 và chạy trước/sau; kết quả trước khi sửa khác dự đoán của Claude (cả hai request đều 200). [ đã đối chiếu và thêm log] |
| Part 6 | Hướng dẫn CP5, ghi code vào repo, soạn báo cáo | Claude viết code cho các TODO (11 file trong `06-lab-complete/`), chạy script chấm trên bản sao, soạn bản nháp Part 6 từ output tôi đã chạy | Tự chạy script chấm trong WSL: PASS 12/12. [ đã đọc, kiểm tra, sửa log] |
