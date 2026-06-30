"""Knowledge extraction engine — concept analysis, relationship mapping, and backlink generation.

Provides intelligent knowledge management features:
- Core knowledge extraction from code, documents, and conversations
- Concept analysis with definitions, usage patterns, and importance scoring
- Relationship mapping between concepts across the knowledge base
- Backlink generation for cross-referencing and knowledge graph construction
"""

from knowledge.backlink_generator import Backlink, BacklinkGenerator
from knowledge.concept_analyzer import Concept, ConceptAnalyzer, ConceptRelation
from knowledge.extractor import ExtractedKnowledge, KnowledgeExtractorEngine, KnowledgeSource
from knowledge.relationship_map import Relationship, RelationshipMap, RelationshipType

__all__ = [
    "KnowledgeExtractorEngine",
    "ExtractedKnowledge",
    "KnowledgeSource",
    "ConceptAnalyzer",
    "Concept",
    "ConceptRelation",
    "RelationshipMap",
    "Relationship",
    "RelationshipType",
    "BacklinkGenerator",
    "Backlink",
]
