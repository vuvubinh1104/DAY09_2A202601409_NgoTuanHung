# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung          |
| --------------- | ----------------- |
| Họ và tên       | Ngô Tuấn Hưng     |
| MSSV            | 2A202601409       |
| Khóa/Lớp        | K3                |
| Vai trò chính   | Toàn bộ hệ thống (individual) |
| Ngày hoàn thành | 2026-08-05        |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Pipeline orchestration (LangGraph) | `src/main.py` → `build_graph()`, `run_case()` | 50 file `input/EC_xxx.json` | 50 file `output/EC_xxx.json`, `trace.jsonl` | Hoàn thành |
| Coordinator Agent | `src/agents/coordinator.py` → `coordinator_node()` | `AgentState` ban đầu (case_id, order_id, customer_message) | AgentState pass-through + LLM triage log | Hoàn thành |
| Order & Seller Agent | `src/agents/order_seller_agent.py` → `order_seller_node()` | `order_id` | `order_status`, `items[]`, `sellers[]`, delivery timestamps | Hoàn thành |
| Payment Agent | `src/agents/payment_agent.py` → `payment_node()` | `order_id` | `item_total`, `freight_total`, `payment_total`, `payments[]` | Hoàn thành |
| Delivery Agent | `src/agents/delivery_agent.py` → `delivery_node()` | Timestamps từ state | `is_late_delivery`, `is_seller_handoff_late`, `late_seller_ids[]` | Hoàn thành |
| Policy Engine | `src/policy.py` → `apply_policy()` | Các flag từ Delivery + Payment | `PolicyDecision` (primary_issue, refund, action, confidence) | Hoàn thành |
| Policy Agent | `src/agents/policy_agent.py` → `policy_node()` | State từ upstream agents | State cập nhật theo `EC_POLICY_V1` | Hoàn thành |
| Verifier Agent | `src/agents/verifier_agent.py` → `verifier_node()` | State đầy đủ | `output` dict đã validate Pydantic, `verified`, `verification_errors` | Hoàn thành |
| Schema definitions | `src/schemas.py` | — | `AgentState` TypedDict, `CaseOutput` Pydantic model | Hoàn thành |
| Data loader tools | `src/tools/data_loader.py` | order_id | Order row, items list, sellers list, payments list | Hoàn thành |
| `architecture.md` | `architecture.md` | — | Sơ đồ agent, vai trò, quyền truy cập, handoff protocol | Hoàn thành |
| `metadata.json` | `metadata.json` | — | Model, framework, runtime, agent list | Hoàn thành |
| `trace.jsonl` | Sinh tự động bởi `src/main.py` | 50 case outputs | 50 trace entries (elapsed_s, verified, primary_issue, v.v.) | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Cấu hình Ollama local (chuyển từ Ollama Cloud → localhost:11434) | `.env`, `coordinator.py` | Giải quyết lỗi 403 Forbidden từ Ollama Cloud; chạy thành công với `qwen3:4b` local |
| Debug binary conflict Ollama (`~/.local/bin/ollama` cũ đè `/usr/local/bin/ollama` mới) | Môi trường hệ thống | Xóa file cũ, Ollama chạy đúng |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Thiết kế và lập trình toàn bộ pipeline 6 agent theo LangGraph | `src/main.py`, `src/agents/*.py` | Graph compile thành công, pipeline chạy sequential | `uv run python src/main.py --case EC_001` |
| Triển khai EC_POLICY_V1 dạng pure Python deterministic | `src/policy.py` → `apply_policy()` | 6 nhánh policy đúng thứ tự ưu tiên, không LLM call | Kiểm tra output EC_003 (canceled), EC_005 (unavailable), EC_001 (seller late) |
| Verifier: validate schema Pydantic + evidence ID regex + financial sanity | `src/agents/verifier_agent.py` | 50/50 case `verified=True`, `verification_errors=[]` | `grep '"verified": true' trace.jsonl \| wc -l` → 50 |
| Chạy toàn bộ 50 case, ghi output và trace | `output/`, `trace.jsonl` | 50 file JSON đúng schema, 50 dòng trace | `ls output/ \| wc -l` → 50 |
| Cấu hình Ollama local và `.env` | `.env`, `coordinator.py` | Chạy thành công với `qwen3:4b` qua `http://localhost:11434` | `ollama list` → `qwen3:4b` có mặt |

**Output cụ thể:** `trace.jsonl` có 50 dòng, mỗi dòng chứa `case_id`, `primary_issue`, `verified=true`, `recommended_refund_brl`, `elapsed_s`. Ví dụ EC_001: `primary_issue=late_delivery_seller`, `recommended_refund_brl=12.04`, `verified=true`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Hệ thống phải điều tra 50 khiếu nại thương mại điện tử: mỗi case chỉ có `claimed_order_id`, nhưng kết luận cần đối chiếu trạng thái đơn (orders CSV), mốc bàn giao hàng (order_items CSV), thông tin seller (sellers CSV) và toàn bộ payment rows (order_payments CSV). Không được tự suy diễn sự kiện không có trong dữ liệu — mọi quyết định phải traceable về dữ liệu CSV gốc.

### Cách triển khai

**LangGraph sequential pipeline**: Thay vì dùng một prompt monolithic, tôi tách logic thành 6 node trong `StateGraph(AgentState)`. Mỗi node nhận toàn bộ `AgentState` TypedDict, cập nhật đúng các field của mình, rồi trả về state cho node tiếp theo.

**Policy engine thuần Python**: `apply_policy()` trong `src/policy.py` áp dụng 6 rule theo thứ tự ưu tiên cứng (canceled > unavailable > late_seller > late_logistics > split_payment > fallback). Không có LLM trong vòng quyết định này — đảm bảo tính deterministic và reproducibility.

**Evidence ID generation**: `verifier_agent.py` xây evidence ID từ dữ liệu thực trong state (order_id, item.order_item_id, payment.payment_sequential, seller_id, root_cause_code), validate bằng regex `_EVIDENCE_PATTERN`, dedup và giới hạn 10 ID.

**LLM chỉ ở coordinator**: Chỉ 1 LLM call/case để triage customer message, non-blocking (wrapped trong try/except). Nếu Ollama không chạy thì pipeline vẫn tiếp tục bình thường.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `input/EC_xxx.json` với schema: `case_id`, `opened_at`, `customer_request.claimed_order_id`, `policy_version` |
| Output | `output/EC_xxx.json` theo schema 7 trường: `case_id`, `assessment`, `affected_entities`, `root_cause_analysis`, `evidence_ids`, `financial_resolution`, `resolution_actions` |
| Module phụ thuộc | `src/tools/data_loader.py` (pandas CSV lookup), `src/policy.py` (business logic), `src/schemas.py` (Pydantic + TypedDict) |
| Module sử dụng output | `trace.jsonl` writer trong `src/main.py`, grader script của lab |
| Điều kiện lỗi cần xử lý | Order không tìm thấy trong CSV → safe defaults; Ollama unavailable → LLM skip, pipeline tiếp tục; `nan` timestamps → cast thành `None` tránh sai lệch timestamp comparison |

### Cách xác minh

```bash
# Chạy toàn bộ 50 case
uv run python src/main.py --all

# Kiểm tra số case verified
python3 -c "
import json
lines = open('trace.jsonl').readlines()
ok = sum(1 for l in lines if json.loads(l).get('verified'))
print(f'{ok}/{len(lines)} verified')
"

# Kiểm tra số output file
ls output/ | wc -l
```

- **Kết quả mong đợi:** 50/50 verified, 50 output files.
- **Kết quả thực tế:** 50/50 verified, 50 output files, `verification_errors=[]` cho tất cả case.
- **Artifact/log:** `trace.jsonl` (root repo), `output/EC_001.json` đến `output/EC_050.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Policy engine có thể được triển khai theo 2 cách: (a) dùng LLM prompt để "suy luận" policy từ description, hoặc (b) code thuần Python với if-else theo thứ tự ưu tiên cứng.
- **Các phương án đã cân nhắc:**
  1. **LLM-based policy**: Prompt mô tả 6 rule, để LLM quyết định. Linh hoạt, dễ mở rộng text.
  2. **Pure Python deterministic** (`apply_policy()` trong `src/policy.py`): If-else theo thứ tự ưu tiên, không LLM.
- **Phương án đã chọn:** Pure Python deterministic.
- **Lý do:** Lab yêu cầu mọi khoản tiền phải làm tròn 2 chữ số và không được hallucinate sự kiện. LLM có thể đưa ra kết quả khác nhau qua các lần chạy, sai thứ tự ưu tiên, hoặc tự tạo refund amount không đúng. Python thực thi deterministic, reproducible, dễ unit test và không tốn VRAM.
- **Bằng chứng quyết định phù hợp:** 50/50 case `verified=True` với Pydantic schema check pass, không có financial anomaly nào cần correction trong `verification_errors`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `403 Client Error: Forbidden for url: https://api.ollama.ai/api/chat` khi chạy `uv run python src/main.py --all`. Pipeline crash ngay tại coordinator node.
- **Lệnh hoặc bước tái hiện:** `uv run python src/main.py --case EC_001` với `OLLAMA_HOST=https://api.ollama.ai` trong `.env`.
- **Nguyên nhân gốc:** Tài khoản Ollama Cloud không có quyền API (endpoint bị restrict). Đồng thời, file `~/.local/bin/ollama` cũ (binary bị lỗi từ lần cài đặt trước) đang shadow `/usr/local/bin/ollama` mới cài — khiến `which ollama` trỏ nhầm và `ollama serve` không khởi động được.
- **Cách xử lý:**
  1. Xóa binary cũ: `rm ~/.local/bin/ollama`
  2. Cài lại Ollama: `curl -fsSL https://ollama.com/install.sh | sh`
  3. Kéo model: `ollama pull qwen3:4b`
  4. Cập nhật `.env`: `OLLAMA_HOST=http://localhost:11434`
  5. `coordinator.py` đọc `OLLAMA_HOST` từ env với fallback `http://localhost:11434`
- **Cách xác minh sau khi sửa:** `uv run python src/main.py --case EC_001` → coordinator log `[Coordinator] LLM classification: ...` (không exception), output file `output/EC_001.json` được ghi.
- **Điều học được:** Khi dùng Ollama, cần đặt base_url rõ ràng từ env (không hardcode), và luôn kiểm tra `which ollama` + `ollama list` trước khi chạy pipeline để xác nhận binary và model đúng.

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của tôi về luồng của hệ thống **multi-agent e-commerce dispute resolution** này:

1. **Dữ liệu đi từ input case đến output như thế nào?**
   File `input/EC_xxx.json` chứa `claimed_order_id`. `coordinator_node` khởi tạo `AgentState` với order_id đó. `order_seller_node` dùng `data_loader` để đọc pandas DataFrame từ `data/*.csv` và tra cứu order row, items, sellers. `payment_node` tính tổng payment. `delivery_node` so sánh timestamps. `policy_node` gọi `apply_policy()` để ra quyết định. `verifier_node` validate và ghi `output` dict vào state. `main.py` ghi file JSON và trace entry.

2. **Pipeline handoff hoạt động ra sao?**
   LangGraph `StateGraph` truyền cùng một `AgentState` TypedDict qua 6 node tuần tự: `START → coordinator → order_seller → payment → delivery → policy → verifier → END`. Mỗi node chỉ đọc các field nó cần và ghi thêm các field mới. Không node nào skip.

3. **Verifier khác các agent khác ở điểm nào trong pipeline?**
   Verifier là checkpoint cuối — nó không xử lý domain data mà chỉ validate: (a) format evidence ID bằng regex, (b) giới hạn list length (max 5 per entity set, 10 evidence), (c) Pydantic schema check toàn bộ `CaseOutput`, (d) sửa financial anomaly (no_action case với refund > 0). Đây là lớp bảo vệ chống hallucination của các agent upstream.

4. **Vì sao policy engine phải chạy sau cả 3 agent data (Order, Payment, Delivery)?**
   `apply_policy()` cần đồng thời `order_status`, `payment_total`, `freight_total`, `is_late_delivery`, `is_seller_handoff_late`, `late_seller_ids` — tất cả đến từ 3 agent khác nhau. Nếu policy chạy trước, nó sẽ nhận giá trị mặc định (None/0/False) và ra quyết định sai.

5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   Trong context bài lab này: một case được coi là xử lý đúng khi `verified=True` (Pydantic pass) và `verification_errors=[]` trong `trace.jsonl`. Financial repair cụ thể: nếu `case_status=no_action` mà `recommended_refund > 0`, verifier tự động correction về `0.0` và log warning — đây là tự-repair trong pipeline.

**Câu trả lời tổng:** Pipeline xử lý 50 case hoàn toàn tự động, mỗi case mất ~12–34 giây (1 LLM call tại coordinator + pure Python cho 5 agent còn lại). Kết quả: 50/50 case `verified=True`, toàn bộ output hợp lệ về schema và financial constraints.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Ngô Tuấn Hưng
**Ngày xác nhận:** 2026-08-05
