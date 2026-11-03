from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import RedisSection
from app.infrastructure.redis import RedisEventSubscriber, RedisManager


def _manager(*, enabled: bool) -> RedisManager:
    return RedisManager(
        RedisSection(
            enabled=enabled,
            url="redis://localhost:6379/0",
            key_prefix="parrot-test",
        )
    )


@pytest.mark.asyncio
async def test_disabled_redis_keeps_rate_limit_and_event_delivery_available() -> None:
    manager = _manager(enabled=False)
    manager.client = Mock()

    assert await manager.ping() is False
    assert await manager.allow("visitor:one", limit=1, window_seconds=60) is True
    await manager.publish_interaction_event("interaction_one")
    subscriber = await manager.subscribe_interaction("interaction_one")
    await subscriber.wait(0)
    await subscriber.close()

    manager.client.assert_not_called()


@pytest.mark.asyncio
async def test_enabled_redis_uses_interaction_scoped_wakeup_channel() -> None:
    manager = _manager(enabled=True)
    client = Mock()
    client.publish = AsyncMock(return_value=1)
    pubsub = Mock()
    pubsub.subscribe = AsyncMock()
    pubsub.get_message = AsyncMock(return_value={"data": "committed"})
    pubsub.aclose = AsyncMock()
    client.pubsub.return_value = pubsub
    manager.client = client

    await manager.publish_interaction_event("interaction_one")
    subscriber = await manager.subscribe_interaction("interaction_one")
    await subscriber.wait(0.25)
    await subscriber.close()

    channel = "parrot-test:interaction:interaction_one:events"
    client.publish.assert_awaited_once_with(channel, "committed")
    pubsub.subscribe.assert_awaited_once_with(channel)
    pubsub.get_message.assert_awaited_once_with(
        ignore_subscribe_messages=True,
        timeout=0.25,
    )
    pubsub.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_enabled_rate_limit_sets_expiry_only_for_first_hit() -> None:
    manager = _manager(enabled=True)
    client = Mock()
    client.incr = AsyncMock(side_effect=[1, 2, 3])
    client.expire = AsyncMock()
    manager.client = client

    assert await manager.allow("visitor:one", limit=2, window_seconds=30) is True
    assert await manager.allow("visitor:one", limit=2, window_seconds=30) is True
    assert await manager.allow("visitor:one", limit=2, window_seconds=30) is False

    client.expire.assert_awaited_once_with("parrot-test:rate:visitor:one", 30)


@pytest.mark.asyncio
async def test_subscriber_without_pubsub_waits_without_opening_a_connection() -> None:
    subscriber = RedisEventSubscriber(None)

    await subscriber.wait(0)
    await subscriber.close()
