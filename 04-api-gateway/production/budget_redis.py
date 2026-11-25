import os
from datetime import datetime, timezone

import redis

r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
MONTHLY_BUDGET_USD = 10.0


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


if __name__ == "__main__":
    key = f"budget:cp3-demo:{datetime.now(timezone.utc):%Y-%m}"
    r.delete(key)
    results = [(c, check_budget("cp3-demo", c)) for c in (6, 3, 2, 1)]
    print(results, "spent =", float(r.get(key)), "ttl =", r.ttl(key))
    assert [ok for _, ok in results] == [True, True, False, True]
    assert float(r.get(key)) == 10
    r.delete(key)