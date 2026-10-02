from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["ORDER_STATUS", "FIT_SIZE", "ORDER_AND_FIT", "RETURN_EXCHANGE", "OTHER"]


class Intent(BaseModel):
    category: Category = Field(description="What the customer is asking about")
    order_id: Optional[str] = Field(default=None, description="Order id the customer refers to, ONLY if it is in the provided list")
    confidence: float = Field(ge=0, le=1, description="0-1 confidence in the category")
    reason: str = Field(default="", description="One short sentence explaining the choice")


class DraftReply(BaseModel):
    reply_text: str = Field(description="Reply to the customer, Hinglish in Roman script")
    facts_used: list[str] = Field(default_factory=list, description="Facts copied from FACTS that the reply relies on")
    needs_human: bool = Field(default=False, description="True if FACTS cannot fully answer the question")
    human_reason: str = Field(default="", description="Why a human must check, if needs_human")


class Verdict(BaseModel):
    grounded: bool = Field(description="Every claim in the reply is supported by FACTS")
    answers_question: bool = Field(description="The reply addresses what the customer asked")
    issues: list[str] = Field(default_factory=list, description="Specific problems found")


class CopilotResult(BaseModel):
    run_id: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    category: Optional[str] = None
    confidence: Optional[float] = None
    order_id: Optional[str] = None
    facts: str = ""
    reply_text: str = ""
    needs_human: bool = False
    human_reason: str = ""
    issues: list[str] = Field(default_factory=list)
    rewrites: int = 0


# ---------- API request bodies ----------
class DraftRequest(BaseModel):
    phone: str = Field(min_length=3)
    message: str = Field(min_length=1)


class ApproveRequest(BaseModel):
    customer_id: str
    phone: str
    category: str = ""
    draft: str
    final: str = Field(min_length=1)
    needs_human: bool = False
    reason: str = ""
