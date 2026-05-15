"""
Simulation cache abstraction with Redis and in-memory fallback implementations.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
import json
import structlog

log = structlog.get_logger()


class SimulationCache(ABC):
    """Abstract base class for simulation result caching."""

    @abstractmethod
    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int = 3600) -> None:
        """Store a simulation result with optional TTL."""
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve a cached simulation result."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a cached simulation result."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cached simulations."""
        pass


class RedisSimulationCache(SimulationCache):
    """Redis-backed simulation cache with TTL support."""

    def __init__(self, redis_url: str, ttl_seconds: int = 3600):
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.redis = None
        self.prefix = "athena:sim:"

    async def connect(self):
        """Lazy-init Redis connection."""
        if self.redis is None:
            try:
                import redis.asyncio as redis_asyncio
                self.redis = await redis_asyncio.from_url(self.redis_url, decode_responses=True)
                await self.redis.ping()
                log.info("redis.connected", url=self.redis_url)
            except Exception as exc:
                log.error("redis.connection_error", error=str(exc))
                raise

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int = None) -> None:
        """Store simulation in Redis with TTL."""
        await self.connect()
        if ttl_seconds is None:
            ttl_seconds = self.ttl_seconds

        redis_key = f"{self.prefix}{key}"
        json_value = json.dumps(value)

        try:
            await self.redis.setex(redis_key, ttl_seconds, json_value)
            log.debug("redis.set", key=key, ttl_seconds=ttl_seconds)
        except Exception as exc:
            log.error("redis.set_error", key=key, error=str(exc))
            raise

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve simulation from Redis."""
        await self.connect()
        redis_key = f"{self.prefix}{key}"

        try:
            json_value = await self.redis.get(redis_key)
            if json_value is None:
                log.debug("redis.cache_miss", key=key)
                return None

            result = json.loads(json_value)
            log.debug("redis.cache_hit", key=key)
            return result
        except Exception as exc:
            log.error("redis.get_error", key=key, error=str(exc))
            return None

    async def delete(self, key: str) -> None:
        """Delete simulation from Redis."""
        await self.connect()
        redis_key = f"{self.prefix}{key}"

        try:
            await self.redis.delete(redis_key)
            log.debug("redis.delete", key=key)
        except Exception as exc:
            log.error("redis.delete_error", key=key, error=str(exc))

    async def clear(self) -> None:
        """Clear all cached simulations."""
        await self.connect()

        try:
            pattern = f"{self.prefix}*"
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
            log.info("redis.clear", count=len(keys) if keys else 0)
        except Exception as exc:
            log.error("redis.clear_error", error=str(exc))

    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            self.redis = None


class MemorySimulationCache(SimulationCache):
    """In-memory cache fallback for single-process or testing."""

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self.cache: dict[str, tuple[dict[str, Any], float]] = {}

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int = None) -> None:
        """Store simulation in memory."""
        if ttl_seconds is None:
            ttl_seconds = self.ttl_seconds

        import time
        expiry = time.time() + ttl_seconds
        self.cache[key] = (value, expiry)
        log.debug("memory.set", key=key, ttl_seconds=ttl_seconds)

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve simulation from memory, checking expiry."""
        if key not in self.cache:
            log.debug("memory.cache_miss", key=key)
            return None

        value, expiry = self.cache[key]
        import time
        if time.time() > expiry:
            del self.cache[key]
            log.debug("memory.cache_expired", key=key)
            return None

        log.debug("memory.cache_hit", key=key)
        return value

    async def delete(self, key: str) -> None:
        """Delete simulation from memory."""
        if key in self.cache:
            del self.cache[key]
            log.debug("memory.delete", key=key)

    async def clear(self) -> None:
        """Clear all cached simulations."""
        count = len(self.cache)
        self.cache.clear()
        log.info("memory.clear", count=count)


async def get_simulation_cache(settings) -> SimulationCache:
    """Factory function: return Redis cache if available, else memory fallback."""
    if settings.redis_url and settings.redis_url != "redis://localhost:6379":
        try:
            cache = RedisSimulationCache(settings.redis_url, settings.simulation_cache_ttl_seconds)
            await cache.connect()
            log.info("simulation_cache.using_redis")
            return cache
        except Exception as exc:
            log.warning("simulation_cache.redis_failed, using memory fallback", error=str(exc))

    log.info("simulation_cache.using_memory")
    return MemorySimulationCache(settings.simulation_cache_ttl_seconds)
