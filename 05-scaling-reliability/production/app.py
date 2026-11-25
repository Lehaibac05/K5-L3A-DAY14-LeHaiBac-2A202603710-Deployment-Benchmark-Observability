"""
ADVANCED — Stateless Agent với Redis Session

Stateless = agent không giữ state trong memory.
Mọi state (session, conversation history) lưu trong Redis.

Tại sao stateless quan trọng khi scale?
  Instance 1: User A gửi request 1 → lưu session trong memory
  Instance 2: User A gửi request 2 → KHÔNG có session! Bug!

  ✅ Giải pháp: Lưu session trong Redis
  Bất kỳ instance nào cũng đọc được session của user.

Demo:
  docker compose up
  # Sau đó test multi-turn conversation
  python test_stateless.py
"""
import os
import time
import json
import logging
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager


from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from utils.mock_llm import ask

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis = redis.from_url(
    REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

START_TIME = time.time()
INSTANCE_ID = os.getenv("INSTANCE_ID", f"instance-{uuid.uuid4().hex[:6]}")


# ──────────────────────────────────────────────────────────
# Session Storage (Redis-backed, Stateless-compatible)
# ──────────────────────────────────────────────────────────

SESSION_TTL_SECONDS = 3600
MAX_MESSAGES = 20  # 10 turns


def load_history(session_id: str) -> list[dict]:
    return [json.loads(m) for m in _redis.lrange(f"session:{session_id}", 0, -1)]


def append_to_history(session_id: str, role: str, content: str):
    key = f"session:{session_id}"
    message = json.dumps({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # RPUSH là atomic: hai instance cùng ghi một session không đè mất message của nhau.
    with _redis.pipeline() as p:
        p.rpush(key, message)
        p.ltrim(key, -MAX_MESSAGES, -1)
        p.expire(key, SESSION_TTL_SECONDS)
        p.execute()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting instance {INSTANCE_ID}")
    yield
    logger.info(f"Instance {INSTANCE_ID} shutting down")


app = FastAPI(
    title="Stateless Agent",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None  # None = tạo session mới


# ──────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────

@app.post("/chat")
def chat(body: ChatRequest):
    """
    Multi-turn conversation với session management.

    Gửi session_id trong các request tiếp theo để tiếp tục cuộc trò chuyện.
    Agent có thể chạy trên bất kỳ instance nào — state trong Redis.
    """
    # Tạo hoặc dùng session hiện có
    session_id = body.session_id or str(uuid.uuid4())

    # Thêm câu hỏi vào history
    append_to_history(session_id, "user", body.question)

    # Gọi LLM với context (trong mock, ta chỉ dùng câu hỏi hiện tại)
    history = load_history(session_id)
    answer = ask(body.question)

    # Lưu response vào history
    append_to_history(session_id, "assistant", answer)

    return {
        "session_id": session_id,
        "question": body.question,
        "answer": answer,
        "turn": len([m for m in history if m["role"] == "user"]),
        "served_by": INSTANCE_ID,  # ← thấy rõ bất kỳ instance nào cũng serve được
        "storage": "redis",
    }


@app.get("/chat/{session_id}/history")
def get_history(session_id: str):
    """Xem conversation history của một session."""
    history = load_history(session_id)
    if not history:
        raise HTTPException(404, f"Session {session_id} not found or expired")
    return {
        "session_id": session_id,
        "messages": history,
        "count": len(history),
    }


@app.delete("/chat/{session_id}")
def delete_session(session_id: str):
    """Xóa session (user logout)."""
    _redis.delete(f"session:{session_id}")
    return {"deleted": session_id}


# ──────────────────────────────────────────────────────────
# Health / Metrics
# ──────────────────────────────────────────────────────────

@app.get("/health")
def health():
    try:
        redis_ok = _redis.ping()
    except redis.RedisError:
        redis_ok = False

    return {
        "status": "ok" if redis_ok else "degraded",
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "storage": "redis",
        "redis_connected": redis_ok,
    }


@app.get("/ready")
def ready():
    try:
        _redis.ping()
    except redis.RedisError:
        raise HTTPException(503, "Redis not available")
    return {"ready": True, "instance": INSTANCE_ID}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
