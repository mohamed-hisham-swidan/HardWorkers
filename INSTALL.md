# Installation Guide

## Prerequisites

- **Python 3.11 or later**
- **Git** (for cloning the repository)
- **Ollama** (recommended for local AI models) — [Download](https://ollama.ai)

## Step 1: Get the Code

```bash
git clone https://github.com/yourusername/hardworkers.git
cd hardworkers
```

Or download and extract the [latest release ZIP](https://github.com/yourusername/hardworkers/releases).

## Step 2: Create a Virtual Environment

```bash
python -m venv .venv
```

**Activate:**

| Platform | Command |
|----------|---------|
| Windows (CMD) | `.venv\Scripts\activate` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| macOS / Linux | `source .venv/bin/activate` |

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs the core packages. See [Dependencies](#dependencies) below for optional extras.

### Optional Dependencies

Some features have additional dependencies that are not required for the base application:

| Feature | Command | Required By |
|---------|---------|-------------|
| Voice (basic) | *(included in requirements.txt)* | Speech Recognition + TTS |
| Voice (enhanced) | `pip install edge-tts` | Higher quality TTS |
| Vision (advanced) | `pip install opencv-python` | Advanced image processing |
| Training | `pip install transformers torch datasets` | Model fine-tuning |
| Development | `pip install -r requirements-dev.txt` | Testing, linting |

## Step 4: Install Ollama (Recommended)

Ollama provides local AI models without API keys:

1. Download from [ollama.ai](https://ollama.ai) and install
2. Pull at least one model:

```bash
ollama pull llama3.2
ollama pull llava  # for vision support
```

3. Ensure the Ollama service is running (`ollama serve` or start the desktop app)

## Step 5: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` to customize paths, models, and API keys for cloud providers.

**Minimum configuration** (all have sensible defaults):

```env
OLLAMA_BASE_URL=http://localhost:11434
```

## Step 6: Run

### Desktop Application

```bash
python main.py
```

### API Server (for custom frontends)

```bash
python run_api.py
```

Serves REST + WebSocket API at `http://localhost:8000` by default. See `config/settings.py` for configuration options.

### Web Mode (Flet in browser)

```bash
python run_web.py
```

Opens the Flet UI in your browser at `http://localhost:8580`.

## Dependencies

### Core (installed by default)

| Package | Version | Purpose |
|---------|---------|---------|
| flet | >=0.85.0 | Desktop UI framework |
| faiss-cpu | >=1.8.0 | Vector similarity search |
| fastapi | >=0.115.0 | REST/WebSocket API server |
| uvicorn | >=0.30.0 | ASGI server |
| pydantic | >=2.9.0 | Data validation |
| requests | >=2.32.0 | HTTP client |
| numpy | >=1.26.0 | Numerical operations |
| tiktoken | >=0.7.0 | Token counting |
| pillow | >=10.4.0 | Image processing |
| cryptography | >=42.0.0 | API key encryption |
| pywin32 | >=306 | Windows clipboard (Ctrl+V image) |

### Optional

| Package | Purpose |
|---------|---------|
| sentence-transformers | Better embeddings for FAISS |
| opencv-python | Advanced image processing |
| edge-tts | Enhanced TTS via Microsoft Edge |
| transformers | Model training pipeline |
| torch | Model training pipeline |
| datasets | Model training pipeline |

## Updating

```bash
git pull
pip install -r requirements.txt --upgrade
```

## Troubleshooting

### "Ollama service not reachable"

- Ensure Ollama is running: `ollama serve`
- Verify the URL in `.env` or `OLLAMA_BASE_URL` environment variable
- Default: `http://localhost:11434`

### Import errors

```bash
# Ensure virtual environment is activated and dependencies installed
pip install -r requirements.txt --force-reinstall
```

### Database issues

Delete the database file and restart — it will be recreated:

```bash
rm data/hardworkers.db
python main.py
```

### "Tesseract is not installed"

Required for OCR. Download from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki) and add to PATH.

### Windows-specific

- If `pywin32` fails to install, you may need the Visual C++ Redistributable
- For voice features, ensure microphone permissions are granted
