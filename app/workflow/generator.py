"""Stage 4: Hinglish description & fit generator (Pydantic schema for copy + fit guidance)."""
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.schemas import ListingCopy


def build_generator_chain(llm) -> Runnable:
    parser = JsonOutputParser(pydantic_object=ListingCopy)
    prompt = ChatPromptTemplate.from_template(
        "You are an e-commerce copywriter for an Indian fashion marketplace.\n\n"
        "Product details:\n"
        "- Title: {title}\n"
        "- Demographic: {demographic}\n"
        "- Size: {size}\n"
        "- Color: {color}\n"
        "- Fabric: {fabric}\n\n"
        "Instructions:\n"
        "1. Write a clear, natural product description in plain English.\n"
        "2. Write an engaging product description in Hinglish (a natural blend of Hindi and English).\n"
        "3. Provide specific, practical fit guidance for buyers.\n\n"
        "{format_instructions}"
    ).partial(format_instructions=parser.get_format_instructions())
    return prompt | llm | parser
