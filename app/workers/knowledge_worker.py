"""
Knowledge worker: drains knowledge:queue and runs the RAG + Gemini pipeline.
Run with:
    python -m app.workers.knowledge_worker
"""
import asyncio
import signal
import uuid
import redis.asyncio as aioredis
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.redis import get_redis_pool
from app.db.session import AsyncSessionLocal, engine
from app.services.knowledge import run_knowledge

logger=get_logger(__name__)

_shutdown=False 
def _handle_signal(sig, frame):
    global _shutdown
    _shutdown=True
    logger.info("knowledge_worker_shutdown",signal=sig)

async def process_one(report_id_str: str, redis_client: aioredis.Redis) -> None:
    try:
        report_id = uuid.UUID(report_id_str)
    except ValueError:
        logger.error("knowledge_invalid_report_id", value=report_id_str)
        return 

    async with AsyncSessionLocal() as db:
        await run_knowledge(report_id=report_id, db=db, redis=redis_client)

async def run_worker() -> None:
    settings=get_settings()
    setup_logging()
    logger.info("knowledge_worker_started")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    pool=get_redis_pool()
    redis_client = aioredis.Redis(connection_pool=pool)
    semaphore=asyncio.Semaphore(4)

    async def bounded(item: str):
        async with semaphore:
            await process_one(item, redis_client)

    try:
        while not _shutdown:
            result = await redis_client.blpop(settings.knowledge_queue_key, timeout=2)
            if result is None:
                continue

            _, raw = result
            report_id_str = raw if isinstance(raw, str) else raw.decode()
            logger.info("knowledge_dequeued", report_id=report_id_str)
            asyncio.create_task(bounded(report_id_str))
    finally:
        await redis_client.aclose()
        await engine.dispose()
        logger.info("knowledge_worker_stopped")

if __name__=="__main__":
    asyncio.run(run_worker())