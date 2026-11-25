"""Rate limiting: sliding window 60 giây, state trong Redis."""
import hashlib
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    # Băm để API key không nằm nguyên văn trong Redis.
    redis_key = f"ratelimit:{hashlib.sha256(key.encode()).hexdigest()}"
    now = time.time()
    member = uuid.uuid4().hex
    # Thêm trước rồi mới đếm (MULTI/EXEC): hai request song song không thể cùng lọt qua.
    with r.pipeline() as p:
        p.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
        p.zadd(redis_key, {member: now})
        p.zcard(redis_key)
        p.expire(redis_key, WINDOW_SECONDS)
        count = p.execute()[2]
    if count > settings.rate_limit_per_minute:
        r.zrem(redis_key, member)  # request bị chặn không chiếm lượt
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
