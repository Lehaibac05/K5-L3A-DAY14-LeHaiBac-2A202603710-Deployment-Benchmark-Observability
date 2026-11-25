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

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
