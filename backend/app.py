"""
AskTube - app.py

FastAPI backend entry point.

Exposes:
    POST /ask   -> answer a question about a specific YouTube video
    GET  /health -> simple health check

Run with:
    uvicorn app:app --reload --port 8000
"""

import logging

from dotenv import load_dotenv
load_dotenv()  # Must run before importing modules that read env vars (e.g. Groq key).

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from transcript import TranscriptError
from rag_chain import answer_question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("asktube")

app = FastAPI(title="AskTube API", version="1.0.0")

# --------------------------------------------------------------------------
# CORS
#
# Chrome extensions call the backend from an "chrome-extension://<id>"
# origin, not a regular http(s) origin. For local development we allow all
# origins so the extension works regardless of the (locally-generated)
# extension ID. In production, replace this with the extension's exact
# "chrome-extension://<your-extension-id>" origin instead of "*".
# --------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to your extension's origin in production
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


class QuestionRequest(BaseModel):
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    question: str = Field(..., min_length=1, description="User's question about the video")


class QuestionResponse(BaseModel):
    answer: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=QuestionResponse)
def ask(payload: QuestionRequest):
    video_id = payload.video_id.strip()
    question = payload.question.strip()

    try:
        answer = answer_question(video_id, question)
        return QuestionResponse(answer=answer)

    except TranscriptError as e:
        # Known, user-friendly error (missing transcript, disabled, etc).
        logger.warning("Transcript error for video_id=%s: %s", video_id, e.message)
        return JSONResponse(status_code=422, content={"detail": e.message})

    except Exception:
        # Catch-all: never leak stack traces / internal details to the client.
        logger.exception("Unexpected error answering question for video_id=%s", video_id)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong. Please try again."},
        )
