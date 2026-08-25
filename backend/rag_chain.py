"""
AskTube - rag_chain.py

Wires together the retriever, prompt, and Groq LLM to answer a question
about a specific YouTube video, using only the retrieved transcript chunks
as context (no hallucinated information).
"""

import os
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from vectorstore import get_or_create_vectorstore

PROMPT_TEMPLATE = """You are AskTube, an AI assistant that answers questions about YouTube videos.

Answer the user's question using only the provided transcript context.

If the answer cannot be found in the context, clearly say that the information is not available in the video transcript.

Keep the answer clear, accurate, and easy to understand.

Context:
{context}

Question:
{question}

Answer:"""


def _format_docs(docs) -> str:
    return "\n\n".join(doc.page_content for doc in docs)


def _get_llm() -> ChatGroq:
    model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    return ChatGroq(model=model_name, temperature=0.2)


def answer_question(video_id: str, question: str) -> str:
    """
    Runs the full RAG pipeline for a single question:
        video_id -> vector store (load or build) -> retriever
        -> relevant chunks -> prompt -> Groq LLM -> answer

    Raises TranscriptError (propagated from vectorstore/transcript modules)
    if the transcript could not be obtained.
    """
    store = get_or_create_vectorstore(video_id)
    retriever = store.as_retriever(search_kwargs={"k": 4})

    prompt = PromptTemplate.from_template(PROMPT_TEMPLATE)
    llm = _get_llm()

    chain = (
        {"context": retriever | _format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain.invoke(question)
