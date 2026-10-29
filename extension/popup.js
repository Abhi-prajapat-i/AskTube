const BACKEND_URL = "http://localhost:8000/ask";

// ---------------------------------------------------------------------------
// Video ID extraction
// ---------------------------------------------------------------------------

/**
 * Extracts a YouTube video ID from a URL.
 * Supports:
 *   https://www.youtube.com/watch?v=VIDEO_ID
 *   https://youtube.com/watch?v=VIDEO_ID
 *   https://youtu.be/VIDEO_ID
 *
 * Returns the video ID string, or null if the URL isn't a supported
 * YouTube video URL.
 */
function extractVideoId(url) {
  if (!url) return null;

  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "");

    if (host === "youtube.com" || host === "m.youtube.com") {
      if (parsed.pathname === "/watch") {
        const id = parsed.searchParams.get("v");
        return id && id.length > 0 ? id : null;
      }
      // Shorts also count as a "video" the user is watching.
      const shortsMatch = parsed.pathname.match(/^\/shorts\/([a-zA-Z0-9_-]+)/);
      if (shortsMatch) return shortsMatch[1];

      return null;
    }

    if (host === "youtu.be") {
      const id = parsed.pathname.replace(/^\//, "");
      return id.length > 0 ? id : null;
    }

    return null;
  } catch (err) {
    // Malformed URL.
    return null;
  }
}

// ---------------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------------

const statusEl = document.getElementById("video-status");
const statusIconEl = document.getElementById("status-icon");
const statusTextEl = document.getElementById("status-text");

const videoMetaEl = document.getElementById("video-meta");
const videoIdBadgeEl = document.getElementById("video-id-badge");

const questionInput = document.getElementById("question-input");
const askButton = document.getElementById("ask-button");
const askButtonLabel = document.getElementById("ask-button-label");

const loadingStateEl = document.getElementById("loading-state");
const errorStateEl = document.getElementById("error-state");
const errorTextEl = document.getElementById("error-text");

const answerSectionEl = document.getElementById("answer-section");
const answerTextEl = document.getElementById("answer-text");

let currentVideoId = null;

// ---------------------------------------------------------------------------
// UI state helpers
// ---------------------------------------------------------------------------

function setVideoDetected(videoId) {
  currentVideoId = videoId;

  statusEl.classList.remove("status-warn");
  statusEl.classList.add("status-ok");
  statusIconEl.textContent = "✓";
  statusTextEl.textContent = "YouTube video detected";

  videoMetaEl.classList.remove("hidden");
  videoIdBadgeEl.textContent = truncateId(videoId);

  questionInput.disabled = false;
  askButton.disabled = false;
}

function setVideoNotDetected() {
  currentVideoId = null;

  statusEl.classList.remove("status-ok");
  statusEl.classList.add("status-warn");
  statusIconEl.textContent = "⚠";
  statusTextEl.textContent = "Please open a YouTube video first.";

  videoMetaEl.classList.add("hidden");

  questionInput.disabled = true;
  askButton.disabled = true;
}

function truncateId(id) {
  return id.length > 16 ? id.slice(0, 16) + "…" : id;
}

function showLoading(isLoading) {
  loadingStateEl.classList.toggle("hidden", !isLoading);
  askButton.disabled = isLoading || !currentVideoId;
  askButtonLabel.textContent = isLoading ? "Thinking" : "Ask";
}

function showError(message) {
  errorTextEl.textContent = message;
  errorStateEl.classList.remove("hidden");
}

function clearError() {
  errorStateEl.classList.add("hidden");
  errorTextEl.textContent = "";
}

function showAnswer(text) {
  // Render Markdown (bold, tables, lists) and sanitize it, since the text
  // comes from an LLM and must never be trusted as raw HTML.
  answerTextEl.innerHTML = DOMPurify.sanitize(marked.parse(text));
  answerSectionEl.classList.remove("hidden");
}

function clearAnswer() {
  answerSectionEl.classList.add("hidden");
  answerTextEl.textContent = "";
}

// ---------------------------------------------------------------------------
// Backend communication
// ---------------------------------------------------------------------------

async function askBackend(videoId, question) {
  const response = await fetch(BACKEND_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId, question }),
  });

  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    // Response wasn't valid JSON at all.
  }

  if (!response.ok) {
    const detail = data && data.detail ? data.detail : "Something went wrong. Please try again.";
    throw new Error(detail);
  }

  if (!data || typeof data.answer !== "string") {
    throw new Error("Something went wrong. Please try again.");
  }

  return data.answer;
}

// ---------------------------------------------------------------------------
// Event handlers
// ---------------------------------------------------------------------------

async function handleAsk() {
  const question = questionInput.value.trim();
  if (!question || !currentVideoId) return;

  clearError();
  clearAnswer();
  showLoading(true);

  try {
    const answer = await askBackend(currentVideoId, question);
    showAnswer(answer);
  } catch (err) {
    // Never surface raw technical details — err.message is already a
    // friendly string from either our backend or askBackend()'s fallback.
    showError(err.message || "Something went wrong. Please try again.");
  } finally {
    showLoading(false);
  }
}

askButton.addEventListener("click", handleAsk);

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!askButton.disabled) {
      handleAsk();
    }
  }
  // Shift+Enter falls through and inserts a newline as normal.
});

// ---------------------------------------------------------------------------
// Init: detect the current tab's video on popup open
// ---------------------------------------------------------------------------

function init() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const url = tabs && tabs[0] ? tabs[0].url : null;
    const videoId = extractVideoId(url);

    if (videoId) {
      setVideoDetected(videoId);
    } else {
      setVideoNotDetected();
    }
  });
}

init();
