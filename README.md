# HardWorkres

> AI-powered desktop assistant with semantic memory, multi-model chat, voice I/O, vision understanding, and autonomous agents.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python)]()
[![Flet](https://img.shields.io/badge/flet-0.85.3-blue?logo=flutter)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Code style](https://img.shields.io/badge/code%20style-ruff-261230)]()

---

## Overview

HardWorkres is a professional AI desktop application that combines local and cloud AI models, long-term semantic memory, voice input/output, vision analysis, and extensible agent/training pipelines — all in a ChatGPT-inspired interface built with [Flet](https://flet.dev).

**Supported providers:** Ollama (local), OpenAI, Anthropic, Google Gemini, Groq, OpenRouter, Together AI, DeepSeek, and any OpenAI-compatible API.

---

## Features

- **Multi-Model Chat** — Use local Ollama models and cloud APIs side by side, with intelligent content-based routing
- **Semantic Memory** — FAISS vector store with sentence-transformers embeddings, global and per-chat facts, conversation summarization
- **Voice I/O** — Speech-to-text and text-to-speech with auto language detection (Arabic/English)
- **Vision** — Paste or attach images; automatic vision model detection and OCR
- **Autonomous Agents** — Observe-Analyze-Plan-Execute-Verify lifecycle with file I/O and code analysis tools
- **Workspaces** — Isolated environments with custom model, router, and memory profiles
- **Model Management** — Browsing, registration, cloning, and testing for Ollama and API models
- **Knowledge Engine** — Concept extraction, relationship mapping, and backlink generation
- **Obsidian Integration** — Read, write, and structure Obsidian vault notes programmatically
- **Training Pipeline** — LoRA fine-tuning with GGUF support and LM Studio/Ollama adapters
- **Extensible** — DI container, event bus, plugin-style subsystems (QA validators, domain experts)
- **FastAPI Server** — REST + WebSocket API with JWT auth (for custom frontends)
- **React Frontend** — (In development) Vite + TypeScript + TanStack Query + Zustand

---

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) (for local models) — or API keys for cloud providers

### Install & Run

```bash
# Clone
git clone https://github.com/mohamed-hisham-swidan/hardworkers.git
cd hardworkers

# Virtual environment (recommended)
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run desktop app
python main.py
```

For the API server: `python run_api.py`

For web mode: `python run_web.py`

See [INSTALL.md](INSTALL.md) for detailed setup, including optional dependencies for voice, vision, and training.

---

## Configuration

Configuration is loaded from environment variables or `.env` file. Copy `.env.example` to `.env` and customize:

```env
OLLAMA_BASE_URL=http://localhost:11434
DB_PATH=./data/hardworkers.db
LOG_DIR=./logs
UI_WIDTH=1280
UI_HEIGHT=900
```

For production deployments, always set `JWT_SECRET` to a strong random value and change the default `ADMIN_PASSWORD`.

---

## Project Structure

```
hardworkers/
├── app/              # DI & application bootstrap
├── agent/            # Autonomous agent system
├── api/              # FastAPI REST/WebSocket server
├── backend/          # Voice subsystem (STT, TTS, audio)
├── config/           # Environment config & constants
├── core/             # DI container, event bus, interfaces, environment validation
├── database/         # SQLite connection, migrations, repositories
├── docs/             # Architecture documentation
├── experts/          # Domain expert modules
├── frontend/         # React + Vite web UI (in development)
├── knowledge/        # Knowledge extraction & relationship mapping
├── memory/           # Semantic memory & summarization
├── models/           # Domain data models & enums
├── obsidian/         # Obsidian vault integration
├── qa/               # Quality assurance validators
├── services/         # Business logic & AI integrations
├── settings/         # User settings persistence
├── tests/            # Test suite
├── training/         # Model training pipeline
├── ui/               # Flet desktop UI components
├── utils/            # Logging, HTTP, crypto, helpers
├── vectorstore/      # FAISS vector index wrapper
├── vision/           # Image processing & vision
├── vault/            # Obsidian vault data store
├── main.py           # Desktop entry point
├── run_api.py        # API server entry point
└── run_web.py        # Web mode entry point
```

---

## Dependencies

| Category | Packages |
|----------|----------|
| **Core** | flet, requests, numpy, tiktoken, pillow |
| **Vector Store** | faiss-cpu, sentence-transformers |
| **Voice** | SpeechRecognition, pyttsx3 |
| **Vision** | pytesseract |
| **API Server** | fastapi, uvicorn, python-jose, pydantic, websockets |
| **Documents** | pypdf, python-docx, beautifulsoup4, pyyaml |
| **Security** | cryptography |
| **Windows** | pywin32 (clipboard access) |

Optional: `transformers`, `torch`, `datasets` for training; `opencv-python` for advanced image processing; `edge-tts` for enhanced TTS.

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Ctrl+N` | New chat |
| `Ctrl+E` | Focus input |
| `Ctrl+B` | Toggle sidebar |
| `Ctrl+V` | Paste image |
| `Ctrl+L` | Clear chat |
| `Ctrl+S` | Open settings |
| `Escape` | Focus input |

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and PR process.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

---

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

---

## License

MIT — see [LICENSE](LICENSE).
