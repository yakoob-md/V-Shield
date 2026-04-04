
# 🏅 Clean Sport – Vernacular Voice-First Anti-Doping RAG App

A production-grade, voice-first RAG assistant for rural Indian athletes.
Answers supplement and medicine safety queries in **Hinglish**, with
persistent conversation memory and a CoE-NSTS aligned knowledge base.

---

## 📁 File Structure

```
antidoping_app/
├── build_vector_db.py   # Dataset generator + FAISS index builder (run once)
├── main.py              # FastAPI backend with RAG + SQLite memory
├── index.html           # Frontend (Vanilla JS + Tailwind CDN)
└── README.md
```

After running `build_vector_db.py`, these files are auto-created:
```
├── faiss_index.bin      # FAISS vector index
├── chunks.pkl           # Raw text chunks
├── datasets.json        # Raw datasets (inspection only)
└── chat_history.db      # SQLite persistent memory
```

---

## ⚡ Quick Start

### 1. Install dependencies
```bash
pip install fastapi uvicorn python-multipart sentence-transformers faiss-cpu groq
```

### 2. Set your Groq API key
```bash
export GROQ_API_KEY="your_groq_key_here"
```
Get a free key at: https://console.groq.com

### 3. Build the vector database (run ONCE)
```bash
python build_vector_db.py
```
Downloads the multilingual embedding model (~400 MB) and creates FAISS index.

### 4. Start the backend
```bash
uvicorn main:app --reload --port 8000
```

### 5. Open the frontend
Open `index.html` in any modern browser.
> If CORS issues arise, serve via: `python -m http.server 3000`

---

## 🎯 API Endpoints

| Method | Endpoint       | Description                        |
|--------|----------------|------------------------------------|
| POST   | `/verify`      | Submit audio file → get response   |
| POST   | `/verify-text` | Submit text query → get response   |
| GET    | `/history`     | Fetch last 10 chat interactions    |
| DELETE | `/history`     | Clear all chat history             |
| GET    | `/health`      | System health check                |

---

## 🧠 System Architecture

```
User (Voice/Text)
      │
      ▼
[ Bhashini STT ] ──── placeholder
      │
      ▼
[ FAISS RAG ] ─── top-3 relevant chunks
      │
      ├── [ SQLite ] ─── last 3 interactions (short-term memory)
      │
      ▼
[ Groq LLM: llama-3.3-70b-versatile ]
      │
      ▼
[ SQLite SAVE ] ─── persist interaction (long-term memory)
      │
      ▼
[ Bhashini TTS ] ──── placeholder -- now using whisper and gtts
      │
      ▼
[ Frontend Response + History Update ]
```

---

## 🔊 Bhashini Integration (Production)

Replace the two placeholder functions in `main.py`:

```python
# STT – POST https://dhruva-api.bhashini.gov.in/services/inference/asr
def bhashini_stt(audio_bytes: bytes) -> str:
    # Send audio_bytes to Bhashini ASR endpoint
    # Return transcribed Hindi/Hinglish text
    ...

# TTS – POST https://dhruva-api.bhashini.gov.in/services/inference/tts
def bhashini_tts(text: str, language: str = "hi") -> bytes:
    # Send text to Bhashini TTS endpoint
    # Return audio bytes (WAV/MP3)
    ...
```

Register at: https://bhashini.gov.in/ulca

---

## 📊 Knowledge Base Coverage

- **52 WADA prohibited substances** with ban status and notes
- **15 Indian branded medicines** with composition and risk flags
- **16 Indian supplements** (Ayurvedic + protein + vitamins) with CoE-NSTS status
- **13 educational knowledge chunks** (strict liability, TUE process, etc.)

---

## 🔒 Safety Design Principles

1. **Fail-safe**: Unknown products → always CAUTION, never assume SAFE
2. **No hallucination**: LLM instructed to use only RAG context
3. **Exact 3-sentence output**: Structured for low-literacy comprehension
4. **Domain restriction**: Off-topic queries rejected with Hindi message

