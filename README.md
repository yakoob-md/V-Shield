# 🏅 Athlete Shield AI – Premium Anti-Doping RAG Assistant

[![Project Status: Active](https://img.shields.io/badge/Project%20Status-Active-brightgreen.svg)](https://github.com/yakoob-md/antidoping-assistant)
[![Stack: FastAPI + React + FAISS](https://img.shields.io/badge/Stack-FastAPI%20%7C%20React%20%7C%20FAISS-blue.svg)](https://fastapi.tiangolo.com/)
[![Design: Midnight Glass](https://img.shields.io/badge/Design-Midnight%20Glass-purple.svg)](https://tailwindcss.com/)

> **The ultimate safety companion for the modern road athlete.** 
> Athlete Shield AI is a production-grade, voice-first RAG (Retrieval-Augmented Generation) assistant designed to protect rural and professional Indian athletes from unintentional doping.

---

## ✨ The "Wow" Factor: Premium Excellence

Athlete Shield AI isn't just a chatbot; it's a high-end digital mentor. Our latest update introduces a **Premium Midnight-Glass** interface designed to wow users at first glance.

### 🌌 Midnight-Glass Design System
- **Vibrant Animated Backgrounds**: Flowing indigo and cyan "aurora" undulations that react and move, creating a living, breathing application surface.
- **Next-Gen Glassmorphism**: High-depth `backdrop-blur-3xl` panels with ultra-thin glowing borders and shadow-bloom effects.
- **Hardware Accelerated**: Optimized with `will-change` properties and GPU-offloaded transitions for a buttery-smooth 60FPS experience even on mobile devices.

### 🎙️ Instant Vernacular Narration
- **Sub-Millisecond Delivery**: Integrated backend `lru_cache` ensures that repeated audio requests are served instantly from memory.
- **Natural Hinglish Accent**: Specialized TTS pipeline that detects mixed Hindi-English and uses a natural Indian accent (`hi-IN`) for maximum cultural resonance and clarity.

---

## 🚀 Core Intelligence Features

- **🛡️ Zero-Doping Shield**: Every response is grounded in a verified KNOWLEDGE CONTEXT derived from WADA Prohibited Lists and Indian pharmaceutical data.
- **🗣️ Natural Hinglish Understanding**: Seamlessly switch between English and Romanized Hindi. The AI understands "Kya ye supplement safe hai?" as easily as "Tell me about Creatine."
- **🧠 Context-Aware Memory**: Remembers your previous questions. Ask about "Vicks Action 500" and then follow up with "Is it banned?"—the AI knows exactly what you mean.
- **📉 Deterministic Risk Tagging**: Every answer starts with a clear, color-coded status: **SAFE ✅**, **CAUTION ⚠️**, **BANNED ❌**, or **UNKNOWN ❓**.

---

## 🏗️ System Architecture

```mermaid
graph TD
    User([User Voice/Text]) --> STT[Groq Whisper v3]
    STT --> Query[Text Query]
    Query --> RAG[FAISS Vector Search]
    RAG --> Context[Verified Knowledge Chunks]
    Context --> LLM[Groq Llama-3.3 70B]
    History[(SQLite Persistent Memory)] <--> LLM
    LLM --> Response[Concise 3-Sentence Logic]
    Response --> Cache{TTS Cache?}
    Cache -- Miss --> gTTS[Google TTS Engine]
    Cache -- Hit --> UI
    gTTS --> UI([Premium Midnight UI])
    UI --> Audio([Instant Narration])
```

---

## 📁 Project Overview

```text
anti-doping-app/
├── main.py              # FastAPI Backend (RAG + Cache + Session Management)
├── build_vector_db.py   # FAISS Vector Index Generator
├── frontend/            # Vite + React + Tailwind (Midnight-Glass UI)
│   ├── src/App.tsx      # Core UI Logic & Hardware-Accelerated Animations
│   └── src/index.css    # Premium Design Tokens & Utilities
├── faiss_index.bin      # High-performance Vector Storage
└── chats_v2.db          # Persistent SQLite Database
```

---

## 🛠️ Getting Started

### 1. Requirements
- Python 3.9+ & Node.js 18+
- [Groq API Key](https://console.groq.com) (FREE)

### 2. Rapid Setup
```bash
# 1. Setup Backend
pip install -r requirements.txt
python build_vector_db.py  # Create the brain

# 2. Setup Frontend
cd frontend
npm install

# 3. Launch (Terminal 1)
uvicorn main:app --reload

# 4. Launch (Terminal 2)
npm run dev
```

---

## 🔍 Why it Matters
Rural athletes often lack access to professional sports doctors. **Athlete Shield AI** fills this gap by translating complex WADA regulations into simple, vernacular, and actionable advice delivered through a state-of-the-art interface that respects the athlete's focus and passion.

---

### 🌟 Standards Applied
- **WADA Code 2024 Compliance**
- **NADA Localized Medicine Database**
- **CoE-NSTS Supplement Verification**

---
Produced with ❤️ by **Yakub**. Built for the gold.

