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

## AI log

| Phần | Hỏi gì | Nhận gì | Tự sửa / tự kiểm tra thế nào |
|---|---|---|---|
| CP0 | Docker không chạy trong WSL | Claude chỉ ra chưa bật WSL integration và cách bật | Bật tích hợp, Docker chạy được trong Ubuntu |
| Part 1 | Hướng dẫn CP1 và soạn báo cáo | Claude giải thích lệnh, soạn bản nháp phần phân tích của Part 1 (bảng anti-pattern, bảng so sánh, nhận xét) | Kiểm tra lại log trong ubuntu và đối chiếu với file .md |
