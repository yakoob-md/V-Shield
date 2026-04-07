"""
main.py  –  v2.0
================
FastAPI backend for the Vernacular Voice-First Anti-Doping RAG application.
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
from functools import lru_cache

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import faiss
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Response
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
# PYDANTIC MODELS
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
# LIFESPAN
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("⏳ Loading FAISS index…")
    if not os.path.exists(FAISS_INDEX_PATH):
        log.error(f"❌ FAISS index not found at '{FAISS_INDEX_PATH}'.")
    else:
        state.faiss_index = faiss.read_index(FAISS_INDEX_PATH)
        log.info(f"✅ FAISS loaded – {state.faiss_index.ntotal} vectors")

    log.info("⏳ Loading text chunks…")
    if not os.path.exists(CHUNKS_PATH):
        log.error(f"❌ Chunks file not found at '{CHUNKS_PATH}'.")
    else:
        with open(CHUNKS_PATH, "rb") as f:
            state.chunks = pickle.load(f)
        log.info(f"✅ {len(state.chunks)} chunks loaded")

    log.info("⏳ Loading embedding model…")
    state.embedder = SentenceTransformer(EMBEDDING_MODEL)
    log.info("✅ Embedding model ready")

    if not GROQ_API_KEY:
        log.error("❌ GROQ_API_KEY not set!")
    else:
        log.info("⏳ Connecting to Groq…")
        state.groq_client = Groq(api_key=GROQ_API_KEY)
        log.info("✅ Groq client ready")

    init_db()
    log.info("✅ SQLite database initialised")

    yield

    log.info("👋 Shutting down…")


# ══════════════════════════════════════════════════════════════════════════════
# FASTAPI APP
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Anti-Doping Rural Athlete Assistant",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


# ══════════════════════════════════════════════════════════════════════════════
# SQLITE
# ══════════════════════════════════════════════════════════════════════════════

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    INTEGER NOT NULL,
                role       TEXT NOT NULL,
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

def save_message(chat_id: int, role: str, content: str, language: str = "hindi", risk_level: str = "unknown"):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content, language, risk_level) VALUES (?, ?, ?, ?, ?)",
            (chat_id, role, content, language, risk_level)
        )
        conn.commit()

def fetch_chat_context(chat_id: int, limit: int = MEMORY_WINDOW) -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def fetch_all_chats() -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT id, title, created_at FROM chats ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

def fetch_chat_detail(chat_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        chat = conn.execute("SELECT id, title, created_at FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if not chat: return None
        messages = conn.execute(
            "SELECT id, role, content, risk_level, language, timestamp FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,)
        ).fetchall()
    return {"chat_id": chat["id"], "title": chat["title"], "messages": [dict(m) for m in messages]}

def delete_chat_session(chat_id: int) -> bool:
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        log.error(f"❌ Deletion error: {e}")
        return False

def get_db_row_count() -> int:
    try:
        with get_db_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    except: return 0


# ══════════════════════════════════════════════════════════════════════════════
# LOGIC HELPERS
# ══════════════════════════════════════════════════════════════════════════════

_HINGLISH_KEYWORDS = {"kya", "hai", "nahi", "karo", "bhai", "aur", "le", "se", "mein", "ko", "pe", "ke", "ki", "ka", "ho", "tum", "main", "yeh", "woh", "kuch", "safe", "lena", "poocha", "doping", "supplement"}

def strip_devanagari(text: str) -> str:
    """Removes pure Devanagari characters from the string."""
    return re.sub(r'[\u0900-\u097F]+', '', text).strip()

def detect_language(text: str) -> str:
    if any('\u0900' <= c <= '\u097F' for c in text): return "hindi"
    tokens = set(re.findall(r'\b[a-zA-Z]+\b', text.lower()))
    if len(tokens & _HINGLISH_KEYWORDS) >= 2: return "hindi"
    return "english"

def parse_risk_level(response_text: str) -> str:
    start_text = response_text[:20].strip()
    if re.search(r'BANNED|❌', start_text, re.IGNORECASE): return "banned"
    if re.search(r'CAUTION|⚠️', start_text, re.IGNORECASE): return "caution"
    if re.search(r'SAFE|✅', start_text, re.IGNORECASE): return "safe"
    if re.search(r'UNKNOWN|❓', start_text, re.IGNORECASE): return "unknown"
    return "caution"


# ══════════════════════════════════════════════════════════════════════════════
# STT / TTS
# ══════════════════════════════════════════════════════════════════════════════

def transcribe_audio(audio_bytes: bytes) -> str:
    if not state.groq_client: return "Server busy."
    try:
        transcription = state.groq_client.audio.transcriptions.create(
            file=("audio.webm", audio_bytes),
            model=WHISPER_MODEL,
            response_format="text",
            language="hi",
        )
        return transcription.strip()
    except Exception as e:
        log.error(f"❌ Whisper error: {e}")
        return "Audio samajh nahi aaya."

_EMOJI_RE = re.compile(r"[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0000FE00-\U0000FE0F✅❌⚠️❓🏋️🎙️]+", flags=re.UNICODE)

@lru_cache(maxsize=128)
def generate_tts(text: str, language: str = "hi") -> Optional[bytes]:
    try:
        from gtts import gTTS
        clean = _EMOJI_RE.sub("", text).strip()
        if not clean: return None
        tts = gTTS(text=clean, lang=language, slow=False)
        fp  = BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
    except Exception as e:
        log.error(f"❌ TTS error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# RAG & LLM
# ══════════════════════════════════════════════════════════════════════════════

def retrieve_context(query: str, top_k: int = TOP_K_RETRIEVAL) -> str:
    if state.faiss_index is None or state.embedder is None: return ""
    query_vec = state.embedder.encode([query], convert_to_numpy=True).astype(np.float32)
    _, indices = state.faiss_index.search(query_vec, top_k)
    retrieved = [state.chunks[idx] for idx in indices[0] if 0 <= idx < len(state.chunks)]
    return "\n\n".join(retrieved)

SYSTEM_PROMPT = """
You are a senior anti-doping mentor for road athletes. Your goal is to provide safety guidance on supplements and medications.

STRICT INSTRUCTION: YOUR KEYBOARD HAS NO HINDI LETTERS.
1. RESPONSE LANGUAGE & SCRIPT:
   - If user asks in English -> Response: English.
   - If user asks in Hindi/Hinglish -> Response: **Hinglish (Hindi words in English/Latin script)**.
   - **MANDATORY**: NEVER use Devanagari script (e.g. नमस्ते). ONLY use Latin letters (e.g. Namaste).
   - If you accidentally output a Hindi character, the system will break. Use ROMAN script only.

2. CONTEXT & MEMORY:
   - You will be provided with "KNOWLEDGE CONTEXT" (scientific facts) and "CONVERSATION HISTORY".
   - Use history to understand follow-up questions (e.g., "it", "them").
   - If the user's current query references something previously discussed, use that context.

3. DOMAIN: Answer ONLY about anti-doping, supplements, and prohibited substances.
   - If asked about something else, politely decline in the same language/script style.

4. STRUCTURE:
   - Every answer MUST start with a risk tag: SAFE ✅, CAUTION ⚠️, BANNED ❌, or UNKNOWN ❓.
   - Keep responses concise: exactly 3 sentences.
   - Sentence 1: Risk tag + direct answer.
   - Sentence 2: Scientific/factual reason based on the provided context.
   - Sentence 3: Practical advice.

5. NO HALLUCINATION: If the context doesn't mention a substance and it's not in your memory, say UNKNOWN ❓.
""".strip()

def call_llm(user_query: str, knowledge_context: str, past_messages: list[dict], lang: str = "hindi") -> str:
    if not state.groq_client: return "CAUTION ⚠️ – Server busy."
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in past_messages: messages.append({"role": msg["role"], "content": msg["content"]})
    if knowledge_context:
        messages.append({"role": "system", "content": f"KNOWLEDGE CONTEXT: {knowledge_context}"})
    messages.append({"role": "user", "content": user_query})
    try:
        completion = state.groq_client.chat.completions.create(model=LLM_MODEL, messages=messages, temperature=0.4, max_tokens=400)
        return completion.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"❌ LLM error: {e}")
        return "CAUTION ⚠️ – Error processing request."


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE & ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

def run_text_pipeline(query: str, chat_id: int) -> dict:
    lang              = detect_language(query)
    past_messages     = fetch_chat_context(chat_id)
    knowledge_context = retrieve_context(query)
    ai_response       = call_llm(query, knowledge_context, past_messages, lang=lang)
    
    # Filter Devanagari leakage
    if lang == "hindi":
        ai_response = strip_devanagari(ai_response)
        if not ai_response: # Fallback if everything was Devanagari
            ai_response = "CAUTION ⚠️ – Mujhse Hindi script mein baat na karein, English letters use karein. Please check with NADA certified products."

    risk_level        = parse_risk_level(ai_response)
    save_message(chat_id, "user", query, language=lang)
    save_message(chat_id, "assistant", ai_response, language=lang, risk_level=risk_level)
    if len(past_messages) == 0:
        new_title = query[:30] + "..." if len(query) > 30 else query
        update_chat_title(chat_id, new_title)
    return {"chat_id": chat_id, "user_query": query, "ai_response": ai_response, "language": lang, "risk_level": risk_level}

@app.post("/verify")
async def verify(chat_id: int = Query(...), audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    user_query = transcribe_audio(audio_bytes)
    result = run_text_pipeline(user_query, chat_id)
    tts_lang = "hi" if result["language"] == "hindi" else "en"
    tts_bytes = generate_tts(result["ai_response"], language=tts_lang)
    return JSONResponse({**result, "audio_base64": tts_bytes.hex() if tts_bytes else None})

@app.post("/verify-text")
async def verify_text(payload: TextQueryRequest, chat_id: int = Query(...)):
    result = run_text_pipeline(payload.query, chat_id)
    return JSONResponse(result)

@app.post("/chats")
async def create_chat():
    return {"chat_id": create_new_chat(), "title": "New Chat"}

@app.get("/chats", response_model=list[ChatSession])
async def list_chats():
    return fetch_all_chats()

@app.get("/chats/{chat_id}", response_model=ChatDetailResponse)
async def get_chat(chat_id: int):
    detail = fetch_chat_detail(chat_id)
    if not detail: raise HTTPException(status_code=404, detail="Chat not found")
    return detail

@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: int):
    if delete_chat_session(chat_id): return {"deleted": True}
    raise HTTPException(status_code=404, detail="Chat not found")

@app.get("/api/tts")
async def get_api_tts(text: str = Query(...), lang: str = Query("hi")):
    """
    Returns audio bytes for the given text and language.
    Language defaults to 'hi' to ensure natural Hinglish pronunciation.
    """
    tts_lang = "hi" if lang == "hindi" else "en"
    audio_bytes = generate_tts(text, language=tts_lang)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="TTS generation failed")
    return Response(content=audio_bytes, media_type="audio/mpeg")

@app.get("/health")
async def health():
    return {"status": "ok" if (state.faiss_index and state.groq_client) else "degraded", "uptime_seconds": int(time.time() - _START_TIME), "db_row_count": get_db_row_count()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)