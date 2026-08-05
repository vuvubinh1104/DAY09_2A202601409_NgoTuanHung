# Setup & Implementation Plan: Multi-Agent E-commerce Dispute Resolution

## Tổng quan

Xây dựng hệ thống **Supervisor (Coordinator) + Specialized Agents + Verifier** để xử lý 50 case khiếu nại thương mại điện tử trên dữ liệu Olist, chạy hoàn toàn local với **Qwen3-4B-Instruct** qua Ollama.

**Môi trường máy**:
- RAM: 16 GB
- GPU: NVIDIA RTX 2050 (4 GB VRAM)
- Python: 3.14.4
- Package manager: `uv 0.11.12`
- Ollama: **chưa cài**

---

## Phase 1 – Cài đặt môi trường

### 1.1 Cài Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 1.2 Pull model Qwen3-4B-Instruct

```bash
ollama pull qwen3:4b
```

> Qwen3-4B chạy được trên 4 GB VRAM (quantized Q4_K_M ~2.5 GB).
> Model ≤ 10B params → đúng quy định đề bài.

### 1.3 Khởi tạo project với `uv`

```bash
uv init .
uv add langchain-ollama langgraph pydantic pandas python-dotenv
```

---

## Phase 2 – Kiến trúc Agent

```
input/EC_xxx.json
        │
        ▼
┌──────────────────┐
│  Coordinator     │  ← điều phối, nhận case, giao việc, tổng hợp
└──────┬───────────┘
       │ handoff (state dict)
   ┌───┴────────────────────────────────┐
   │                                    │
   ▼                                    ▼
┌──────────────────┐        ┌──────────────────────┐
│ Order & Seller   │        │   Payment Agent      │
│ Agent            │        │   (đối soát payment) │
│ (status, items,  │        └──────────┬───────────┘
│  seller, handoff)│                   │
└────────┬─────────┘                   │
         │                             │
         ▼                             ▼
┌──────────────────┐        ┌──────────────────────┐
│  Delivery Agent  │        │   Policy Agent       │
│  (timestamps,    │───────►│   (EC_POLICY_V1,     │
│   SLA check)     │        │    refund calc)      │
└──────────────────┘        └──────────┬───────────┘
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │   Verifier Agent     │
                            │   (schema, ID, math) │
                            └──────────┬───────────┘
                                       │
                                       ▼
                              output/EC_xxx.json
```

### Vai trò từng agent

| Agent | Công việc | Truy cập dữ liệu |
|---|---|---|
| **Coordinator** | Parse input, giao task, tổng hợp final output | `input/*.json` |
| **Order & Seller Agent** | Kiểm tra `order_status`, items, `shipping_limit_date`, seller | `orders`, `order_items`, `sellers` |
| **Payment Agent** | Tính tổng payment, đối soát item+freight | `order_payments`, `order_items` |
| **Delivery Agent** | So sánh `order_delivered_customer_date` vs `order_estimated_delivery_date`, `order_delivered_carrier_date` vs `shipping_limit_date` | `orders`, `order_items` |
| **Policy Agent** | Áp dụng `EC_POLICY_V1` → xác định `primary_issue`, `refund`, `action` | state từ các agent trước |
| **Verifier Agent** | Validate schema, evidence ID format, math, limits | state hoàn chỉnh |

---

## Phase 3 – Cấu trúc file

```
DAY09_2A202601409_NgoTuanHung/
├── pyproject.toml          # uv project
├── .python-version
├── .env                    # (không commit)
├── .env.example
├── metadata.json
├── architecture.md
├── trace.jsonl             # auto-generated
├── src/
│   ├── agents/
│   │   ├── coordinator.py
│   │   ├── order_seller_agent.py
│   │   ├── payment_agent.py
│   │   ├── delivery_agent.py
│   │   ├── policy_agent.py
│   │   └── verifier_agent.py
│   ├── tools/
│   │   └── data_loader.py  # pandas CSV loader & join helpers
│   ├── schemas.py          # Pydantic output schema
│   ├── policy.py           # EC_POLICY_V1 business rules (pure Python)
│   └── main.py             # chạy 50 cases, ghi output & trace
├── data/                   # CSV files (sẵn có)
├── input/                  # JSON cases (sẵn có)
└── output/                 # sẽ được tạo
```

---

## Phase 4 – Chiến lược implementation

### Nguyên tắc quan trọng
- Business logic (policy rules, math) viết thuần **Python** trong `policy.py` → không phụ thuộc LLM cho phép tính tiền.
- LLM (Qwen3-4B) chỉ dùng để **điều phối và diễn giải** ngữ cảnh, không tính số.
- Mỗi agent nhận `state` dict và trả về `state` dict bổ sung — pattern LangGraph `StateGraph`.
- **Verifier** chạy cuối cùng để đảm bảo output đúng schema trước khi ghi file.

### Tối ưu cho 4 GB VRAM
- Dùng `ollama` với model `qwen3:4b` (quantized Q4_K_M).
- Chạy các agent **tuần tự** (không parallel) để tránh OOM.
- Dùng `temperature=0` để output ổn định và deterministic.

---

## Phase 5 – File cần tạo/cập nhật

| File | Hành động |
|---|---|
| `pyproject.toml` | [NEW] – `uv init` + dependencies |
| `.env.example` | [NEW] – template biến môi trường |
| `metadata.json` | [NEW] – model info |
| `src/schemas.py` | [NEW] – Pydantic models |
| `src/policy.py` | [NEW] – EC_POLICY_V1 pure Python |
| `src/tools/data_loader.py` | [NEW] – CSV loader |
| `src/agents/coordinator.py` | [NEW] |
| `src/agents/order_seller_agent.py` | [NEW] |
| `src/agents/payment_agent.py` | [NEW] |
| `src/agents/delivery_agent.py` | [NEW] |
| `src/agents/policy_agent.py` | [NEW] |
| `src/agents/verifier_agent.py` | [NEW] |
| `src/main.py` | [NEW] – entrypoint |
| `architecture.md` | [MODIFY] – cập nhật sơ đồ |

---

## Verification Plan

1. Chạy thử 1 case: `uv run python src/main.py --case EC_001`
2. Kiểm tra `output/EC_001.json` đúng schema
3. Chạy toàn bộ 50 case: `uv run python src/main.py --all`
4. Validate: 50 file JSON tồn tại, `trace.jsonl` có đủ entries
5. Zip output: `cd output && zip -r ../output.zip *.json`

---

## Open Questions

> [!IMPORTANT]
> Bạn có muốn dùng **LangGraph** cho orchestration giữa các agent không, hay prefer viết pipeline đơn giản hơn (sequential function calls)?
> LangGraph cho phép visualize graph và retry từng node nhưng phức tạp hơn một chút.

> [!NOTE]
> Với 4 GB VRAM, Qwen3-4B chạy được nhưng có thể chậm (~5-15s/call). Với 50 cases × ~5-6 LLM calls/case = ~250-300 LLM calls tổng. Tôi sẽ thiết kế để **Policy Agent và data queries chạy thuần Python** (không gọi LLM) để giảm latency và tăng accuracy.
