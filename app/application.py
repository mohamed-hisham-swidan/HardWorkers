"""Application factory — wires all services together.

Single responsibility: dependency injection.
No business logic lives here; only object construction and ordering.
"""

from __future__ import annotations

import time
from typing import Any

import flet as ft
from packaging.version import Version

from config.settings import AppConfig
from core.container import Container
from core.environment.models import Severity, ValidationReport
from core.environment.validator import EnvironmentValidator
from core.events import EventBus
from database.repositories import DatabaseManager
from memory.memory_service import MemoryService
from memory.summarization_service import SummarizationService
from services.ai.model_creator import ModelCreatorService
from services.ai.model_manager import ModelManager
from services.ai.model_router import ModelRouterService
from services.ai.ollama_client import OllamaClient
from services.chat_service import ChatService
from services.diagnostics_service import DiagnosticsService
from services.infrastructure.ollama_lifecycle import OllamaLifecycleService
from services.workspace_service import WorkspaceService
from settings.service import SettingsService
from ui.main_window import MainWindow
from ui.helpers import Colors
from utils.logging_setup import configure_logging, get_logger
from vectorstore.faiss_store import VectorStore

log = get_logger("app.application")


def bootstrap(page: ft.Page) -> None:
    """Entry point passed to ft.app()."""
    log = get_logger("app.application")
    _t0 = time.monotonic()

    # --- Flet version guard ---
    current_version = Version(ft.__version__)
    if current_version < Version("0.80.0"):
        msg = (
            f"Unsupported Flet version {ft.__version__} — "
            "this application requires Flet >=0.80.0.\n"
            "Run with the project virtual environment:\n"
            "  .venv\\Scripts\\python.exe main.py"
        )
        log.critical(msg)
        page.add(ft.Text(msg, color=Colors.ERROR, size=16, selectable=True))
        return

    try:
        config = AppConfig.load()
        config.prepare_dirs()

        configure_logging(config.log_dir)
        log.info("HardWorkres starting - config loaded")

        # --- environment validation ---
        validator = EnvironmentValidator(config)
        env_report = validator.validate()
        log.info(
            "Environment validation: %s (%.3fs, %d checks)",
            "HEALTHY" if env_report.is_healthy else "FAILED",
            env_report.execution_time,
            len(env_report.results),
        )

        if env_report.critical:
            report_md = validator.generate_report_markdown()
            log.critical("Environment validation found CRITICAL issues:\n%s", report_md)

            _show_validation_failure(page, env_report)
            return

        if env_report.errors:
            log.warning(
                "Environment validation found %d errors (non-critical)",
                len(env_report.errors),
            )
        if env_report.warnings:
            for warn in env_report.warnings:
                log.warning("Env warning: %s — %s", warn.name, warn.message)

        # --- cross-cutting infrastructure ---
        bus = EventBus()
        container = Container()
        settings = SettingsService(bus)
        settings.load()

        # --- infrastructure ---
        db = DatabaseManager(config.database)
        log.info("STARTUP db=%.3fs", time.monotonic() - _t0)

        vs = VectorStore(config.vector)
        log.info("STARTUP vs=%.3fs", time.monotonic() - _t0)

        ollama = OllamaClient(config.ollama)
        log.info("STARTUP ollama_client=%.3fs", time.monotonic() - _t0)

        ollama_lifecycle = OllamaLifecycleService(
            client=ollama,
            config=config.ollama,
            bin_path=config.ollama.bin_path,
        )
        log.info("STARTUP ollama_lifecycle=%.3fs", time.monotonic() - _t0)

        # --- services ---
        model_manager = ModelManager(ollama, config.ollama.default_model, db)
        log.info("STARTUP model_manager=%.3fs", time.monotonic() - _t0)

        model_creator = ModelCreatorService(config.ollama, db)
        log.info("STARTUP model_creator=%.3fs", time.monotonic() - _t0)

        model_router = ModelRouterService(db)
        log.info("STARTUP model_router=%.3fs", time.monotonic() - _t0)

        memory = MemoryService(db, vs)
        log.info("STARTUP memory=%.3fs", time.monotonic() - _t0)

        workspaces = WorkspaceService(db, model_manager, model_router, memory)
        log.info("STARTUP workspaces=%.3fs", time.monotonic() - _t0)

        chats = ChatService(db)
        log.info("STARTUP chats=%.3fs", time.monotonic() - _t0)

        summarizer = SummarizationService(ollama, config.ollama.default_model, db, memory)
        log.info("STARTUP summarizer=%.3fs", time.monotonic() - _t0)

        diagnostics = DiagnosticsService(ollama, model_manager, db, vs)
        log.info("STARTUP diagnostics=%.3fs", time.monotonic() - _t0)

        # --- new feature services (lazy init, heavy imports deferred) ---
        _try_register_obsidian(container)
        log.info("STARTUP obsidian=%.3fs", time.monotonic() - _t0)

        _try_register_vision(container, config)
        log.info("STARTUP vision=%.3fs", time.monotonic() - _t0)

        _try_register_training(container)
        log.info("STARTUP training=%.3fs", time.monotonic() - _t0)

        _try_register_experts(container)
        log.info("STARTUP experts=%.3fs", time.monotonic() - _t0)

        _try_register_knowledge(container)
        log.info("STARTUP knowledge=%.3fs", time.monotonic() - _t0)

        _try_register_qa(container)
        log.info("STARTUP qa=%.3fs", time.monotonic() - _t0)

        _try_register_voice(container)
        log.info("STARTUP voice=%.3fs", time.monotonic() - _t0)

        # --- DI container registration ---
        log.info("STARTUP reg=%.3fs", time.monotonic() - _t0)
        container.register_instance("config", config)
        container.register_instance("bus", bus)
        container.register_instance("settings", settings)
        container.register_instance("db", db)
        container.register_instance("vs", vs)
        container.register_instance("ollama", ollama)
        container.register_instance("ollama_lifecycle", ollama_lifecycle)
        container.register_instance("model_manager", model_manager)
        container.register_instance("model_creator", model_creator)
        container.register_instance("model_router", model_router)
        container.register_instance("memory", memory)
        container.register_instance("workspaces", workspaces)
        container.register_instance("chats", chats)
        container.register_instance("summarizer", summarizer)
        container.register_instance("diagnostics", diagnostics)

        _try_register_agent(container, config)
        log.info("STARTUP agent=%.3fs", time.monotonic() - _t0)

        # --- resolve voice services (registered inside _try_register_voice) ---
        stt = container.resolve("stt") if container.has("stt") else None

        # --- UI (created before Ollama is guaranteed ready —
        #   _bootstrap runs in background and handles startup) ---
        MainWindow(
            page=page,
            config=config,
            db=db,
            vs=vs,
            ollama=ollama,
            ollama_lifecycle=ollama_lifecycle,
            model_manager=model_manager,
            model_creator=model_creator,
            model_router=model_router,
            memory=memory,
            workspaces=workspaces,
            chats=chats,
            summarizer=summarizer,
            diagnostics=diagnostics,
            bus=bus,
            settings=settings,
            container=container,
            stt=stt,
        )

        log.info("HardWorkres initialised successfully")

    except Exception as exc:
        log.critical("Fatal initialisation error: %s", exc, exc_info=True)

        def _close_app(_e: ft.ControlEvent | None = None) -> None:
            try:
                page.run_task(page.window.close)
            except Exception:
                log.debug("Window close on init failure ignored")

        page.add(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("\u26a0\ufe0f", size=40),
                        ft.Text(
                            "Initialisation failed",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=Colors.ERROR,
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(str(exc), color=Colors.TEXT_MUTED, size=13, selectable=True),
                                    ft.Text(
                                        "Check the logs for details and fix the issue before restarting.",
                                        color=Colors.TEXT_MUTED2,
                                        size=11,
                                        italic=True,
                                    ),
                                ],
                                spacing=4,
                            ),
                            padding=ft.Padding(top=4, bottom=8),
                        ),
                        ft.ElevatedButton(
                            "Close Application",
                            icon=ft.Icons.EXIT_TO_APP,
                            on_click=_close_app,
                            style=ft.ButtonStyle(
                                bgcolor=Colors.ERROR,
                                color=Colors.TEXT_HIGH,
                            ),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment="center",
                expand=True,
            )
        )


# ── Lazy feature registration ───────────────────────────────────────────────────


def _show_validation_failure(page: ft.Page, report: ValidationReport) -> None:
    """Render a detailed environment validation failure UI."""
    from core.environment.report import generate_report_markdown

    report_md = generate_report_markdown(report)
    critical_count = len(report.critical)
    error_count = len(report.errors)

    lines: list[ft.Control] = [
        ft.Text(" Environment Validation Failed", size=20, weight=ft.FontWeight.BOLD, color=Colors.ERROR),
        ft.Container(height=4),
        ft.Text(
            f"{critical_count} critical / {error_count} errors — cannot start safely.",
            size=14,
            color=Colors.WARNING,
        ),
        ft.Container(height=8),
    ]

    for result in report.results:
        if result.success and result.severity not in (Severity.ERROR, Severity.CRITICAL):
            continue
        icon = "\u26a0\ufe0f" if not result.success else "\u2705"
        lines.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(f"{icon} {result.name}", weight=ft.FontWeight.BOLD, size=13),
                        ft.Text(f"  {result.message}", size=12, color=Colors.TEXT_MUTED, selectable=True),
                        ft.Text(f"  Severity: {result.severity}", size=11, color=Colors.TEXT_LOW),
                    ],
                    spacing=2,
                ),
                padding=ft.Padding(top=4, bottom=4, left=8, right=8),
                bgcolor=Colors.BG_SURFACE,
                border_radius=6,
            )
        )

    lines.append(ft.Container(height=12))
    lines.append(
        ft.Text(
            "Recommendations:",
            weight=ft.FontWeight.BOLD,
            size=13,
            color=Colors.WARNING,
        )
    )

    recommendations = [r.recommendation for r in report.results if r.recommendation]
    for rec in recommendations[:5]:
        lines.append(ft.Text(f"  - {rec}", size=11, color=Colors.TEXT_MUTED, selectable=True))

    lines.append(ft.Container(height=12))

    def _close_app(_e: ft.ControlEvent | None = None) -> None:
        try:
            page.run_task(page.window.close)
        except Exception:
            pass

    lines.append(
        ft.ElevatedButton(
            "Close Application",
            icon=ft.Icons.EXIT_TO_APP,
            on_click=_close_app,
            style=ft.ButtonStyle(bgcolor=Colors.ERROR, color=Colors.TEXT_HIGH),
        )
    )

    page.add(
        ft.Container(
            content=ft.Column(lines, spacing=4, scroll=ft.ScrollMode.AUTO),
            padding=24,
            expand=True,
        )
    )

    log = get_logger("app.application")
    log.info("Validation failure report:\n%s", report_md)


def _try_register_obsidian(container: Container) -> None:
    try:
        from obsidian.vault import ObsidianVault, VaultConfig

        vault = ObsidianVault(config=VaultConfig(path="./vault"))
        container.register_instance("obsidian_vault", vault)

        from obsidian.note_generator import NoteGenerator

        container.register_instance("obsidian_notes", NoteGenerator(vault))

        from obsidian.structure import VaultStructure

        container.register_instance("obsidian_structure", VaultStructure(vault))

        from obsidian.importer import ObsidianImporter
        from training.document_import import DocumentImporter

        container.register_instance(
            "obsidian_importer",
            ObsidianImporter(vault, VaultStructure(vault), NoteGenerator(vault), DocumentImporter()),
        )

        log.info("Obsidian integration registered")
    except Exception as exc:
        log.warning("Obsidian integration unavailable: %s", exc)


def _try_register_vision(container: Container, config: AppConfig) -> None:
    try:
        from vision.image_processor import ImageProcessor
        from vision.pipeline import VisionPipeline
        from vision.vision_model import VisionModel

        vision_model = VisionModel(api_url=config.ollama.base_url)
        container.register_instance("vision_processor", ImageProcessor())
        container.register_instance("vision_model", vision_model)
        container.register_instance("vision_pipeline", VisionPipeline(vision_model, ImageProcessor()))

        log.info("Vision pipeline registered")
    except Exception as exc:
        log.warning("Vision pipeline unavailable: %s", exc)


def _try_register_agent(container: Container, config: Any) -> None:
    try:
        from agent.agent import Agent, AgentConfig
        from agent.tools.code_analyzer import CodeAnalyzerTool
        from agent.tools.file_io import FileIOTool
        from agent.workflow import Workflow

        workspace_dir = str(getattr(config, "workspace_dir", "./workspace"))
        agent = Agent(config=AgentConfig(workspace_dir=workspace_dir))
        container.register_instance("agent", agent)
        container.register_instance("agent_file_io", FileIOTool())
        container.register_instance("agent_code_analyzer", CodeAnalyzerTool())
        container.register_instance("agent_workflow", Workflow())

        log.info("Agent system registered")
    except Exception as exc:
        log.warning("Agent system unavailable: %s", exc)


def _try_register_training(container: Container) -> None:
    try:
        from training.training_pipeline import TrainingPipeline

        pipeline = TrainingPipeline()
        container.register_instance("training_pipeline", pipeline)

        log.info("Training pipeline registered")
    except Exception as exc:
        log.warning("Training pipeline unavailable: %s", exc)


def _try_register_experts(container: Container) -> None:
    try:
        from experts.review_board import ReviewBoard

        board = ReviewBoard()
        container.register_instance("expert_board", board)

        log.info("Expert review board registered")
    except Exception as exc:
        log.warning("Expert review board unavailable: %s", exc)


def _try_register_knowledge(container: Container) -> None:
    try:
        from knowledge.extractor import KnowledgeExtractorEngine

        engine = KnowledgeExtractorEngine()
        container.register_instance("knowledge_engine", engine)

        from knowledge.concept_analyzer import ConceptAnalyzer

        analyzer = ConceptAnalyzer()
        container.register_instance("concept_analyzer", analyzer)

        from knowledge.relationship_map import RelationshipMap

        rel_map = RelationshipMap()
        container.register_instance("relationship_map", rel_map)

        from knowledge.backlink_generator import BacklinkGenerator

        bl_gen = BacklinkGenerator()
        container.register_instance("backlink_generator", bl_gen)

        log.info("Knowledge engine registered")
    except Exception as exc:
        log.warning("Knowledge engine unavailable: %s", exc)


def _try_register_qa(container: Container) -> None:
    try:
        from qa.validator import QAValidator

        validator = QAValidator()
        validator.register_defaults()
        container.register_instance("qa_validator", validator)

        log.info("QA validator registered")
    except Exception as exc:
        log.warning("QA validator unavailable: %s", exc)


def _try_register_voice(container: Container) -> None:
    try:
        from backend.voice.stt import SpeechToText

        settings = container.resolve("settings") if container.has("settings") else None
        device_index = None
        if settings:
            try:
                device_index = settings.current.voice.mic_device_index if settings.current else None
            except Exception as exc:
                log.warning("Failed to read mic device index: %s", exc)
        stt = SpeechToText(device_index=device_index)
        container.register_instance("stt", stt)
        log.info("STT service registered (available=%s, device=%s)", stt.available, device_index)
    except Exception as exc:
        log.warning("Voice services unavailable: %s", exc)
