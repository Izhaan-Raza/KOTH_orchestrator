from __future__ import annotations

import asyncio
import threading
import logging

import httpx

from config import SETTINGS

logger = logging.getLogger("koth.referee")


async def send_webhook(payload: dict) -> None:
    if not SETTINGS.webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(SETTINGS.webhook_url, json=payload)
    except Exception as exc:
        logger.error("webhook delivery failed: %s", exc)


def fire_and_forget(payload: dict) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(send_webhook(payload))
    except RuntimeError:
        threading.Thread(
            target=lambda: asyncio.run(send_webhook(payload)),
            daemon=True,
        ).start()
