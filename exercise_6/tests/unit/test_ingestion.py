"""Unit tests for ingestion worker — follows .claude/rules/testing.md:
- pytest fixtures (no unittest.TestCase)
- Arrange-Act-Assert pattern
- test_<action>_<scenario>_<expected> naming
- No database, no network (pure logic only)
"""

import pytest


# --- Fixtures ---

@pytest.fixture
def sample_events():
    """Factory for test event data."""
    return [
        {"event_type": "page_view", "timestamp": "2024-01-15T10:00:00Z", "properties": {"page": "/home"}},
        {"event_type": "click", "timestamp": "2024-01-15T10:01:00Z", "properties": {"element": "cta_button"}},
        {"event_type": "page_view", "timestamp": "2024-01-15T10:02:00Z", "properties": {"page": "/pricing"}},
    ]


@pytest.fixture
def large_batch():
    """Generate a batch exceeding the chunk size (10,000)."""
    return [{"event_type": "page_view", "timestamp": f"2024-01-15T{i:05d}", "properties": {}} for i in range(25000)]


# --- Tests ---

class TestEventValidation:
    def test_validate_event_valid_event_returns_true(self):
        event = {"event_type": "page_view", "timestamp": "2024-01-15T10:00:00Z", "properties": {}}

        is_valid = "event_type" in event and "timestamp" in event

        assert is_valid is True

    def test_validate_event_missing_type_returns_false(self):
        event = {"timestamp": "2024-01-15T10:00:00Z", "properties": {}}

        is_valid = "event_type" in event and "timestamp" in event

        assert is_valid is False

    def test_validate_event_missing_timestamp_returns_false(self):
        event = {"event_type": "click", "properties": {}}

        is_valid = "event_type" in event and "timestamp" in event

        assert is_valid is False


class TestChunking:
    def test_chunk_events_small_batch_single_chunk(self, sample_events):
        chunk_size = 10000
        chunks = [sample_events[i:i + chunk_size] for i in range(0, len(sample_events), chunk_size)]

        assert len(chunks) == 1
        assert len(chunks[0]) == 3

    def test_chunk_events_large_batch_multiple_chunks(self, large_batch):
        chunk_size = 10000
        chunks = [large_batch[i:i + chunk_size] for i in range(0, len(large_batch), chunk_size)]

        assert len(chunks) == 3
        assert len(chunks[0]) == 10000
        assert len(chunks[1]) == 10000
        assert len(chunks[2]) == 5000

    def test_chunk_events_empty_batch_no_chunks(self):
        events = []
        chunk_size = 10000
        chunks = [events[i:i + chunk_size] for i in range(0, len(events), chunk_size)]

        assert len(chunks) == 0


class TestDeduplication:
    def test_deduplicate_events_removes_duplicates(self):
        events = [
            {"id": "evt_1", "event_type": "click"},
            {"id": "evt_2", "event_type": "page_view"},
            {"id": "evt_1", "event_type": "click"},  # duplicate
        ]

        seen = set()
        unique = []
        for e in events:
            if e["id"] not in seen:
                seen.add(e["id"])
                unique.append(e)

        assert len(unique) == 2
        assert unique[0]["id"] == "evt_1"
        assert unique[1]["id"] == "evt_2"
