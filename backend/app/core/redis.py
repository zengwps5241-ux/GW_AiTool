"""Redis 客户端生命周期管理。"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings

_client: Redis | None = None


def get_redis_client() -> Redis:
    """返回进程级 Redis 客户端；测试可 monkeypatch 本函数。"""
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def close_redis_client() -> None:
    """关闭 Redis 连接池，供应用生命周期或测试清理。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
