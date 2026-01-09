"""API clients for external services."""

from papersqueeze.api.paperless import PaperlessClient, DocumentSnapshot, DocumentPatch

__all__ = ["PaperlessClient", "DocumentSnapshot", "DocumentPatch"]

# LLM clients loaded on-demand (require optional dependencies)
# from papersqueeze.api.claude import ClaudeClient
