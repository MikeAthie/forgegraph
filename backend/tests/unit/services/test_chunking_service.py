from datetime import UTC, datetime, timedelta

from application.services.chunking_service import (
    Message,
    SlidingWindowChunking,
    TopicBasedChunking,
    TurnBasedChunking,
)


def _messages(count: int) -> list[Message]:
    start = datetime.now(UTC)
    return [
        Message(role="user", content=f"msg-{i}", timestamp=start + timedelta(seconds=i))
        for i in range(count)
    ]


def test_turn_based_chunking_with_overlap():
    chunker = TurnBasedChunking(chunk_size=3, overlap=1)
    chunks = chunker.chunk(_messages(5))
    assert len(chunks) == 2
    assert len(chunks[0].messages) == 3
    assert len(chunks[1].messages) == 3


def test_sliding_window_chunking():
    chunker = SlidingWindowChunking(window_size=4, overlap=2)
    chunks = chunker.chunk(_messages(6))
    assert len(chunks) == 2
    assert chunks[0].messages[0].content == "msg-0"
    assert chunks[1].messages[0].content == "msg-2"


def test_topic_based_chunking_respects_topic():
    messages = [
        Message(role="user", content="a", timestamp=datetime.now(UTC), metadata={"topic": "t1"}),
        Message(
            role="assistant", content="b", timestamp=datetime.now(UTC), metadata={"topic": "t1"}
        ),
        Message(role="user", content="c", timestamp=datetime.now(UTC), metadata={"topic": "t2"}),
    ]
    chunker = TopicBasedChunking()
    chunks = chunker.chunk(messages)
    assert len(chunks) == 2
    assert chunks[0].messages[0].metadata is not None
    assert chunks[0].messages[0].metadata["topic"] == "t1"
    assert chunks[1].messages[0].metadata is not None
    assert chunks[1].messages[0].metadata["topic"] == "t2"
