"""
Assembles the full diagram:

  [RAW VENDOR ROW]
        |
  RunnableParallel (fan-out) -> color | fabric | demographic router (WOMEN/KIDS/MEN)
        |
  fan-in merge -> Hinglish description & fit generator
        |
  [APPROVED LISTING OBJECT]
"""
from functools import lru_cache

from langchain_core.runnables import Runnable, RunnableLambda, RunnableParallel, RunnablePassthrough

from app.llm import get_llm
from app.schemas import ApprovedListingObject, ListingCopy
from app.workflow.extractors import build_color_chain, build_fabric_chain
from app.workflow.generator import build_generator_chain
from app.workflow.router import build_demographic_router


def build_workflow(llm) -> Runnable:
    # Stage 1-3: parallel fan-out
    parallel_stage = RunnableParallel(
        color=build_color_chain(llm),
        fabric=build_fabric_chain(llm),
        details=build_demographic_router(llm),
    )

    # Fan-in: flatten branch outputs into one dict
    def fan_in(x: dict) -> dict:
        d = x["details"]
        return {
            "color": x["color"],
            "fabric": x["fabric"],
            "demographic": d["demographic"],
            "title": d["title"],
            "size": d["size"],
        }

    # Stage 4 runs on merged data; keep merged fields alongside the generated copy
    with_copy = RunnablePassthrough.assign(copy=build_generator_chain(llm))

    # Final validation into the approved object (title/color/fabric come from the
    # extractors, NOT re-written by the generator, so they stay consistent)
    def assemble(x: dict) -> ApprovedListingObject:
        copy = ListingCopy.model_validate(x.pop("copy"))
        return ApprovedListingObject(**x, **copy.model_dump())

    return parallel_stage | RunnableLambda(fan_in) | with_copy | RunnableLambda(assemble)


@lru_cache
def get_workflow() -> Runnable:
    """FastAPI dependency. Raises MissingApiKeyError if no key is configured."""
    return build_workflow(get_llm())
