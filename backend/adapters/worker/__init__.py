"""Worker adapters (Celery tasks)."""

from .embedding_worker import process_embeddings  # noqa: F401
from .gc_worker import run_memory_gc  # noqa: F401
