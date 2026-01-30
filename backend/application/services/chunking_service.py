from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    timestamp: datetime
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class Chunk:
    content: str
    messages: list[Message]
    chunk_type: str
    source_timestamp: datetime


class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, messages: list[Message]) -> list[Chunk]:
        raise NotImplementedError


class TurnBasedChunking(ChunkingStrategy):
    def __init__(self, chunk_size: int = 6, overlap: int = 1) -> None:
        self._chunk_size = max(1, chunk_size)
        self._overlap = max(0, min(overlap, self._chunk_size - 1))

    def chunk(self, messages: list[Message]) -> list[Chunk]:
        if not messages:
            return []

        chunks: list[Chunk] = []
        start = 0
        while start < len(messages):
            end = min(start + self._chunk_size, len(messages))
            batch = messages[start:end]
            chunks.append(_build_chunk(batch, "turn"))
            if end == len(messages):
                break
            start = end - self._overlap
        return chunks


class SlidingWindowChunking(ChunkingStrategy):
    def __init__(self, window_size: int = 10, overlap: int = 2) -> None:
        self._window_size = max(1, window_size)
        self._overlap = max(0, min(overlap, self._window_size - 1))

    def chunk(self, messages: list[Message]) -> list[Chunk]:
        if not messages:
            return []

        chunks: list[Chunk] = []
        start = 0
        while start < len(messages):
            end = min(start + self._window_size, len(messages))
            batch = messages[start:end]
            chunks.append(_build_chunk(batch, "window"))
            if end == len(messages):
                break
            start = end - self._overlap
        return chunks


class TopicBasedChunking(ChunkingStrategy):
    def __init__(self, fallback: ChunkingStrategy | None = None) -> None:
        self._fallback = fallback or TurnBasedChunking()

    def chunk(self, messages: list[Message]) -> list[Chunk]:
        if not messages:
            return []

        chunks: list[Chunk] = []
        current_topic = _topic_for(messages[0])
        current_messages: list[Message] = [messages[0]]

        for message in messages[1:]:
            topic = _topic_for(message)
            if topic and current_topic and topic != current_topic:
                chunks.append(_build_chunk(current_messages, "topic"))
                current_messages = [message]
                current_topic = topic
                continue
            current_messages.append(message)
            if current_topic is None:
                current_topic = topic

        if current_messages:
            chunks.append(_build_chunk(current_messages, "topic"))

        if len(chunks) == 1 and current_topic is None:
            return self._fallback.chunk(messages)
        return chunks


def _topic_for(message: Message) -> str | None:
    if message.metadata and message.metadata.get("topic"):
        return str(message.metadata["topic"])
    return None


def _build_chunk(messages: list[Message], chunk_type: str) -> Chunk:
    content = "\n".join(f"{msg.role}: {msg.content}" for msg in messages).strip()
    source_timestamp = messages[0].timestamp
    return Chunk(
        content=content,
        messages=messages,
        chunk_type=chunk_type,
        source_timestamp=source_timestamp,
    )
