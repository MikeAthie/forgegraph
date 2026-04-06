from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from application.services.memory_gc import GCResult, MemoryGCService


class TestGCResult:
    def test_default_values(self):
        result = GCResult()
        assert result.chunks_deleted == 0
        assert result.entries_deleted == 0
        assert result.orphaned_tenant_ids == []
        assert result.dry_run is False
        assert result.errors == []

    def test_custom_values(self):
        tenant_id = uuid4()
        result = GCResult(
            chunks_deleted=10,
            entries_deleted=5,
            orphaned_tenant_ids=[tenant_id],
            dry_run=True,
            errors=["test error"],
        )
        assert result.chunks_deleted == 10
        assert result.entries_deleted == 5
        assert result.orphaned_tenant_ids == [tenant_id]
        assert result.dry_run is True
        assert result.errors == ["test error"]


class TestGetValidTenantIds:
    @pytest.mark.django_db
    def test_includes_organization_ids(self, user):
        gc = MemoryGCService(batch_size=10)
        valid_ids = gc.get_valid_tenant_ids()
        assert user.default_organization_id in valid_ids

    @pytest.mark.django_db
    def test_excludes_graph_ids(self, graph):
        gc = MemoryGCService(batch_size=10)
        valid_ids = gc.get_valid_tenant_ids()
        assert graph.id not in valid_ids

    @pytest.mark.django_db
    def test_excludes_non_canonical_user_ids(self, user):
        gc = MemoryGCService(batch_size=10)
        valid_ids = gc.get_valid_tenant_ids()
        assert user.id not in valid_ids

    @pytest.mark.django_db
    def test_returns_only_canonical_tenant_ids(self, user, graph):
        gc = MemoryGCService(batch_size=10)
        valid_ids = gc.get_valid_tenant_ids()
        assert len(valid_ids) >= 1
        assert user.default_organization_id in valid_ids
        assert graph.id not in valid_ids
        assert user.id not in valid_ids


class TestFindOrphanedTenantIds:
    @pytest.mark.django_db
    def test_finds_orphaned_ids(self, memory_chunk_factory):
        gc = MemoryGCService(batch_size=10)
        orphan_id = uuid4()
        memory_chunk_factory(tenant_id=orphan_id)

        orphans = gc.find_orphaned_tenant_ids()
        assert orphan_id in orphans

    @pytest.mark.django_db
    def test_excludes_valid_user_ids(self, user, memory_chunk_factory):
        gc = MemoryGCService(batch_size=10)
        memory_chunk_factory(tenant_id=user.default_organization_id)

        orphans = gc.find_orphaned_tenant_ids()
        assert user.default_organization_id not in orphans

    @pytest.mark.django_db
    def test_marks_non_canonical_graph_ids_as_orphaned(self, graph, memory_chunk_factory):
        gc = MemoryGCService(batch_size=10)
        memory_chunk_factory(tenant_id=graph.id)

        orphans = gc.find_orphaned_tenant_ids()
        assert graph.id in orphans


class TestCleanupOrphanedChunks:
    @pytest.mark.django_db
    def test_dry_run_does_not_delete(self, memory_chunk_factory, user):
        from infrastructure.orm.models import MemoryChunk

        gc = MemoryGCService(batch_size=10)
        memory_chunk_factory(tenant_id=user.default_organization_id)
        orphan_id = uuid4()
        chunk = memory_chunk_factory(tenant_id=orphan_id)

        result = gc.cleanup_orphaned_chunks(dry_run=True)

        assert result.dry_run is True
        assert result.chunks_deleted == 1
        assert MemoryChunk.objects.filter(id=chunk.id).exists()

    @pytest.mark.django_db
    def test_deletes_orphaned_chunks(self, memory_chunk_factory, user):
        from infrastructure.orm.models import MemoryChunk

        gc = MemoryGCService(batch_size=10)
        memory_chunk_factory(tenant_id=user.default_organization_id)
        orphan_id = uuid4()
        chunk = memory_chunk_factory(tenant_id=orphan_id)

        result = gc.cleanup_orphaned_chunks(dry_run=False)

        assert result.chunks_deleted == 1
        assert not MemoryChunk.objects.filter(id=chunk.id).exists()

    @pytest.mark.django_db
    def test_preserves_valid_organization_chunks(self, user, memory_chunk_factory):
        from infrastructure.orm.models import MemoryChunk

        gc = MemoryGCService(batch_size=10)
        chunk = memory_chunk_factory(tenant_id=user.default_organization_id)

        gc.cleanup_orphaned_chunks(dry_run=False)

        assert MemoryChunk.objects.filter(id=chunk.id).exists()

    @pytest.mark.django_db
    def test_deletes_non_canonical_graph_scoped_chunks(self, graph, memory_chunk_factory):
        from infrastructure.orm.models import MemoryChunk

        gc = MemoryGCService(batch_size=10)
        memory_chunk_factory(tenant_id=graph.owner.default_organization_id)
        chunk = memory_chunk_factory(tenant_id=graph.id)

        gc.cleanup_orphaned_chunks(dry_run=False)

        assert not MemoryChunk.objects.filter(id=chunk.id).exists()


class TestCleanupExpiredEntries:
    @pytest.mark.django_db
    def test_deletes_expired_entries(self, memory_entry_factory):
        from infrastructure.orm.models import MemoryEntry

        gc = MemoryGCService(batch_size=10)

        # Expired entry
        expired = memory_entry_factory(expires_at=datetime.now(UTC) - timedelta(hours=1))

        # Valid entry
        valid = memory_entry_factory(expires_at=datetime.now(UTC) + timedelta(hours=1))

        result = gc.cleanup_expired_entries(dry_run=False)

        assert result.entries_deleted == 1
        assert not MemoryEntry.objects.filter(id=expired.id).exists()
        assert MemoryEntry.objects.filter(id=valid.id).exists()

    @pytest.mark.django_db
    def test_dry_run_does_not_delete(self, memory_entry_factory):
        from infrastructure.orm.models import MemoryEntry

        gc = MemoryGCService(batch_size=10)
        expired = memory_entry_factory(expires_at=datetime.now(UTC) - timedelta(hours=1))

        result = gc.cleanup_expired_entries(dry_run=True)

        assert result.dry_run is True
        assert result.entries_deleted == 1
        assert MemoryEntry.objects.filter(id=expired.id).exists()


class TestCleanupOldChunks:
    @pytest.mark.django_db
    def test_deletes_old_chunks(self, user, memory_chunk_factory):
        from infrastructure.orm.models import MemoryChunk

        gc = MemoryGCService(batch_size=10, chunk_retention_days=90)

        # Create old chunk and manually set created_at
        old_chunk = memory_chunk_factory(tenant_id=user.default_organization_id)
        MemoryChunk.objects.filter(id=old_chunk.id).update(
            created_at=datetime.now(UTC) - timedelta(days=100)
        )

        # Create new chunk
        new_chunk = memory_chunk_factory(tenant_id=user.default_organization_id)

        result = gc.cleanup_old_chunks(max_age_days=90, dry_run=False)

        assert result.chunks_deleted == 1
        assert not MemoryChunk.objects.filter(id=old_chunk.id).exists()
        assert MemoryChunk.objects.filter(id=new_chunk.id).exists()


class TestRunFullGC:
    @pytest.mark.django_db
    def test_returns_summary_dict(self, user):
        gc = MemoryGCService(batch_size=10)
        result = gc.run_full_gc(dry_run=True)

        assert "dry_run" in result
        assert result["dry_run"] is True
        assert "expired_entries_deleted" in result
        assert "orphaned_chunks_deleted" in result
        assert "orphaned_tenant_ids" in result
        assert "old_chunks_deleted" in result
        assert "total_deleted" in result
        assert "errors" in result


class TestCompatibilityCleanup:
    @pytest.mark.django_db
    def test_prune_missing_users_removes_non_canonical_non_tenant_chunks(
        self, user, graph, memory_chunk_factory
    ):
        """Compatibility cleanup should keep organization chunks and delete non-canonical scopes."""
        from infrastructure.orm.models import MemoryChunk

        gc = MemoryGCService(batch_size=10)

        # Create one canonical tenant chunk and two non-canonical chunks.
        organization_chunk = memory_chunk_factory(tenant_id=user.default_organization_id)
        user_chunk = memory_chunk_factory(tenant_id=user.id)
        graph_chunk = memory_chunk_factory(tenant_id=graph.id)
        orphan_id = uuid4()
        orphan_chunk = memory_chunk_factory(tenant_id=orphan_id)

        stats = gc.cleanup(retention_days=0, prune_missing_users=True)

        assert stats["deleted_missing_users"] == 3
        assert MemoryChunk.objects.filter(id=organization_chunk.id).exists()
        assert not MemoryChunk.objects.filter(id=user_chunk.id).exists()
        assert not MemoryChunk.objects.filter(id=graph_chunk.id).exists()
        assert not MemoryChunk.objects.filter(id=orphan_chunk.id).exists()


# Fixtures
@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    from application.services.tenancy import ensure_default_organization

    User = get_user_model()
    user = User.objects.create_user(
        email=f"test_{uuid4().hex[:8]}@example.com", password="testpass"
    )
    ensure_default_organization(user)
    return user


@pytest.fixture
def graph(db, user):
    from infrastructure.orm.models import Graph

    return Graph.objects.create(id=uuid4(), name="Test Graph", owner=user)


@pytest.fixture
def memory_chunk_factory(db):
    from infrastructure.orm.models import MemoryChunk

    def _create(tenant_id=None, **kwargs):
        if tenant_id is None:
            tenant_id = uuid4()
        defaults = {
            "tenant_id": tenant_id,
            "content": "test content",
            "embedding": [0.1] * 1536,
            "source_timestamp": datetime.now(UTC),
        }
        defaults.update(kwargs)
        return MemoryChunk.objects.create(**defaults)

    return _create


@pytest.fixture
def memory_entry_factory(db):
    from infrastructure.orm.models import MemoryEntry

    def _create(**kwargs):
        defaults = {
            "namespace": f"test_{uuid4().hex[:8]}",
            "key": f"key_{uuid4().hex[:8]}",
            "value_json": {"test": True},
        }
        defaults.update(kwargs)
        return MemoryEntry.objects.create(**defaults)

    return _create
