"""Human-reviewed knowledge-gap candidate boundary."""

from app.knowledge_gap.models import KnowledgeGap
from app.knowledge_gap.repository import JsonlKnowledgeGapRepository, KnowledgeGapRepository

__all__ = ["JsonlKnowledgeGapRepository", "KnowledgeGap", "KnowledgeGapRepository"]
