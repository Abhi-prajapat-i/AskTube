"""
AskTube - transcript.py

Handles fetching YouTube video transcripts.

Responsibilities:
    - Fetch a transcript for a given YouTube video ID.
    - Try a preferred list of languages (e.g. English, then Hindi).
    - Convert transcript-related failures into clear, user-friendly errors
      instead of letting raw library exceptions bubble up to the API layer.

Uses youtube-transcript-api >= 1.0, which exposes an instance-based API
(YouTubeTranscriptApi().list(video_id) / .fetch(video_id)) rather than the
older static YouTubeTranscriptApi.list_transcripts(...) methods.

Every exception class the library can raise (as of 1.2.4) is handled
explicitly below with its own friendly message, and the real exception is
always logged first via logger.exception(...) so the backend terminal shows
the true cause, not just the generic fallback message.
"""

import logging
import os
from typing import List

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    AgeRestricted,
    CookieError,
    CouldNotRetrieveTranscript,
    HTTPError,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    NotTranslatable,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    TranslationLanguageNotAvailable,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeDataUnparsable,
    YouTubeRequestFailed,
)

logger = logging.getLogger("asktube")

_ytt_api = YouTubeTranscriptApi()


class TranscriptError(Exception):
    """
    Raised whenever we cannot produce a transcript for a video.

    The `message` attribute is always safe to show directly to the end user
    (no stack traces, no internal library details).
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _get_preferred_languages() -> List[str]:
    """
    Reads the ordered list of transcript languages to try from the
    TRANSCRIPT_LANGUAGES env var (comma separated), falling back to
    English and Hindi as sensible defaults.
    """
    raw = os.getenv("TRANSCRIPT_LANGUAGES", "en,hi")
    return [lang.strip() for lang in raw.split(",") if lang.strip()]


def _friendly_message_for(exc: Exception) -> str:
    """
    Maps a caught exception from youtube-transcript-api to a single
    friendly, user-safe message. Always logs the real exception first.
    """
    logger.exception("youtube-transcript-api error: %s", type(exc).__name__)

    if isinstance(exc, TranscriptsDisabled):
        return "Transcripts are disabled for this video, so AskTube can't answer questions about it."
    if isinstance(exc, (VideoUnavailable, VideoUnplayable)):
        return "This video appears to be unavailable. Please check the link and try again."
    if isinstance(exc, InvalidVideoId):
        return "That doesn't look like a valid YouTube video ID."
    if isinstance(exc, AgeRestricted):
        return "This video is age-restricted, so AskTube can't access its transcript."
    if isinstance(exc, (RequestBlocked, IpBlocked, PoTokenRequired)):
        return (
            "YouTube is currently blocking automated transcript requests from this "
            "network. This is a known limitation of the underlying transcript "
            "library — try again later, from a different network, or with a "
            "residential proxy configured on the backend."
        )
    if isinstance(exc, YouTubeDataUnparsable):
        return "YouTube returned data AskTube couldn't understand. Please try again shortly."
    if isinstance(exc, (YouTubeRequestFailed, HTTPError)):
        return "AskTube couldn't reach YouTube right now. Please check your connection and try again."
    if isinstance(exc, CookieError):
        return "AskTube ran into a cookie/authentication issue trying to reach this video."
    if isinstance(exc, (NotTranslatable, TranslationLanguageNotAvailable)):
        return "A transcript exists for this video, but not in a usable language."
    if isinstance(exc, CouldNotRetrieveTranscript):
        return "AskTube couldn't retrieve a transcript for this video right now. Please try again later."

    return "Something went wrong while contacting YouTube. Please try again."


def fetch_transcript_text(video_id: str) -> str:
    """
    Fetches the transcript for a YouTube video and returns it as a single
    plain-text string (transcript segments joined with spaces).

    Raises:
        TranscriptError: with a friendly message describing what went wrong.
        The real underlying exception is always logged server-side first.
    """
    preferred_languages = _get_preferred_languages()

    try:
        transcript_list = _ytt_api.list(video_id)
    except Exception as exc:
        raise TranscriptError(_friendly_message_for(exc))

    # First, try to find a transcript in one of our preferred languages
    # (manually created transcripts are generally higher quality than
    # auto-generated ones, so we check for those first).
    transcript = None
    try:
        transcript = transcript_list.find_transcript(preferred_languages)
    except NoTranscriptFound:
        # Fall back to ANY available transcript, and translate it to our
        # first preferred language if translation is supported.
        try:
            available = list(transcript_list)
            if not available:
                raise NoTranscriptFound(video_id, preferred_languages, transcript_list)
            fallback = available[0]
            if fallback.is_translatable and preferred_languages:
                transcript = fallback.translate(preferred_languages[0])
            else:
                transcript = fallback
        except NoTranscriptFound:
            raise TranscriptError(
                "No transcript is available in the requested language(s) "
                f"({', '.join(preferred_languages)}) for this video."
            )
        except Exception as exc:
            raise TranscriptError(_friendly_message_for(exc))

    try:
        fetched = transcript.fetch()
    except Exception as exc:
        raise TranscriptError(_friendly_message_for(exc))

    def _segment_text(segment) -> str:
        # Support both the new FetchedTranscriptSnippet objects and plain
        # dicts, in case of library version differences.
        if isinstance(segment, dict):
            return segment.get("text", "").strip()
        return getattr(segment, "text", "").strip()

    full_text = " ".join(text for text in (_segment_text(s) for s in fetched) if text)

    if not full_text:
        raise TranscriptError("The transcript for this video appears to be empty.")

    return full_text
