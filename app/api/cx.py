"""CX Support Copilot endpoints: draft a reply for a customer message, log the agent's approval."""
import asyncio

from fastapi import APIRouter, Depends

from app import db
from app.cx import pipeline, store
from app.cx.chains import CxChains
from app.cx.schemas import ApproveRequest, CopilotResult, DraftRequest

router = APIRouter(prefix="/cx", tags=["cx"])


@router.post("/draft", response_model=CopilotResult)
async def draft(body: DraftRequest, chains: CxChains = Depends(pipeline.get_cx_chains)):
    """Identify the customer by phone, look up orders + approved catalogue, draft a Hinglish reply.
    Blocking calls (Supabase, LLM) run in a worker thread."""
    return await asyncio.to_thread(pipeline.run_copilot, body.phone, body.message, chains)


@router.post("/approve")
async def approve(body: ApproveRequest):
    """Log the agent's final text next to the AI draft. Sending via Freshdesk is not wired up yet."""
    await asyncio.to_thread(
        lambda: store.log_reply(
            db.get_client(), customer_id=body.customer_id, phone=body.phone, category=body.category,
            draft=body.draft, final=body.final, needs_human=body.needs_human, reason=body.reason))
    return {"status": "logged"}
