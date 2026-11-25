# Benchmark & Observability Report — Day 14

**Họ tên:** LeHaiBac (2A202603710)
**Ngày chạy:** 2026-11-25
**Môi trường:** AMD Ryzen 7 5700U, RAM 15,4 GB, Windows 11; chạy trong WSL2 Ubuntu 24.04 (16 CPU, 7,4 GB RAM), Docker Desktop. Load test và agent chạy trên cùng máy.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Ở 10–50 luồng p95 đo được 221–276 ms, nên 500 ms còn dư nhưng vẫn phát hiện được quá tải |
| Error rate `/ask` | < 2 % | Mock LLM lỗi ngẫu nhiên khoảng 1%; 2% chừa chỗ cho mức nền này |
| Accuracy trên golden dataset | ≥ 85 % | Dưới mức 91,3% của v2 ban đầu (sai thêm 2 câu là fail), cũng là ngưỡng của job CI |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4,13 | 194,6 | 222,2 | 1690,0 | 0% | PASS |
| 10 | 43,19 | 190,1 | 221,1 | 1693,1 | 1,67% | PASS |
| 50 | 108,49 | 195,9 | 275,6 | 1693,1 | 0,33% | PASS |
| 100 | 85,74 | 356,6 | 2795,6 | 3003,5 | 0,67% | FAIL (p95) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- **Từ 1 lên 10** gần tuyến tính: RPS tăng 10,5 lần, p50 không đổi. Thời gian chủ yếu là chờ LLM (`await`), nên nhiều request chờ cùng lúc mà không cản nhau.
- **Từ 10 lên 50** RPS chỉ tăng 2,5 lần. **Từ 50 lên 100** RPS giảm từ 108 xuống 86, p95 tăng từ 276 lên 2796 ms: hệ thống đã bão hoà.
- Nguyên nhân có thể là agent chạy một process và dùng chung máy với load test, nên request phải xếp hàng. Tôi chưa đo CPU để xác nhận.
- Mỗi mức chỉ 300 request: ở mức 50 và 100 lượt test kéo dài khoảng 3 giây, nên vài request chậm 1,5 giây cũng kéo RPS xuống đáng kể.
- Ở 1 luồng, p99 đã là 1690 ms vì 3% request chậm của mock. p99 ở ba mức đầu gần như bằng nhau, nên không phải do tải.

Nguồn: `reports/load_v2_c*.json`, mỗi mức 300 request.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 193,0 | 220,9 | 229,2 |
| 0.03 (mặc định) | 228,2 | 231,1 | 1688,1 |
| 0.1 | 333,2 | 1695,8 | 1714,7 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **p99 nhạy nhất:** chỉ 3% request chậm đã đẩy p99 từ 229 lên 1688 ms (7,4 lần), trong khi avg tăng 18% và p95 gần như không đổi.
- p95 chỉ phản ứng khi hơn 5% request chậm: ở 10%, p95 lên 1696 ms.
- **Không dùng average** vì nó trộn nhóm chậm vào số đông: ở 10% chậm, avg mới 333 ms, không phản ánh một phần mười người dùng phải chờ khoảng 1,7 giây.
- SLO p95 < 500 ms bỏ sót trường hợp 3%, nên cần theo dõi thêm p99.

Nguồn: `reports/load_v2_slow_*.json`, 300 request, concurrency 20.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4,3% (1/23) | 91,3% (21/23) | 100% (23/23) |
| Avg tokens / câu | 57,6 | 108,8 | 113,3 |
| Tổng cost (USD) | 0,000411 | 0,000758 | 0,000788 |
| Cost / câu đúng (USD) | 0,00041115 | 0,00003607 | 0,00003425 |
| Quality gate | FAIL (ngưỡng 80%) | PASS (ngưỡng 80%) | PASS (ngưỡng 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | token, hết hạn, chữ ký | Thêm tài liệu JWT vào `KNOWLEDGE_BASE` |
| scaling-03 | cpu, memory, custom metrics | Thêm tài liệu Kubernetes HPA vào `KNOWLEDGE_BASE` |

Hai câu này không khớp tài liệu nào nên agent trả lời chung chung. Không sửa golden dataset.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** v2 đúng 21/23 so với 1/23 của v1.
- **Chi phí:** v2 tốn token hơn 89% và cost hơn 84% vì prompt kèm tài liệu. Nhưng cost / câu đúng **rẻ hơn 11,4 lần**. Cost / câu thì ngược lại, cho thấy v1 rẻ hơn, vì nó tính cả câu trả lời sai.
- **Latency:** p50 tăng từ 174 lên 192 ms (khoảng 17 ms, gần với bước retrieval 20 ms). 23 câu là mẫu nhỏ, nên chỉ để tham khảo.
- Sửa KB tăng cost 4% nhưng cost / câu đúng giảm 5%.

**Chặn merge bằng exit code:** `run_eval.py` trả exit code 1 khi accuracy dưới ngưỡng hoặc có regression so với `--baseline`. Job [`.github/workflows/eval.yml`](.github/workflows/eval.yml) chạy eval trên mỗi pull request với ngưỡng 85%; để chặn merge phải đặt job là required status check. Job hiện chỉ kiểm tra accuracy, chưa truyền `--baseline`, và chưa chạy thật trên GitHub.

Nguồn: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [Dashboard Grafana](screenshots/grafana-dashboard.png)
- [Trace chậm trong Jaeger](screenshots/jaeger-slow-trace.png)
- [Trace lỗi trong Jaeger](screenshots/jaeger-error-trace.png)
- [Prometheus Alerts: 3 alert đang firing](screenshots/prometheus-alert-firing.png)

Số từ Prometheus khi chạy 3 instance, 100 users (23:36:35):

1. **avg 285 ms, p95 747 ms.** p95 gấp 2,6 lần avg: một phần nhỏ request chậm bị avg che mất.
2. **Nginx chia đều:** 18,05 / 18,22 / 18,06 req/s cho 3 instance.
3. **Input 3968, output 2108 tokens/s:** input gồm system prompt, tài liệu retrieval và câu hỏi, còn output chỉ là câu trả lời.
4. `curl localhost:8080/metrics` trả **404:** Nginx chặn từ bên ngoài, Prometheus scrape trực tiếp trong mạng nội bộ.

### 4.2 Thí nghiệm "phá hệ thống"

A và B được làm **cùng lúc** (3 instance, 30 users). Mốc 0 là 23:37:39, ngay sau khi lệnh `up` xong; log ghi khoảng 5 giây một lần.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | khoảng 88 giây (pending từ giây 25) | Error rate |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | khoảng 141 giây (pending từ giây 25) | p95 latency |
| C | `LLM_MODEL=mock-llm-large` | Không làm | | |
| D | `docker pause` 1 instance | Không làm | | |
| E | `AGENT_VERSION=v1` | Không làm | | |

- B firing sau A vì `for` là 2 phút, còn A là 1 phút.
- `LLMCostBurnRateHigh` đã firing từ giây 0, trước khi A và B có tác dụng: do tải 100 users của bài scale, không phải do thí nghiệm. Rule dùng cửa sổ 5 phút nên còn kéo dài.
- `AgentInstanceDown` chỉ `pending` thoáng qua khi container được tạo lại, không firing.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Metric hạ tầng không biết câu trả lời đúng hay sai. Cần chạy eval trên golden dataset trước mỗi lần deploy (quality gate ở mục 3) và định kỳ trên bản đang chạy, theo dõi retrieval hit ratio và phản hồi của người dùng.

### 4.3 Debug bằng trace

Trace chậm, lấy khi `MOCK_SLOW_RATE=0.3`:

- `trace_id`: `7eebbbd644efe5b0b947bff91edb215f`
- Tổng thời gian: 1784,8 ms
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1637,0 ms, 92%); `agent.retrieve_context` 84,3 ms
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T16:41:56.580237+00:00", "level": "INFO", "service": "observable-agent", "instance": "7ffe4c990c53", "event": "llm_call", "trace_id": "7eebbbd644efe5b0b947bff91edb215f", "span_id": "841b1af79787abb6", "request_id": "c26c7fe14c2a", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 37, "output_tokens": 20, "cost_usd": 1.8e-05, "llm_ms": 1633.5}
{"ts": "2026-11-25T16:41:56.581318+00:00", "level": "INFO", "service": "observable-agent", "instance": "7ffe4c990c53", "event": "http_request", "trace_id": "7eebbbd644efe5b0b947bff91edb215f", "span_id": "841b1af79787abb6", "request_id": "c26c7fe14c2a", "method": "POST", "route": "/ask", "status": 200, "ms": 1783.2}
```

Trace lỗi (`0f1c979d091a5ec1d64c5a84463542a7`):

```json
{"ts": "2026-11-25T16:42:13.734025+00:00", "level": "INFO", "service": "observable-agent", "instance": "7ffe4c990c53", "event": "llm_error", "trace_id": "0f1c979d091a5ec1d64c5a84463542a7", "span_id": "dfb70c7bdb3fe648", "request_id": "6483fb31bd9a", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Dòng `/ask` trong `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv`:

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 57,6 | 240 | 1700 | 2200 | 62 / 6203 (1,00%) |
| 3 | 56,8 | 210 | 980 | 2000 | 64 / 6762 (0,95%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **p95 giảm 42%** (1700 → 980 ms), p50 giảm 12%, p99 chỉ giảm 9%.
- Với 1 instance, LLM p95 chỉ khoảng 198 ms trong khi HTTP p95 khoảng 1,3 giây (Prometheus, 90 giây). Phần chênh nằm ngoài LLM: có thể là request xếp hàng trong instance bị giới hạn 0,5 CPU. Tôi chưa đo CPU để xác nhận.
- **p99 gần như không đổi** vì phần đuôi chủ yếu đến từ 3% request chậm 1,5 giây của mock LLM; thêm instance không sửa được.
- **RPS không tăng** (57,6 và 56,8): 100 users nghỉ 0,5–2 giây giữa các lần gọi, nên tải bị giới hạn bởi số user. Lượt 3 instance gửi nhiều request hơn (6762 so với 6203) nhưng RPS trong CSV không cao hơn, nên không dùng RPS để kết luận.
- Failures gần bằng nhau, khớp mức lỗi 1% của mock.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. Trung bình che mất request chậm: 3% request chậm làm p99 tăng 7,4 lần trong khi avg chỉ tăng 18%.
  2. Scale chỉ giúp phần chậm do xếp hàng: p95 giảm 42%, còn p99 gần như giữ nguyên vì do LLM.
  3. Nhanh và không lỗi chưa phải là đúng: v1 chỉ đúng 1/23 câu, chỉ eval mới phát hiện được.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa? Alert p99, lỗi 5xx đo ở Nginx, CPU của từng instance, retrieval hit ratio giảm, và điểm eval định kỳ.

**Sửa code mẫu:** `production/Dockerfile` thiếu `ENV PYTHONUSERBASE=/home/agent/.local` nên container crash (`No module named 'uvicorn'`); đã thêm dòng này. Cổng 8089 bị Windows chiếm nên chạy Locust headless.
