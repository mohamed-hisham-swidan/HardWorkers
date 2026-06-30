"""Obsidian vault importer — imports documents and external content into the vault."""

from __future__ import annotations

import logging
from pathlib import Path

from obsidian.note_generator import NoteGenerator, ObsidianNote
from obsidian.structure import VaultStructure
from obsidian.vault import ObsidianVault
from training.document_import import DocumentImporter

log = logging.getLogger("hard_workers.obsidian.importer")


class ObsidianImporter:
    """Imports various content types into an Obsidian vault."""

    def __init__(
        self,
        vault: ObsidianVault,
        structure: VaultStructure,
        note_generator: NoteGenerator,
        document_importer: DocumentImporter | None = None,
    ) -> None:
        self._vault = vault
        self._structure = structure
        self._notes = note_generator
        self._docs = document_importer or DocumentImporter()

    # ── Public API ──────────────────────────────────────────────────────────────

    def import_file(self, file_path: str | Path) -> ObsidianNote | None:
        """Import a single file into the vault as a knowledge note."""
        file_path = Path(file_path)
        if not file_path.exists():
            log.error("File not found: %s", file_path)
            return None

        doc = self._docs.import_file(file_path)
        folder = self._structure.suggest_folder(doc.title, doc.content)
        tags = list(set(doc.metadata.get("tags", [])))
        if doc.source_type == "code":
            language = doc.metadata.get("language", "code")
            tags.append(language)

        note = self._notes.generate_knowledge_note(
            title=doc.title,
            content=doc.content,
            tags=tags,
        )
        log.info("Imported file: %s → %s/%s", file_path.name, folder, doc.title)
        return note

    def import_obsidian_vault(self, source_path: str | Path) -> list[ObsidianNote]:
        """Import notes from another Obsidian vault."""
        source_path = Path(source_path)
        if not source_path.exists():
            log.error("Source vault not found: %s", source_path)
            return []

        docs = self._docs.import_obsidian_vault(source_path)
        notes: list[ObsidianNote] = []
        for doc in docs:
            folder = self._structure.suggest_folder(doc.title, doc.content)
            tags = list(set(doc.metadata.get("tags", [])))
            note = ObsidianNote(
                title=doc.title,
                content=doc.content,
                folder=folder,
                tags=tags,
                links=doc.metadata.get("wikilinks", []),
            )
            self._vault.write_note(note.folder, note.title, note.render(), tags=note.tags)
            log.info("Imported vault note: %s → %s", doc.title, folder)
            notes.append(note)

        return notes

    def import_directory(
        self,
        dir_path: str | Path,
        recursive: bool = True,
    ) -> list[ObsidianNote]:
        """Import all supported files from a directory."""
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            log.error("Directory not found: %s", dir_path)
            return []

        docs = self._docs.import_directory(dir_path, recursive=recursive)
        notes: list[ObsidianNote] = []
        for doc in docs:
            try:
                self._structure.suggest_folder(doc.title, doc.content)
                tags = list(set(doc.metadata.get("tags", [])))
                note = self._notes.generate_knowledge_note(
                    title=doc.title,
                    content=doc.content,
                    tags=tags,
                )
                notes.append(note)
            except Exception as exc:
                log.warning("Failed to import %s: %s", doc.title, exc)

        log.info("Imported %d files from %s", len(notes), dir_path)
        return notes

    def import_text(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
        folder: str | None = None,
    ) -> ObsidianNote:
        """Import raw text as a vault note."""
        if not folder:
            folder = self._structure.suggest_folder(title, content, tags)
        note = self._notes.generate_knowledge_note(
            title=title,
            content=content,
            tags=tags,
        )
        return note
