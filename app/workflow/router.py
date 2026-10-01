"""Stage 3: Demographic category router -> [WOMEN | KIDS | MEN] title & size extraction."""
import re

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableBranch, RunnableLambda

from app.schemas import TitleSize

_KIDS = re.compile(r"\b(kid|kids|child|children|boy|boys|girl|girls|infant|toddler|baby)\b", re.I)
_WOMEN = re.compile(r"\b(women|woman|womens|ladies|lady|female|w-drs)\b", re.I)

_GUIDANCE = {
    "WOMEN": "Women's sizes use S, M, L, XL, XXL or 'Free Size' (sarees, dupattas).",
    "KIDS": "Kids' sizes are age ranges such as 2-3Y, 4-5Y, 6-7Y, 8-9Y.",
    "MEN": "Men's sizes use S, M, L, XL, XXL, or numeric waist sizes for bottoms (e.g. 32).",
}


def detect_demographic(raw_text: str) -> str:
    """Keyword routing. Kids is checked first, then Women, default Men (same as the prototype)."""
    if _KIDS.search(raw_text):
        return "KIDS"
    if _WOMEN.search(raw_text):
        return "WOMEN"
    return "MEN"


def _branch_chain(llm, demographic: str) -> Runnable:
    parser = JsonOutputParser(pydantic_object=TitleSize)
    prompt = ChatPromptTemplate.from_template(
        "You are extracting for the " + demographic + " demographic category.\n"
        + _GUIDANCE[demographic] + "\n"
        "Extract the clean product title and the standard size from this raw product text:\n"
        "{raw_row}\n\n{format_instructions}"
    ).partial(format_instructions=parser.get_format_instructions())

    def tag(result: dict) -> dict:
        return {"demographic": demographic, **result}

    return prompt | llm | parser | RunnableLambda(tag)


def build_demographic_router(llm) -> Runnable:
    def is_(d: str):
        return lambda x: detect_demographic(x["raw_row"]) == d

    return RunnableBranch(
        (is_("WOMEN"), _branch_chain(llm, "WOMEN")),
        (is_("KIDS"), _branch_chain(llm, "KIDS")),
        _branch_chain(llm, "MEN"),  # default branch
    )
