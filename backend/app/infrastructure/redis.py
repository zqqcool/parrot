from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from app.core.config import RedisSection


class RedisManager:
    def __init__(self, config: RedisSection) -> None:
        self.enabled = config.enabled
        self.key_prefix = config.key_prefix
        self.client: Redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            config.url, decode_responses=True
        )

    async def ping(self) -> bool:
        if not self.enabled:
            return False
        ping = cast(
            Callable[[], Awaitable[bool]],
            self.client.ping,  # pyright: ignore[reportUnknownMemberType]
        )
        result = await ping()
        return result

    async def allow(self, scope: str, limit: int, window_seconds: int) -> bool:
        if not self.enabled:
            return True
        key = f"{self.key_prefix}:rate:{scope}"
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, window_seconds)
        return int(count) <= limit

    async def publish_interaction_event(self, interaction_id: str) -> None:
        if not self.enabled:
            return
        publish = cast(
            Callable[[str, str], Awaitable[int]],
            self.client.publish,  # pyright: ignore[reportUnknownMemberType]
        )
        await publish(self._interaction_channel(interaction_id), "committed")

    async def subscribe_interaction(self, interaction_id: str) -> RedisEventSubscriber:
        if not self.enabled:
            return RedisEventSubscriber(None)
        create_pubsub = cast(
            Callable[[], PubSub],
            self.client.pubsub,  # pyright: ignore[reportUnknownMemberType]
        )
        pubsub = create_pubsub()
        subscribe = cast(
            Callable[[str], Awaitable[None]],
            pubsub.subscribe,  # pyright: ignore[reportUnknownMemberType]
        )
        await subscribe(self._interaction_channel(interaction_id))
        return RedisEventSubscriber(pubsub)

    def _interaction_channel(self, interaction_id: str) -> str:
        return f"{self.key_prefix}:interaction:{interaction_id}:events"

    async def close(self) -> None:
        await self.client.aclose()


class RedisEventSubscriber:
    def __init__(self, pubsub: PubSub | None) -> None:
        self._pubsub = pubsub

    async def wait(self, timeout_seconds: float) -> None:
        if self._pubsub is None:
            await asyncio.sleep(timeout_seconds)
            return
        await self._pubsub.get_message(
            ignore_subscribe_messages=True,
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        if self._pubsub is not None:
            await self._pubsub.aclose()
