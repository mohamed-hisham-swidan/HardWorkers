"""Obsidian knowledge management integration.

Provides full vault integration including:
- Automatic vault organization with standardized folder structure
- Markdown note generation with YAML frontmatter
- Tags, links, wikilinks, and backlinks
- Document categorization and automatic filing

Vault structure:
  Knowledge/  Projects/  Ideas/  Research/  Conversations/
  Agents/  Documentation/  Code/  Archives/
"""

from obsidian.importer import ObsidianImporter
from obsidian.note_generator import NoteGenerator, ObsidianNote
from obsidian.structure import VaultFolder, VaultStructure
from obsidian.vault import ObsidianVault, VaultConfig

__all__ = [
    "ObsidianVault",
    "VaultConfig",
    "NoteGenerator",
    "ObsidianNote",
    "VaultStructure",
    "VaultFolder",
    "ObsidianImporter",
]
