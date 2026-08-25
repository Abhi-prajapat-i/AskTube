"""
AskTube - vectorstore.py

Handles creation and loading of per-video FAISS vector stores.

Key idea (per spec section 7 - "Vector Store Optimization"):
    We must NOT re-embed a video's transcript every time a question is asked.
    Instead, each video gets its own FAISS index on disk, keyed by video ID:

        vectorstores/
            J5_-l7WIO_w/
            abc123xyz/
            xyz789abc/

    On each question:
        1. Check if vectorstores/<video_id>/ already exists.
        2. If yes -> load it directly.
        3. If no  -> fetch transcript, split into chunks, embed, save, then load.
"""

import os
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from transcript import fetch_transcript_text, TranscriptError

VECTORSTORE_ROOT = os.path.join(os.path.dirname(__file__), "vectorstores")

# A single shared embeddings model instance, reused across requests so we
# don't reload the HuggingFace model from disk on every call.
_embeddings = None


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return _embeddings


def _index_path(video_id: str) -> str:
    return os.path.join(VECTORSTORE_ROOT, video_id)


def _index_exists(video_id: str) -> bool:
    path = _index_path(video_id)
    # FAISS.save_local() writes an index.faiss and index.pkl file.
    return os.path.isdir(path) and os.path.exists(os.path.join(path, "index.faiss"))


def _build_and_save_index(video_id: str) -> FAISS:
    """
    Fetches the transcript, splits it into chunks, embeds those chunks, and
    saves the resulting FAISS index to disk under the video's own folder.
    """
    transcript_text = fetch_transcript_text(video_id)  # may raise TranscriptError

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )
    chunks = splitter.create_documents([transcript_text])

    if not chunks:
        raise TranscriptError("Could not split the transcript into usable chunks.")

    embeddings = _get_embeddings()
    store = FAISS.from_documents(chunks, embeddings)

    os.makedirs(VECTORSTORE_ROOT, exist_ok=True)
    store.save_local(_index_path(video_id))

    return store


def get_or_create_vectorstore(video_id: str) -> FAISS:
    """
    Returns a FAISS vector store for the given video ID, loading it from
    disk if it already exists, or building + saving a new one if not.
    """
    if _index_exists(video_id):
        embeddings = _get_embeddings()
        return FAISS.load_local(
            _index_path(video_id),
            embeddings,
            # Safe here: we only ever load indexes that AskTube itself wrote.
            allow_dangerous_deserialization=True,
        )

    return _build_and_save_index(video_id)
