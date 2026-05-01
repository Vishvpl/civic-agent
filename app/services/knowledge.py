"""
Knowledge service: loads PerceptionResult, checks cache, queries ChromaDB,
calls Gemini, validates ActionPlan, persists, and enqueues for Phase 4.
"""

import hashlib
import json 
import uuid
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.logging import get_logger 
from app.db.models import DeadLetterQueue, LifecycleEvent, Report, ReportStatus
from app.schemas.report import ActionPlan, PerceptionResult
from app.services.chroma_client import query_collection
from app.services.gemini_client import build_action_plan

logger = get_logger(__name__)

def _cache_key(issue_types: list[str]) -> str:
    """
    Cache key is a hash of sorted issue types.
    Same mix of issues -> same RAG + Gemini result.
    """
    joined="|".join(sorted(issue_types))
    digest = hashlib.sha256(joined.encode()).hexdigest()[:20]
    return f"rag:{digest}"

async def _transition(db: AsyncSession, report: Report, to_status: ReportStatus, detail: str) -> None:
    from_status=report.status
    report.status=to_status
    db.add(LifecycleEvent(
        report_id=report.id,
        from_status=from_status,
        to_status=to_status,
        detail=detail 
    ))
    await db.flush()

async def run_knowledge(
    report_id: uuid.UUID,
    db: AsyncSession,
    redis: aioredis.Redis
) -> ActionPlan | None:
    settings = get_settings()
    report = await db.get(Report, report_id)

    if not report:
        logger.error("knowledge_report_not_found", report_id=str(report_id))
        return None
    
    if not report.perception_result:
        logger.error("knowledge_no_perception_result", report_id=str(report_id))
        await _transition(db, report, ReportStatus.FAILED, "No perception result found")
        await db.commit()
        return None

    perception = PerceptionResult.model_validate(report.perception_result)
    issue_types = [i.type for i in perception.issues]

    if not issue_types:
        logger.info("knowledge_no_issues_detected", report_id=str(report_id))
        plan=ActionPlan(
            report_id=report_id,
            issue_type="none",
            statute_ref=None,
            severity="low",
            recommended_tools=[],
            context_summary="No civic issues were detected in this image. No action required.",
            requires_human_review=False 
        )
        report.action_plan=plan.model_dump(mode="json")
        await _transition(db, report, ReportStatus.ACTIONED, "No issues detected - closed")
        await db.commit()
        return plan 
    cache_key=_cache_key(issue_types)
    cached=await redis.get(cache_key)

    if cached:
        try:
            cached_data = json.loads(cached)
            cached_data["report_id"] = str(report_id)
            plan = ActionPlan.model_validate(cached_data)
            logger.info("rag_cache_hit", report_id=str(report_id), cache_key=cache_key)
            report.action_plan = plan.model_dump(mode="json")
            await _transition(db,report,ReportStatus.ANALYZED, "ActionPlan loaded from cache")
            await db.commit()
            await redis.rpush(settings.action_queue_key, str(report_id))
            return plan
        except Exception as exc:
            logger.warning("rag_cache_invalid", error=str(exc))
    
    rag_query = f"regulations and laws for: {','.join(issue_types)}"
    try:
        context_chunks = await query_collection(rag_query,n_results=settings.rag_top_k)
        logger.info(
            "rag_query_complete",
            report_id=str(report_id),
            chunks_retrieved=len(context_chunks)
        )
    except Exception as exc:
        logger.error(
            "rag_query_failed",
            report_id=str(report_id),
            error=str(exc)
        )
        context_chunks=[]
    
    try:
        plan = await build_action_plan(perception, context_chunks)
    except ValueError as exc:
        logger.error(
            "knowledge_gemini_failed",
            report_id=str(report_id),
            error=str(exc)
        )
        db.add(DeadLetterQueue(
            report_id=report_id,
            phase="knowledge",
            error_detail=str(exc),
            retry_count=2
        ))
        await _transition(
            db, report, ReportStatus.PENDING_REVIEW,
            "Gemini ActionPlan validation failed - routed to human review"
        )
        await db.commit()
        return None

    if plan.requires_human_review:
        logger.info("knowledge_human_review_flagged", report_id=str(report_id))
        report.action_plan=plan.model_dump(mode="json")
        await _transition(
            db, report, ReportStatus.PENDING_REVIEW, f"Gemini flagged ambiguous statute for: {plan.issue_type}"
        )
        await db.commit()
        return None

    report.action_plan=plan.model_dump(mode="json")
    await _transition(db, report, ReportStatus.ANALYZED, f"ActionPlan built: {plan.issue_type}")
    await db.commit()

    # Write to cache - exclude report_id so it's reusable across reports
    cacheable = plan.model_dump(mode="json")
    cacheable.pop("report_id",None)
    await redis.set(cache_key, json.dumps(cacheable), ex=settings.rag_cache_ttl_seconds)
    logger.info("rag_cache_written", cache_key=cache_key, ttl=settings.rag_cache_ttl_seconds)

    await redis.rpush(settings.action_queue_key, str(report_id))
    logger.info("knowledge_complete", report_id=str(report_id), issue_type=plan.issue_type)

    return plan 