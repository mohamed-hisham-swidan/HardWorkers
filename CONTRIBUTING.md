# Contributing

We welcome contributions of all sizes — bug fixes, features, documentation, tests, and design improvements.

## Development Setup

```bash
git clone https://github.com/yourusername/hardworkers.git
cd hardworkers
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Running Tests

```bash
pytest tests/
```

## Code Style

This project uses [ruff](https://docs.astral.sh/ruff) for linting and formatting:

```bash
ruff check .    # lint
ruff format .   # format
```

Configuration is in `ruff.toml`.

Guidelines:

- **Python 3.11+** — use modern typing, f-strings, and pattern matching where appropriate
- **Type annotations** — required for all function signatures
- **Docstrings** — for all public APIs (Google-style recommended)
- **Thread safety** — use `threading.Lock` or `RLock` for shared mutable state
- **UI mutations** — must go through `page.run_thread()` in Flet
- **No circular imports** — use `TYPE_CHECKING` for type-only imports
- **Keep functions focused** — single responsibility, reasonable length

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Run tests: `pytest tests/`
4. Run linting: `ruff check .`
5. Submit a pull request with a clear description

### PR Guidelines

- One feature/fix per PR
- Include tests for new functionality
- Update documentation (README, docs/) if behaviour changes
- Keep the commit history clean

## Project Architecture

```
app/           DI container & application bootstrap
agent/         Autonomous agent system
api/           FastAPI REST + WebSocket server
backend/       Subsystems (voice, etc.)
config/        Environment config & constants
core/          DI container, event bus, interfaces, environment validation
database/      SQLite connection, migrations, repositories
docs/          Architecture documentation
experts/       Domain expert modules
frontend/      React + Vite web UI
knowledge/     Knowledge extraction & relationship mapping
memory/        Semantic memory & summarization
models/        Domain data models & enums
obsidian/      Obsidian vault integration
qa/            Quality assurance validators
services/      Business logic & AI integrations
settings/      User settings persistence
tests/         Test suite
training/      Model training pipeline
ui/            Flet desktop UI
utils/         Logging, HTTP, crypto, helpers
vectorstore/   FAISS vector index
vision/        Image processing & vision
```

## Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add semantic memory search
fix: resolve crash on empty chat history
docs: update API documentation
refactor: extract model router service
test: add tests for workspace service
chore: update ruff config
```

## Questions?

Open a [Discussion](https://github.com/yourusername/hardworkers/discussions) or check the [docs/](docs/) directory for architecture details.
