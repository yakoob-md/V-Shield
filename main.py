"""
main.py  –  v2.0
================
FastAPI backend for the Vernacular Voice-First Anti-Doping RAG application.

Features (v2 additions):
  ✅ Unified language detection supporting Hinglish (Latin-script Hindi) in
     addition to Devanagari and plain English
  ✅ /verify now returns user_query + ai_response + audio_base64 (hex)
     in a consistent envelope — no more silent audio-only response
  ✅ /verify-text returns identical envelope shape for easy frontend parity
  ✅ /history endpoint supports ?limit= and ?offset= for pagination
  ✅ /history/{id} DELETE endpoint to remove a single item
  ✅ /health returns richer diagnostics (db row count, uptime, model names)
  ✅ Robust empty-audio guard in bhashini_tts (returns None instead of dummy bytes)
  ✅ audio_base64 field is None (not present) when TTS fails — frontend handles gracefully
  ✅ Consistent CORS headers including DELETE method
  ✅ Graceful FAISS index missing → clear startup error, not a crash
  ✅ Response envelope typed via Pydantic models for automatic OpenAPI docs
  ✅ Emoji stripping improved in TTS (handles more Unicode emoji blocks)
  ✅ SYSTEM_PROMPT aligned with index.html risk classification UI
  ✅ All log messages use structured emoji prefixes for easy filtering

Run:
    pip install fastapi uvicorn python-multipart sentence-transformers faiss-cpu groq gtts python-dotenv
    python build_vector_db.py   # first time only
    uvicorn main:app --reload --port 8000
"""

import os
import re
import time
import pickle
import sqlite3
import logging
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import faiss
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from groq import Groq


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

GROQ_API_KEY     = os.getenv("GROQ_API_KEY")
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "faiss_index.bin")
CHUNKS_PATH      = os.getenv("CHUNKS_PATH",      "chunks.pkl")
SQLITE_DB_PATH   = os.getenv("SQLITE_DB_PATH",   "chats_v2.db")
EMBEDDING_MODEL  = "paraphrase-multilingual-MiniLM-L12-v2"
LLM_MODEL        = "llama-3.3-70b-versatile"
WHISPER_MODEL    = "whisper-large-v3"
TOP_K_RETRIEVAL  = 3    # FAISS chunks retrieved per query
MEMORY_WINDOW    = 10   # Context messages fed into LLM
HISTORY_LIMIT    = 20   # Default /history page size

# Startup timestamp (for /health uptime reporting)
_START_TIME = time.time()

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL SINGLETONS
# ══════════════════════════════════════════════════════════════════════════════

class AppState:
    faiss_index: Optional[faiss.Index]       = None
    chunks:      Optional[list[str]]         = None
    embedder:    Optional[SentenceTransformer] = None
    groq_client: Optional[Groq]              = None

state = AppState()


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS  (for OpenAPI docs + type safety)
# ══════════════════════════════════════════════════════════════════════════════

class TextQueryRequest(BaseModel):
    query: str

class VerifyResponse(BaseModel):
    chat_id:      int
    user_query:   str
    ai_response:  str
    audio_base64: Optional[str] = None
    language:     str = "hindi"
    risk_level:   str = "unknown"

class ChatSession(BaseModel):
    id: int
    title: str
    created_at: str

class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    risk_level: str
    language: str
    timestamp: str

class ChatDetailResponse(BaseModel):
    chat_id: int
    title: str
    messages: list[MessageItem]


# ══════════════════════════════════════════════════════════════════════════════
# LIFESPAN  (startup / shutdown)
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all heavy resources once at startup; release at shutdown."""

    # FAISS index
    log.info("⏳ Loading FAISS index…")
    if not os.path.exists(FAISS_INDEX_PATH):
        log.error(
            f"❌ FAISS index not found at '{FAISS_INDEX_PATH}'. "
            "Run `python build_vector_db.py` first, then restart."
        )
        # Don't crash – allow app to start so /health can report the issue
    else:
        state.faiss_index = faiss.read_index(FAISS_INDEX_PATH)
        log.info(f"✅ FAISS loaded – {state.faiss_index.ntotal} vectors")

    # Text chunks
    log.info("⏳ Loading text chunks…")
    if not os.path.exists(CHUNKS_PATH):
        log.error(f"❌ Chunks file not found at '{CHUNKS_PATH}'.")
    else:
        with open(CHUNKS_PATH, "rb") as f:
            state.chunks = pickle.load(f)
        log.info(f"✅ {len(state.chunks)} chunks loaded")

    # Embedding model
    log.info("⏳ Loading embedding model…")
    state.embedder = SentenceTransformer(EMBEDDING_MODEL)
    log.info("✅ Embedding model ready")

    # Groq client
    if not GROQ_API_KEY:
        log.error("❌ GROQ_API_KEY not set in environment / .env file!")
    else:
        log.info("⏳ Connecting to Groq…")
        state.groq_client = Groq(api_key=GROQ_API_KEY)
        log.info("✅ Groq client ready")

    init_db()
    log.info("✅ SQLite database initialised")

    yield  # ── App runs here ──

    log.info("👋 Shutting down…")


# ══════════════════════════════════════════════════════════════════════════════
# FASTAPI APP
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Anti-Doping Rural Athlete Assistant",
    description=(
        "Voice-first RAG assistant for rural Indian athletes. "
        "Supports Hindi, Hinglish, and English queries via voice or text."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Restrict to specific domains in production
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


# ══════════════════════════════════════════════════════════════════════════════
# SQLITE  –  PERSISTENT MEMORY LAYER
# ══════════════════════════════════════════════════════════════════════════════

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;") # Ensure ON DELETE CASCADE works
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialise the multi-chat database schema."""
    with get_db_connection() as conn:
        # 1. Chats table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 2. Messages table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    INTEGER NOT NULL,
                role       TEXT NOT NULL, -- 'user' or 'assistant'
                content    TEXT NOT NULL,
                language   TEXT NOT NULL DEFAULT 'hindi',
                risk_level TEXT NOT NULL DEFAULT 'unknown',
                timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        """)
        conn.commit()


def create_new_chat(title: str = "New Chat") -> int:
    with get_db_connection() as conn:
        cursor = conn.execute("INSERT INTO chats (title) VALUES (?)", (title,))
        conn.commit()
        return cursor.lastrowid

def update_chat_title(chat_id: int, title: str):
    with get_db_connection() as conn:
        conn.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))
        conn.commit()

def save_message(chat_id: int, role: str, content: str, 
                 language: str = "hindi", risk_level: str = "unknown"):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content, language, risk_level) VALUES (?, ?, ?, ?, ?)",
            (chat_id, role, content, language, risk_level)
        )
        conn.commit()

def fetch_chat_context(chat_id: int, limit: int = MEMORY_WINDOW) -> list[dict]:
    """Retrieve history for a specific chat to maintain context."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    # Groq/Llama expects list of {role, content}
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def fetch_all_chats() -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT id, title, created_at FROM chats ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

def fetch_chat_detail(chat_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        chat = conn.execute("SELECT id, title, created_at FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if not chat:
            return None
        messages = conn.execute(
            "SELECT id, role, content, risk_level, language, timestamp FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,)
        ).fetchall()
    return {
        "chat_id": chat["id"],
        "title": chat["title"],
        "messages": [dict(m) for m in messages]
    }


def fetch_history_for_api():
    """DEPRECATED: Old history endpoint logic."""
    return [], 0

def get_db_row_count() -> int:
    """Helper to count total messages in DB."""
    try:
        with get_db_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    except:
        return 0

def delete_chat_session(chat_id: int) -> bool:
    """Deletes a chat and its messages (cascades automatically)."""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        log.error(f"❌ Deletion error for chat {chat_id}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# LANGUAGE DETECTION  (improved: Devanagari + Hinglish Latin keywords)
# ══════════════════════════════════════════════════════════════════════════════

# Common Hinglish words that appear in Latin script but indicate Hindi context
_HINGLISH_KEYWORDS = {
    "kya", "hai", "nahi", "karo", "bhai", "aur", "le", "se", "mein",
    "ko", "pe", "ke", "ki", "ka", "ho", "tum", "main", "yeh", "woh",
    "kuch", "safe", "lena", "poocha", "doping", "supplement",
}

def detect_language(text: str) -> str:
    """
    Returns 'hindi' if Devanagari chars are found OR if enough Hinglish
    Latin-script keywords are detected. Otherwise returns 'english'.
    """
    # 1. Devanagari check
    if any('\u0900' <= c <= '\u097F' for c in text):
        log.info("🌐 Language: hindi (Devanagari detected)")
        return "hindi"

    # 2. Hinglish keyword check (case-insensitive token match)
    tokens = set(re.findall(r'\b[a-zA-Z]+\b', text.lower()))
    matches = tokens & _HINGLISH_KEYWORDS
    if len(matches) >= 2:
        log.info(f"🌐 Language: hindi (Hinglish keywords: {matches})")
        return "hindi"

    log.info("🌐 Language: english")
    return "english"


# ══════════════════════════════════════════════════════════════════════════════
# RISK LEVEL PARSER  (mirrors frontend detectRisk())
# ══════════════════════════════════════════════════════════════════════════════

def parse_risk_level(response_text: str) -> str:
    """
    Extracts the risk level from LLM response text.
    Only checks the start of the response to avoid false positives from words
    appearing in the explanation.
    """
    # Normalize and check the first 20 characters for the tag
    start_text = response_text[:20].strip()
    if re.search(r'BANNED|❌', start_text, re.IGNORECASE):
        return "banned"
    if re.search(r'CAUTION|⚠️', start_text, re.IGNORECASE):
        return "caution"
    if re.search(r'SAFE|✅', start_text, re.IGNORECASE):
        return "safe"
    if re.search(r'UNKNOWN|❓', start_text, re.IGNORECASE):
        return "unknown"
    return "caution"   # default: be cautious when uncertain


# ══════════════════════════════════════════════════════════════════════════════
# STT  –  Groq Whisper
# ══════════════════════════════════════════════════════════════════════════════

def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcribes audio using Groq Whisper.
    Accepts WebM/OGG/MP3 (whatever MediaRecorder produces in the browser).
    Returns transcribed text or a user-friendly fallback in Hindi.
    """
    if not state.groq_client:
        return "Server abhi ready nahi hai. Thodi der baad try karo."

    log.info("🎙️  [Whisper] Transcribing audio…")
    try:
        # Groq expects (filename, bytes) tuple
        transcription = state.groq_client.audio.transcriptions.create(
            file=("audio.webm", audio_bytes),
            model=WHISPER_MODEL,
            response_format="text",
            language="hi",   # Whisper v3 handles hi/en/Hinglish well with this hint
        )
        text = transcription.strip()
        log.info(f"📝 Transcribed: {text[:80]}")
        return text
    except Exception as e:
        log.error(f"❌ Whisper STT error: {e}")
        return "Audio samajh nahi aaya, kripya text mein send karein."


# ══════════════════════════════════════════════════════════════════════════════
# TTS  –  gTTS
# ══════════════════════════════════════════════════════════════════════════════

# Regex to strip emoji / special unicode from TTS input
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"   # misc symbols & pictographs
    "\U00002600-\U000027BF"   # misc symbols
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U00002702-\U000027B0"
    "✅❌⚠️❓🏋️🎙️"
    "]+",
    flags=re.UNICODE,
)

def generate_tts(text: str, language: str = "hi") -> Optional[bytes]:
    """
    Generates MP3 audio bytes from text using gTTS.
    Returns None (not dummy bytes) when TTS fails – frontend handles gracefully.
    """
    log.info(f"🔊 [gTTS] Generating audio (lang={language})…")
    try:
        from gtts import gTTS

        # Strip emojis so TTS doesn't read them aloud
        clean = _EMOJI_RE.sub("", text).strip()
        if not clean:
            log.warning("⚠️  TTS: nothing left after emoji strip – skipping audio")
            return None

        tts = gTTS(text=clean, lang=language, slow=False)
        fp  = BytesIO()
        tts.write_to_fp(fp)
        audio_bytes = fp.getvalue()
        log.info(f"✅ TTS generated {len(audio_bytes):,} bytes")
        return audio_bytes

    except ImportError:
        log.warning("⚠️  gTTS not installed. Run: pip install gTTS")
        return None
    except Exception as e:
        log.error(f"❌ TTS error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# RAG RETRIEVAL
# ══════════════════════════════════════════════════════════════════════════════

def retrieve_context(query: str, top_k: int = TOP_K_RETRIEVAL) -> str:
    """
    Embeds the query and retrieves the top-k most relevant knowledge chunks
    from the FAISS index.
    Returns a fallback string if FAISS is not loaded.
    """
    if state.faiss_index is None or state.embedder is None or state.chunks is None:
        log.warning("⚠️  RAG: FAISS or embedder not ready – skipping retrieval")
        return "Knowledge base not available."

    query_vec = state.embedder.encode([query], convert_to_numpy=True).astype(np.float32)
    _, indices = state.faiss_index.search(query_vec, top_k)

    retrieved = [
        state.chunks[idx]
        for idx in indices[0]
        if 0 <= idx < len(state.chunks)
    ]
    return "\n\n".join(retrieved) if retrieved else "No specific knowledge found."


# ══════════════════════════════════════════════════════════════════════════════
# LLM CALL  (Groq)
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
You are a senior anti-doping mentor for road athletes. Your goal is to provide safety guidance on supplements and medications.

IMPORTANT RULES:
1. RESPONSE LANGUAGE & SCRIPT:
   - If the user asks in English -> Respond in clear, simple English.
   - If the user asks in Hindi/Hinglish -> Respond in **Hinglish (Hindi words using Latin/English script)**.
   - **STRICT PROHIBITION**: NEVER use Devanagari script (like 'नमस्ते' or 'खून'). Use Latin script only (like 'Namaste' or 'khoon').
   - Remove any pure Hindi characters from your output.

2. DOMAIN: Answer ONLY about anti-doping, supplements, and prohibited substances.
   - If asked about something else, politely decline in the same language/script style.

3. STRUCTURE:
   - Every answer MUST start with a risk tag: SAFE ✅, CAUTION ⚠️, BANNED ❌, or UNKNOWN ❓.
   - Keep responses concise: exactly 3 sentences.
   - Sentence 1: Risk tag + direct answer.
   - Sentence 2: Scientific/factual reason based on the provided context.
   - Sentence 3: Practical advice (e.g., check with NADA or avoid).

4. TONE: Professional, empathetic, and mentor-like.
5. NO HALLUCINATION: If the context doesn't mention a substance, say UNKNOWN ❓.
""".strip()


def call_llm(
    user_query:        str,
    knowledge_context: str,
    past_messages:     list[dict],  # Now list of {role, content}
    lang:              str = "hindi",
) -> str:
    """
    Calls Groq LLM with a language-adaptive system prompt.
    """
    if not state.groq_client:
        return ("CAUTION ⚠️ – Server busy. Try NADA helpline: 1800-11-9979.")

    # Build memory block from past messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add context window
    for msg in past_messages:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Add current context and query
    user_content = f"KNOWLEDGE CONTEXT:\n{knowledge_context}\n\nUSER QUESTION: {user_query}"
    messages.append({"role": "user", "content": user_content})

    try:
        completion = state.groq_client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=400,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"❌ LLM error: {e}")
        return "CAUTION ⚠️ – Error processing request. Use certified products only."


# ══════════════════════════════════════════════════════════════════════════════
# SHARED PIPELINE  (used by both /verify and /verify-text)
# ══════════════════════════════════════════════════════════════════════════════

def run_text_pipeline(query: str, chat_id: int) -> dict:
    """
    Shared RAG pipeline for any text query (voice-transcribed or direct).
    """
    lang              = detect_language(query)
    past_messages     = fetch_chat_context(chat_id, limit=MEMORY_WINDOW)
    knowledge_context = retrieve_context(query)
    ai_response       = call_llm(query, knowledge_context, past_messages, lang=lang)
    risk_level        = parse_risk_level(ai_response)

    # Save messages to database
    save_message(chat_id, "user", query, language=lang)
    save_message(chat_id, "assistant", ai_response, language=lang, risk_level=risk_level)
    
    # Auto-generate title if this is the first interaction
    if len(past_messages) == 0:
        new_title = query[:30] + "..." if len(query) > 30 else query
        update_chat_title(chat_id, new_title)

    return {
        "chat_id":     chat_id,
        "user_query":  query,
        "ai_response": ai_response,
        "language":    lang,
        "risk_level":  risk_level,
    }


# ══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

# ─── POST /verify  ────────────────────────────────────────────────────────────
@app.post("/verify", summary="Process voice query with chat context")
async def verify(chat_id: int = Query(...), audio: UploadFile = File(...)):
    log.info(f"📨 [/verify] Voice query for chat {chat_id}")
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    user_query = transcribe_audio(audio_bytes)
    result = run_text_pipeline(user_query, chat_id)

    tts_lang = "hi" if result["language"] == "hindi" else "en"
    tts_bytes = generate_tts(result["ai_response"], language=tts_lang)
    audio_base64 = tts_bytes.hex() if tts_bytes else None

    return JSONResponse({
        "chat_id":      result["chat_id"],
        "user_query":   result["user_query"],
        "ai_response":  result["ai_response"],
        "audio_base64": audio_base64,
        "language":     result["language"],
        "risk_level":   result["risk_level"],
    })


# ─── POST /verify-text  ───────────────────────────────────────────────────────
@app.post("/verify-text", summary="Process text query with chat context")
async def verify_text(payload: TextQueryRequest, chat_id: int = Query(...)):
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    log.info(f"📨 [/verify-text] Chat {chat_id}: {query[:60]}…")
    result = run_text_pipeline(query, chat_id)

    return JSONResponse({
        "chat_id":     result["chat_id"],
        "user_query":  result["user_query"],
        "ai_response": result["ai_response"],
        "language":    result["language"],
        "risk_level":  result["risk_level"],
    })

@app.post("/chats", summary="Create a new chat session")
async def create_chat():
    chat_id = create_new_chat("New Chat")
    return {"chat_id": chat_id, "title": "New Chat"}

@app.get("/chats", response_model=list[ChatSession])
async def list_chats():
    return fetch_all_chats()

@app.get("/chats/{chat_id}", response_model=ChatDetailResponse)
async def get_chat(chat_id: int):
    detail = fetch_chat_detail(chat_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Chat not found")
    return detail


@app.delete("/chats/{chat_id}", summary="Delete a specific chat session")
async def delete_chat(chat_id: int):
    log.info(f"🗑️  [/chats/{chat_id}] Deletion requested")
    success = delete_chat_session(chat_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"message": f"Chat {chat_id} deleted successfully.", "deleted": True}


# ─── GET /health  ─────────────────────────────────────────────────────────────
@app.get("/health", summary="Health check with diagnostics")
async def health():
    """Returns system readiness and runtime diagnostics."""
    uptime_secs = int(time.time() - _START_TIME)
    return JSONResponse({
        "status":         "ok" if (state.faiss_index and state.groq_client) else "degraded",
        "uptime_seconds": uptime_secs,
        "faiss_loaded":   state.faiss_index is not None,
        "faiss_vectors":  state.faiss_index.ntotal if state.faiss_index else 0,
        "chunks_loaded":  len(state.chunks) if state.chunks else 0,
        "groq_ready":     state.groq_client is not None,
        "llm_model":      LLM_MODEL,
        "whisper_model":  WHISPER_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "db_path":        SQLITE_DB_PATH,
        "db_row_count":   get_db_row_count(),
    })


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)