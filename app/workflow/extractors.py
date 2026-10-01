"""Stage 1 (Color) and Stage 2 (Fabric): single-call extractors, no fan-out."""
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda


def _clean(text: str) -> str:
    return text.strip().strip("\"'`. \n")


def build_color_chain(llm) -> Runnable:
    prompt = ChatPromptTemplate.from_template(
        "Extract the primary product color as one word."
        "Map vague terms (bluish) to nearest standard color."
        "Reply with the word only.\n\nProduct text: {raw_row}"
    )
    return prompt | llm | StrOutputParser() | RunnableLambda(_clean)


def build_fabric_chain(llm) -> Runnable:
    prompt = ChatPromptTemplate.from_template(
        "Extract and standardize the main fabric/material from this text into a standard "
        "industry label (e.g. Cotton, Linen, Cotton Blend, Georgette, Silk). "
        "Reply with the label only.\n\nProduct text: {raw_row}"
    )
    return prompt | llm | StrOutputParser() | RunnableLambda(_clean)
