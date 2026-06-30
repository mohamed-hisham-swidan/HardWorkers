"""Multi-expert system with specialized personas.

Provides 5 expert personas that collaboratively review plans before
major modifications:

1. Technical Architect — architecture, refactoring, design decisions
2. Cybersecurity Expert — security audits, vulnerability analysis
3. Python Expert — code quality, performance optimization
4. AI Expert — LLM systems, agents, RAG, fine-tuning
5. Obsidian Knowledge Expert — vault organization, knowledge graph
"""

from experts.ai_expert import AIExpert
from experts.base import ExpertBase, ExpertOpinion, ReviewVerdict
from experts.cybersecurity_expert import CybersecurityExpert
from experts.obsidian_expert import ObsidianExpert
from experts.python_expert import PythonExpert
from experts.review_board import ReviewBoard, ReviewResult
from experts.technical_architect import TechnicalArchitect

__all__ = [
    "ExpertBase",
    "ExpertOpinion",
    "ReviewVerdict",
    "TechnicalArchitect",
    "CybersecurityExpert",
    "PythonExpert",
    "AIExpert",
    "ObsidianExpert",
    "ReviewBoard",
    "ReviewResult",
]
