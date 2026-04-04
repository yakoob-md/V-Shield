"""
main.py
=======
FastAPI backend for the Vernacular Voice-First Anti-Doping RAG application.

Features:
  - FAISS-based RAG retrieval
  - Persistent SQLite conversation memory
  - Short-term (in-prompt) memory from last 3 interactions
  - Groq Whisper STT + gTTS for voice pipeline
  - Groq LLM (llama-3.3-70b-versatile) integration
  - Auto language detection: English reply in English, Hindi reply in Hinglish
  - /verify       -> voice input, audio-only response
  - /verify-text  -> text input, text response (chat UI)

Run:
    pip install fastapi uvicorn python-multipart sentence-transformers faiss-cpu groq
    python build_vector_db.py   # first time only
    uvicorn main:app --reload --port 8000
"""

import os
import pickle
import sqlite3
import datetime
import logging
import json
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import faiss
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentence_transformers import SentenceTransformer
from groq import Groq


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

GROQ_API_KEY       = os.getenv("GROQ_API_KEY")
FAISS_INDEX_PATH   = "faiss_index.bin"
CHUNKS_PATH        = "chunks.pkl"
SQLITE_DB_PATH     = "chat_history.db"
EMBEDDING_MODEL    = "paraphrase-multilingual-MiniLM-L12-v2"
LLM_MODEL          = "llama-3.3-70b-versatile"
TOP_K_RETRIEVAL    = 3   # FAISS chunks retrieved per query
MEMORY_WINDOW      = 3   # Number of past interactions used as context
HISTORY_LIMIT      = 10  # Default items returned by /history

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL SINGLETONS  (loaded once at startup)
# ══════════════════════════════════════════════════════════════════════════════

class AppState:
    faiss_index: Optional[faiss.Index] = None
    chunks:      Optional[list[str]]   = None
    embedder:    Optional[SentenceTransformer] = None
    groq_client: Optional[Groq] = None


state = AppState()


# ══════════════════════════════════════════════════════════════════════════════
# LIFESPAN  (startup / shutdown)
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all heavy resources at startup; release at shutdown."""
    log.info("⏳ Loading FAISS index…")
    if not os.path.exists(FAISS_INDEX_PATH):
        raise RuntimeError(
            f"FAISS index not found at '{FAISS_INDEX_PATH}'. "
            "Run `python build_vector_db.py` first."
        )
    state.faiss_index = faiss.read_index(FAISS_INDEX_PATH)
    log.info(f"✅ FAISS loaded – {state.faiss_index.ntotal} vectors")

    log.info("⏳ Loading text chunks…")
    with open(CHUNKS_PATH, "rb") as f:
        state.chunks = pickle.load(f)
    log.info(f"✅ {len(state.chunks)} chunks loaded")

    log.info("⏳ Loading embedding model…")
    state.embedder = SentenceTransformer(EMBEDDING_MODEL)
    log.info("✅ Embedding model ready")

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
    description="Voice-first RAG assistant for rural Indian athletes",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# SQLITE  –  PERSISTENT MEMORY LAYER
# ══════════════════════════════════════════════════════════════════════════════

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the chat_history table if it doesn't exist."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_query  TEXT    NOT NULL,
                ai_response TEXT    NOT NULL,
                timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save_interaction(user_query: str, ai_response: str):
    """Persist a query-response pair to SQLite."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO chat_history (user_query, ai_response) VALUES (?, ?)",
            (user_query, ai_response),
        )
        conn.commit()


def fetch_recent_history(limit: int = MEMORY_WINDOW) -> list[dict]:
    """Retrieve the N most recent interactions (for in-prompt memory)."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT user_query, ai_response FROM chat_history "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    # Reverse to chronological order
    return [{"user_query": r["user_query"], "ai_response": r["ai_response"]}
            for r in reversed(rows)]


def fetch_history_for_api(limit: int = HISTORY_LIMIT) -> list[dict]:
    """Retrieve the N most recent interactions for the /history endpoint."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, user_query, ai_response, timestamp "
            "FROM chat_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# FREE STT/TTS INTEGRATION (Groq Whisper & gTTS)
# ══════════════════════════════════════════════════════════════════════════════

def bhashini_stt(audio_bytes: bytes) -> str:
    """
    Uses Groq's whisper-large-v3 model to transcribe the audio.
    Supports Hindi, Hinglish, and English naturally.
    """
    log.info("🎙️  [Groq Whisper] Transcribing audio...")
    try:
        # Wrap bytes in a tuple with a filename to satisfy the Groq API
        file_obj = ("audio.webm", audio_bytes)
        transcription = state.groq_client.audio.transcriptions.create(
            file=file_obj,
            model="whisper-large-v3",
            response_format="text",
            language="hi"  # Target Hindi/Hinglish
        )
        return transcription.strip()
    except Exception as e:
        log.error(f"Whisper STT error: {e}")
        return "Audio samajh nahi aaya, kripya text send karein."

def bhashini_tts(text: str, language: str = "hi") -> bytes:
    """
    Uses Google Text-to-Speech (gTTS) to generate free Hindi audio.
    Returns audio bytes (MP3).
    """
    log.info("🔊 [gTTS] Generating Hindi audio...")
    try:
        from gtts import gTTS
        from io import BytesIO
        import re
        
        # Strip emojis so the voice doesn't read them out awkwardly
        clean_text = re.sub(r'[^\w\s,.-]', '', text)
        
        tts = gTTS(text=clean_text, lang=language, slow=False)
        fp = BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
    except ImportError:
        log.warning("gTTS not installed. Run: pip install gTTS")
        return b"DUMMY_AUDIO_BYTES"
    except Exception as e:
        log.error(f"TTS error: {e}")
        return b"DUMMY_AUDIO_BYTES"


# ══════════════════════════════════════════════════════════════════════════════
# RAG RETRIEVAL
# ══════════════════════════════════════════════════════════════════════════════

def retrieve_context(query: str, top_k: int = TOP_K_RETRIEVAL) -> str:
    """
    Embeds the query and retrieves the top-k most relevant knowledge chunks
    from the FAISS index.
    """
    query_embedding = state.embedder.encode([query], convert_to_numpy=True).astype(np.float32)
    distances, indices = state.faiss_index.search(query_embedding, top_k)

    retrieved = []
    for idx in indices[0]:
        if idx < len(state.chunks):
            retrieved.append(state.chunks[idx])

    return "\n\n".join(retrieved) if retrieved else "No specific knowledge found."


# ══════════════════════════════════════════════════════════════════════════════
# LLM CALL  (Groq)
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
You are a trusted, empathetic anti-doping mentor for rural Indian athletes.

YOUR STRICT RULES:
1. Answer ONLY questions about medicines, supplements, or doping risks.
   - If unrelated, politely refuse in the instructed language.

2. Use ONLY the knowledge context and past conversation provided. DO NOT guess or invent facts.
   - If data missing, say so in the instructed language.

3. SAFETY-FIRST: When uncertain, mark as RISKY, never assume safe.

4. RISK CLASSIFICATION: Every answer must reflect one of:
   - SAFE ✅  |  CAUTION ⚠️  |  BANNED ❌  |  UNKNOWN ❓

5. Response LENGTH: EXACTLY 3 short sentences only.
   - Sentence 1: Direct answer (safe / banned / risky) with emoji tag.
   - Sentence 2: Reason (why).
   - Sentence 3: Advice (what to do next).

6. Never give medical prescriptions, legal guarantees, or absolute safety claims.

7. If the product is unknown: output the UNKNOWN ❓ message in the instructed language.

Remember: You are a supportive mentor, not a strict authority.
"""


# ══════════════════════════════════════════════════════════════════════════════
# LANGUAGE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detect_language(text: str) -> str:
    """
    Returns 'hindi' if any Devanagari character (U+0900–U+097F) is found,
    otherwise returns 'english'. Used to drive language-adaptive LLM responses.
    """
    has_hindi_chars = any('\u0900' <= c <= '\u097F' for c in text)
    detected = "hindi" if has_hindi_chars else "english"
    log.info(f"🌐 Language detected: {detected}")
    return detected


def call_llm(user_query: str, knowledge_context: str, past_chats: list[dict], lang: str = "hindi") -> str:
    """
    Calls Groq LLM with language-adaptive system prompt injection.
      - lang='english'  -> responds in plain English
      - lang='hindi'    -> responds in Hinglish (Hindi in English script)
    """

    # Choose language instruction and fallback message based on detected language
    if lang == "english":
        language_instruction = (
            "LANGUAGE INSTRUCTION: The user wrote in English. "
            "Respond ONLY in clear, simple English. Do NOT use Hindi or Hinglish."
        )
        fallback_response = (
            "CAUTION ⚠️ – System is busy right now, please try again shortly. "
            "If urgent, call the NADA helpline. "
            "Always use certified products before taking any supplement."
        )
    else:
        language_instruction = (
            "LANGUAGE INSTRUCTION: The user wrote in Hindi. "
            "Respond in Hinglish (Hindi written in English script, mixed with simple English). "
            "Do NOT use Devanagari script in your response."
        )
        fallback_response = (
            "CAUTION ⚠️ – Abhi system thoda busy hai, try karo thodi der baad. "
            "Agar urgent hai toh NADA helpline pe call karo. "
            "Koi bhi supplement lene se pehle certified products hi lo."
        )

    # Build memory block from recent history
    memory_block = ""
    if past_chats:
        memory_block = "PAST CONVERSATIONS (use as context):\n"
        for i, chat in enumerate(past_chats, 1):
            memory_block += (
                f"[{i}] User: {chat['user_query']}\n"
                f"    Assistant: {chat['ai_response']}\n"
            )
        memory_block += "\n"

    # Final user message combining context + query
    user_message = (
        f"{memory_block}"
        f"KNOWLEDGE CONTEXT:\n{knowledge_context}\n\n"
        f"CURRENT QUESTION: {user_query}"
    )

    log.info(f"📤 Sending query to Groq LLM (lang={lang})…")
    try:
        completion = state.groq_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + language_instruction},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        response_text = completion.choices[0].message.content.strip()
        log.info(f"📥 LLM response received ({len(response_text)} chars)")
        return response_text

    except Exception as e:
        log.error(f"Groq API error: {e}")
        return fallback_response


# ══════════════════════════════════════════════════════════════════════════════
# FULL PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run_rag_pipeline(audio_bytes: bytes) -> tuple[str, str, bytes]:
    """
    Full voice pipeline:
      audio -> STT -> language detect -> RAG retrieval -> Memory fetch -> LLM -> Save -> TTS -> return

    Returns:
        (user_query_text, ai_response_text, tts_audio_bytes)
    """
    log.info("🎤 [Voice Pipeline] Starting…")

    # Step 1: Speech-to-Text
    user_query = bhashini_stt(audio_bytes)
    log.info(f"📝 Transcribed query: {user_query}")

    # Step 2: Detect language of the transcribed text
    lang = detect_language(user_query)

    # Step 3: Fetch recent conversation history (short-term memory)
    past_chats = fetch_recent_history(limit=MEMORY_WINDOW)
    log.info(f"🧠 Loaded {len(past_chats)} past interactions for context")

    # Step 4: Retrieve relevant knowledge from FAISS
    knowledge_context = retrieve_context(user_query)
    log.info(f"📚 Retrieved {TOP_K_RETRIEVAL} knowledge chunks")

    # Step 5: Call LLM with language-aware system prompt
    ai_response = call_llm(user_query, knowledge_context, past_chats, lang=lang)
    log.info(f"🤖 AI Response: {ai_response[:80]}…")

    # Step 6: Persist to SQLite
    save_interaction(user_query, ai_response)
    log.info("💾 Interaction saved to SQLite")

    # Step 7: Text-to-Speech in matching language
    tts_lang = "hi" if lang == "hindi" else "en"
    audio_response = bhashini_tts(ai_response, language=tts_lang)
    log.info("🔊 TTS audio generated")

    return user_query, ai_response, audio_response


# ══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/verify", summary="Process voice query – returns audio-only response")
async def verify(audio: UploadFile = File(...)):
    """
    Accepts a voice note (audio file), runs the full RAG pipeline.
    Returns ONLY audio bytes (hex-encoded) for voice-first UX.
    History is still saved to SQLite for the sidebar.

    Returns:
        { "audio_base64": "<hex-encoded MP3 bytes>" }
    """
    log.info("📨 [/verify] Voice query received")
    try:
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file received.")

        _user_query, _ai_response, audio_bytes_out = run_rag_pipeline(audio_bytes)
        log.info("✅ [/verify] Audio response ready – sending to client")

        return JSONResponse({
            "audio_base64": audio_bytes_out.hex(),
        })

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[/verify] Pipeline error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/verify-text", summary="Process text query – returns text response for chat UI")
async def verify_text(payload: dict):
    """
    Accepts plain text query from the chat UI.
    Auto-detects language and responds in English or Hinglish accordingly.
    Body: { "query": "Kya whey protein safe hai?" }

    Returns:
        { "user_query": "...", "ai_response": "..." }
    """
    query = payload.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query text cannot be empty.")

    log.info(f"📨 [/verify-text] Received: {query[:60]}…")

    try:
        lang              = detect_language(query)
        past_chats        = fetch_recent_history(limit=MEMORY_WINDOW)
        knowledge_context = retrieve_context(query)
        ai_response       = call_llm(query, knowledge_context, past_chats, lang=lang)
        save_interaction(query, ai_response)

        log.info("✅ [/verify-text] Response ready – sending to frontend")
        return JSONResponse({
            "user_query":  query,
            "ai_response": ai_response,
        })

    except Exception as e:
        log.error(f"[/verify-text] Pipeline error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history", summary="Fetch last N chat interactions")
async def history(limit: int = HISTORY_LIMIT):
    """
    Returns the most recent `limit` chat interactions from SQLite.

    Returns:
        [{ "id": 1, "user_query": "...", "ai_response": "...", "timestamp": "..." }, …]
    """
    try:
        rows = fetch_history_for_api(limit=limit)
        return JSONResponse({"history": rows, "count": len(rows)})
    except Exception as e:
        log.error(f"History fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/history", summary="Clear all chat history")
async def clear_history():
    """Clears all records from the chat_history table."""
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM chat_history")
            conn.commit()
        return JSONResponse({"message": "Chat history cleared successfully."})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", summary="Health check")
async def health():
    return {
        "status":         "ok",
        "faiss_vectors":  state.faiss_index.ntotal if state.faiss_index else 0,
        "chunks_loaded":  len(state.chunks) if state.chunks else 0,
        "db_path":        SQLITE_DB_PATH,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)