"""Cost guard: tổng chi phí trong ngày (UTC) lưu trong Redis, chạm DAILY_BUDGET_USD → 402."""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _today_key() -> str:
    return f"cost:{datetime.now(timezone.utc):%Y-%m-%d}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM."""
    # shortcut: chưa tính request đang chạy nên có thể vượt nhẹ; dùng LLM thật thì giữ chỗ trước.
    if float(r.get(_today_key()) or 0) >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM, trả về chi phí của request."""
    cost = input_tokens / 1000 * PRICE_INPUT_PER_1K + output_tokens / 1000 * PRICE_OUTPUT_PER_1K
    key = _today_key()
    with r.pipeline() as p:
        p.incrbyfloat(key, cost)
        p.expire(key, 2 * 24 * 3600)
        p.execute()
    return cost
