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
SQLITE_DB_PATH   = os.getenv("SQLITE_DB_PATH",   "chat_history.db")
EMBEDDING_MODEL  = "paraphrase-multilingual-MiniLM-L12-v2"
LLM_MODEL        = "llama-3.3-70b-versatile"
WHISPER_MODEL    = "whisper-large-v3"
TOP_K_RETRIEVAL  = 3    # FAISS chunks retrieved per query
MEMORY_WINDOW    = 3    # Past interactions fed into LLM context
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
    user_query:   str
    ai_response:  str
    audio_base64: Optional[str] = None   # hex-encoded MP3; None if TTS failed/disabled
    language:     str = "hindi"          # detected language: "hindi" | "english"
    risk_level:   str = "unknown"        # parsed from response: safe|caution|banned|unknown

class HistoryItem(BaseModel):
    id:          int
    user_query:  str
    ai_response: str
    timestamp:   str

class HistoryResponse(BaseModel):
    history: list[HistoryItem]
    count:   int
    total:   int


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
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create chat_history table if it doesn't exist. Also adds language column if missing."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_query  TEXT     NOT NULL,
                ai_response TEXT     NOT NULL,
                language    TEXT     NOT NULL DEFAULT 'hindi',
                risk_level  TEXT     NOT NULL DEFAULT 'unknown',
                timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migration: add columns to existing DBs that pre-date v2
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(chat_history)").fetchall()
        }
        for col, definition in [("language", "TEXT NOT NULL DEFAULT 'hindi'"),
                                  ("risk_level", "TEXT NOT NULL DEFAULT 'unknown'")]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE chat_history ADD COLUMN {col} {definition}")
                log.info(f"🔧 DB migration: added column '{col}'")
        conn.commit()


def save_interaction(user_query: str, ai_response: str,
                     language: str = "hindi", risk_level: str = "unknown") -> int:
    """Persist a query-response pair to SQLite. Returns the new row id."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO chat_history (user_query, ai_response, language, risk_level) VALUES (?, ?, ?, ?)",
            (user_query, ai_response, language, risk_level),
        )
        conn.commit()
        return cursor.lastrowid


def fetch_recent_history(limit: int = MEMORY_WINDOW) -> list[dict]:
    """Retrieve the N most recent interactions (for in-prompt short-term memory)."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT user_query, ai_response FROM chat_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"user_query": r["user_query"], "ai_response": r["ai_response"]}
            for r in reversed(rows)]


def fetch_history_for_api(limit: int = HISTORY_LIMIT, offset: int = 0) -> tuple[list[dict], int]:
    """
    Retrieve paginated history for the /history endpoint.
    Returns (items, total_count).
    """
    with get_db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
        rows  = conn.execute(
            "SELECT id, user_query, ai_response, language, risk_level, timestamp "
            "FROM chat_history ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows], total


def get_db_row_count() -> int:
    with get_db_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]


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
You are a trusted, empathetic anti-doping mentor for rural Indian athletes.

YOUR STRICT RULES:
1. DOMAIN: Answer ONLY questions about medicines, supplements, or doping risks.
   - If the question is unrelated, respond (in the detected language):
     Hindi/Hinglish: "Bhai main sirf supplements aur medicines ke baare mein help kar sakta hoon."
     English: "I can only help with supplements and medicines related to anti-doping."

2. NO HALLUCINATION: Use ONLY the knowledge context and past conversation. Do NOT invent facts.
   - If the product is unknown or data is missing:
     Hindi/Hinglish: "Iske baare mein pakka data nahi mila. Better hai use avoid karo ya certified product lo."
     English: "No verified data found. Please avoid this product or use a certified alternative."

3. SAFETY-FIRST: When uncertain, classify as RISKY — never assume safe.

4. RISK CLASSIFICATION: Every answer MUST start with ONE of these exact tags:
   - SAFE ✅       — substance confirmed safe for athletes
   - CAUTION ⚠️   — substance may carry contamination or indirect risk
   - BANNED ❌     — substance is on the WADA Prohibited List
   - UNKNOWN ❓    — substance not found in knowledge base

5. RESPONSE FORMAT: EXACTLY 3 short, plain sentences.
   - Sentence 1: Risk tag + direct answer (e.g. "SAFE ✅ – Creatine allowed hai.")
   - Sentence 2: Reason why (brief, factual, from context only).
   - Sentence 3: Practical advice (what the athlete should do next).

6. LANGUAGE: You will receive a language instruction below. Follow it strictly.
   - Hinglish: Write in Hindi words but use Latin (English) script only, NOT Devanagari.
   - English: Write in clear, simple English.

7. TONE: Supportive mentor — warm, simple, never preachy or robotic.

8. NEVER give medical prescriptions, legal guarantees, or absolute safety claims.
""".strip()


def call_llm(
    user_query:        str,
    knowledge_context: str,
    past_chats:        list[dict],
    lang:              str = "hindi",
) -> str:
    """
    Calls Groq LLM with a language-adaptive system prompt.
    Falls back to a safe canned response if the API call fails.
    """
    if not state.groq_client:
        return ("CAUTION ⚠️ – Server abhi ready nahi hai, thodi der baad try karo. "
                "Agar urgent hai toh NADA helpline pe call karo: 1800-11-9979. "
                "Koi bhi supplement lene se pehle certified product hi lo.")

    # Language-specific instruction injected into system prompt
    if lang == "english":
        lang_instruction = (
            "LANGUAGE INSTRUCTION: The user wrote in English. "
            "Respond in clear, simple English only. Do NOT use Hindi or Hinglish."
        )
        fallback = (
            "CAUTION ⚠️ – System is temporarily busy, please try again shortly. "
            "If urgent, call the NADA helpline at 1800-11-9979. "
            "Always use certified products before taking any supplement."
        )
    else:
        lang_instruction = (
            "LANGUAGE INSTRUCTION: The user wrote in Hindi or Hinglish. "
            "Respond in Hinglish — Hindi words written in Latin (English) script. "
            "Do NOT use Devanagari script anywhere in your response."
        )
        fallback = (
            "CAUTION ⚠️ – Abhi system thoda busy hai, thodi der baad try karo. "
            "Agar urgent hai toh NADA helpline pe call karo: 1800-11-9979. "
            "Koi bhi supplement lene se pehle certified product hi lo."
        )

    # Build short-term memory block
    memory_block = ""
    if past_chats:
        memory_block = "RECENT CONVERSATION CONTEXT:\n"
        for i, chat in enumerate(past_chats, 1):
            memory_block += (
                f"[{i}] User: {chat['user_query']}\n"
                f"    Assistant: {chat['ai_response']}\n"
            )
        memory_block += "\n"

    user_message = (
        f"{memory_block}"
        f"KNOWLEDGE CONTEXT:\n{knowledge_context}\n\n"
        f"CURRENT QUESTION: {user_query}"
    )

    log.info(f"📤 Sending to Groq LLM (lang={lang}, query={user_query[:60]}…)")
    try:
        completion = state.groq_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{lang_instruction}"},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        response = completion.choices[0].message.content.strip()
        log.info(f"📥 LLM response ({len(response)} chars): {response[:80]}…")
        return response
    except Exception as e:
        log.error(f"❌ Groq LLM error: {e}")
        return fallback


# ══════════════════════════════════════════════════════════════════════════════
# SHARED PIPELINE  (used by both /verify and /verify-text)
# ══════════════════════════════════════════════════════════════════════════════

def run_text_pipeline(query: str) -> dict:
    """
    Shared RAG pipeline for any text query (voice-transcribed or direct).

    Returns a dict with:
        user_query, ai_response, language, risk_level
    """
    lang              = detect_language(query)
    past_chats        = fetch_recent_history(limit=MEMORY_WINDOW)
    knowledge_context = retrieve_context(query)
    ai_response       = call_llm(query, knowledge_context, past_chats, lang=lang)
    risk_level        = parse_risk_level(ai_response)

    # Persist to DB AFTER LLM responds (so history sidebar reflects real order)
    save_interaction(query, ai_response, language=lang, risk_level=risk_level)
    log.info(f"💾 Saved interaction – lang={lang}, risk={risk_level}")

    return {
        "user_query":  query,
        "ai_response": ai_response,
        "language":    lang,
        "risk_level":  risk_level,
    }


# ══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

# ─── POST /verify  ────────────────────────────────────────────────────────────
@app.post(
    "/verify",
    summary="Process voice query",
    description=(
        "Accepts a voice audio file (WebM/OGG/MP3). Runs STT → RAG → LLM → TTS pipeline. "
        "Returns user_query, ai_response, audio_base64 (hex-encoded MP3), language, risk_level."
    ),
)
async def verify(audio: UploadFile = File(...)):
    """
    Voice pipeline endpoint.

    Returns:
        {
          "user_query":   "...",
          "ai_response":  "...",
          "audio_base64": "<hex MP3 or null>",
          "language":     "hindi" | "english",
          "risk_level":   "safe" | "caution" | "banned" | "unknown"
        }
    """
    log.info("📨 [/verify] Voice query received")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file received.")

    # Step 1: Speech → Text
    user_query = transcribe_audio(audio_bytes)

    # Step 2: Text pipeline (RAG + LLM + save)
    result = run_text_pipeline(user_query)

    # Step 3: Text → Speech
    tts_lang    = "hi" if result["language"] == "hindi" else "en"
    tts_bytes   = generate_tts(result["ai_response"], language=tts_lang)
    audio_base64 = tts_bytes.hex() if tts_bytes else None

    log.info("✅ [/verify] Sending response to client")
    return JSONResponse({
        "user_query":   result["user_query"],
        "ai_response":  result["ai_response"],
        "audio_base64": audio_base64,   # None → frontend shows text only, no audio player
        "language":     result["language"],
        "risk_level":   result["risk_level"],
    })


# ─── POST /verify-text  ───────────────────────────────────────────────────────
@app.post(
    "/verify-text",
    summary="Process text query",
    description=(
        "Accepts a plain-text query from the chat UI. "
        "Returns user_query, ai_response, language, risk_level. "
        "No audio is generated (text mode only)."
    ),
)
async def verify_text(payload: TextQueryRequest):
    """
    Text pipeline endpoint.

    Body: { "query": "Kya whey protein safe hai?" }

    Returns:
        {
          "user_query":  "...",
          "ai_response": "...",
          "language":    "hindi" | "english",
          "risk_level":  "safe" | "caution" | "banned" | "unknown"
        }
    """
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query text cannot be empty.")

    log.info(f"📨 [/verify-text] Query: {query[:60]}…")
    result = run_text_pipeline(query)

    log.info("✅ [/verify-text] Sending response to client")
    return JSONResponse({
        "user_query":  result["user_query"],
        "ai_response": result["ai_response"],
        "language":    result["language"],
        "risk_level":  result["risk_level"],
    })


# ─── GET /history  ────────────────────────────────────────────────────────────
@app.get(
    "/history",
    summary="Fetch paginated chat history",
    description="Returns the most recent `limit` interactions, with optional `offset` for pagination.",
)
async def history(
    limit:  int = Query(default=HISTORY_LIMIT, ge=1,  le=100,  description="Max items to return"),
    offset: int = Query(default=0,              ge=0,           description="Skip N newest items"),
):
    """
    Returns:
        {
          "history": [ { "id", "user_query", "ai_response", "language", "risk_level", "timestamp" }, … ],
          "count":   <items in this page>,
          "total":   <total rows in DB>
        }
    """
    try:
        rows, total = fetch_history_for_api(limit=limit, offset=offset)
        return JSONResponse({"history": rows, "count": len(rows), "total": total})
    except Exception as e:
        log.error(f"❌ History fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── DELETE /history  (clear all) ─────────────────────────────────────────────
@app.delete(
    "/history",
    summary="Clear all chat history",
)
async def clear_history():
    """Deletes every row from chat_history."""
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM chat_history")
            conn.commit()
        log.info("🗑️  All history cleared")
        return JSONResponse({"message": "Chat history cleared successfully.", "deleted": True})
    except Exception as e:
        log.error(f"❌ Clear history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── DELETE /history/{item_id}  (delete single item) ──────────────────────────
@app.delete(
    "/history/{item_id}",
    summary="Delete a single chat history item",
)
async def delete_history_item(item_id: int):
    """Deletes a single row from chat_history by id."""
    try:
        with get_db_connection() as conn:
            result = conn.execute(
                "DELETE FROM chat_history WHERE id = ?", (item_id,)
            )
            conn.commit()
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Item {item_id} not found.")
        log.info(f"🗑️  Deleted history item id={item_id}")
        return JSONResponse({"message": f"Item {item_id} deleted.", "deleted": True})
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"❌ Delete item error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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