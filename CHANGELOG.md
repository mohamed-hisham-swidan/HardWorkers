# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.3.0] - 2026-06-30

### Added

- Semantic memory with FAISS vector store and sentence-transformers embeddings
- Multi-chat system with isolated histories and per-chat memory facts
- Autonomous agent system with Observe-Analyze-Plan-Execute-Verify lifecycle
- Vision pipeline (image analysis via Ollama vision models + OCR)
- Knowledge extraction engine (concept analysis, relationship mapping, backlinks)
- Obsidian vault integration (read/write notes, structured imports)
- Training pipeline with LoRA fine-tuning, GGUF support, LM Studio/Ollama adapters
- Domain expert modules (Python, AI, Cybersecurity, Technical Architecture)
- Quality assurance validator with automated check registration
- FastAPI REST/WebSocket API server with JWT auth
- React frontend (Vite + TypeScript + TanStack Query + Zustand)
- Environment validation system with pre-startup checks
- DI container for service registration and resolution

### Changed

- Extracted settings from config into a dedicated `settings/` module with JSON persistence
- Split monolithic database repository into domain-specific repository classes
- Migrated API client services into `services/ai/` subpackage
- Improved logging configuration with rotation and structured format

### Security

- Added encryption for API keys at rest via `cryptography` library
- Added warnings for default JWT secret and admin credentials in production
- Path traversal protection in file I/O tools

## [3.2.0] - 2026-05-15

### Added

- Model routing with keyword-based category detection
- Workspace system with isolated model/router/memory configuration
- Model creator dialog for Ollama and API models
- Diagnostics dialog with system health metrics
- Chat pinning and search in sidebar

### Changed

- Enhanced markdown rendering with syntax-highlighted code blocks
- Improved error handling during startup
- UI layout optimizations for various screen sizes

## [3.1.0] - 2026-04-01

### Added

- Voice I/O with speech-to-text and text-to-speech
- Waveform animation during recording
- Multi-language support (Arabic, English) for voice input
- Image paste via clipboard (Ctrl+V)
- Environment validation with configurable checks

### Changed

- Refactored configuration into frozen dataclasses with env var overrides
- Improved logging with structured formatting and rotation

## [3.0.0] - 2026-02-15

### Added

- Initial public release
- Flet desktop UI with ChatGPT-inspired design
- Multi-model chat (Ollama + external API providers)
- Streaming responses with markdown rendering
- SQLite database with schema migrations
- Basic memory system with conversation summarization
- Model registry for API provider management
