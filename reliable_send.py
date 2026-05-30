"""Reliable Discord send queue.

All signal sends pass through one queue/worker.  It retries transient Discord
errors, respects retry_after when available, logs attempts to DB, and falls back
to embed-only if a chart/file cannot be attached.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional

import discord

try:
    import db
except Exception:  # pragma: no cover
    db = None


@dataclass
class SendJob:
    channel: object
    embed: discord.Embed
    file_path: str | None = None
    signal_id: str | None = None
    tier: str | None = None
    max_attempts: int = 3
    future: asyncio.Future | None = None


_queue: asyncio.Queue[SendJob] | None = None
_worker_task: asyncio.Task | None = None


def _err_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:900]


def _log_attempt(signal_id, tier, channel_id, attempt, status, message_id=None, error=None):
    if db:
        try:
            db.record_discord_attempt(signal_id, tier, channel_id, attempt, status, message_id=message_id, error=error)
        except Exception:
            pass


def _log_event(event, payload=None, level="info"):
    if db:
        try:
            db.log_event(event, payload or {}, level=level)
        except Exception:
            pass


async def start() -> None:
    """Start the global send worker for the current event loop."""
    global _queue, _worker_task
    if _queue is None:
        maxsize = int(os.environ.get("DISCORD_SEND_QUEUE_SIZE", "200") or 200)
        _queue = asyncio.Queue(maxsize=max(10, maxsize))
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker(), name="discord-send-queue")
        _log_event("discord_send_queue_started")


async def stop() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except Exception:
            pass


async def send_queued(
    channel,
    *,
    embed: discord.Embed,
    file_path: str | None = None,
    signal_id: str | None = None,
    tier: str | None = None,
    max_attempts: int | None = None,
) -> Optional[discord.Message]:
    """Queue a Discord embed send and wait for the result."""
    await start()
    assert _queue is not None
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    job = SendJob(
        channel=channel,
        embed=embed,
        file_path=file_path,
        signal_id=signal_id,
        tier=tier,
        max_attempts=int(max_attempts or os.environ.get("DISCORD_SEND_MAX_ATTEMPTS", "3") or 3),
        future=fut,
    )
    try:
        _queue.put_nowait(job)
    except asyncio.QueueFull:
        _log_event("discord_send_queue_full", {"signal_id": signal_id, "tier": tier}, level="error")
        return None
    return await fut


async def _worker() -> None:
    assert _queue is not None
    while True:
        job = await _queue.get()
        try:
            msg = await _send_with_retry(job)
            if job.future and not job.future.done():
                job.future.set_result(msg)
        except Exception as exc:
            _log_event("discord_queue_worker_error", {"error": _err_text(exc), "signal_id": job.signal_id}, level="error")
            if job.future and not job.future.done():
                job.future.set_result(None)
        finally:
            _queue.task_done()


async def _send_with_retry(job: SendJob) -> Optional[discord.Message]:
    channel = job.channel
    if channel is None:
        _log_event("discord_send_skipped", {"reason": "missing_channel", "signal_id": job.signal_id, "tier": job.tier}, level="warning")
        return None

    channel_id = getattr(channel, "id", None)
    last_error = ""
    file_failed = False

    for attempt in range(1, max(1, job.max_attempts) + 1):
        try:
            if job.file_path and not file_failed and os.path.exists(job.file_path):
                try:
                    with open(job.file_path, "rb") as fh:
                        msg = await channel.send(embed=job.embed, file=discord.File(fh, filename=os.path.basename(job.file_path)))
                    _log_attempt(job.signal_id, job.tier, channel_id, attempt, "sent", message_id=getattr(msg, "id", None))
                    return msg
                except (discord.Forbidden, discord.HTTPException, OSError) as file_exc:
                    # A chart should never be the reason a signal is lost.  Log it,
                    # then retry this same attempt as embed-only.
                    file_failed = True
                    last_error = _err_text(file_exc)
                    _log_attempt(job.signal_id, job.tier, channel_id, attempt, "file_failed", error=last_error)

            msg = await channel.send(embed=job.embed)
            status = "sent_embed_only" if file_failed else "sent"
            _log_attempt(job.signal_id, job.tier, channel_id, attempt, status, message_id=getattr(msg, "id", None), error=last_error if file_failed else None)
            return msg

        except discord.Forbidden as exc:
            last_error = _err_text(exc)
            _log_attempt(job.signal_id, job.tier, channel_id, attempt, "forbidden", error=last_error)
            _log_event("discord_forbidden", {"channel_id": channel_id, "signal_id": job.signal_id, "tier": job.tier, "error": last_error}, level="error")
            return None
        except discord.HTTPException as exc:
            last_error = _err_text(exc)
            _log_attempt(job.signal_id, job.tier, channel_id, attempt, "http_error", error=last_error)
            retry_after = getattr(exc, "retry_after", None)
            if retry_after:
                await asyncio.sleep(float(retry_after) + 0.25)
            else:
                await asyncio.sleep(min(2 ** attempt, 12))
        except Exception as exc:
            last_error = _err_text(exc)
            _log_attempt(job.signal_id, job.tier, channel_id, attempt, "error", error=last_error)
            await asyncio.sleep(min(2 ** attempt, 12))

    _log_event("discord_send_failed", {"channel_id": channel_id, "signal_id": job.signal_id, "tier": job.tier, "error": last_error}, level="error")
    return None


def stats() -> dict:
    """Queue status for /health and admin diagnostics."""
    return {
        "started": bool(_worker_task and not _worker_task.done()),
        "queue_size": _queue.qsize() if _queue is not None else 0,
        "queue_maxsize": _queue.maxsize if _queue is not None else 0,
    }
