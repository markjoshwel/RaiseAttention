"""tests for the cache module."""

from __future__ import annotations

import time
from pathlib import Path
from typing import cast

from raiseattention.cache import (
    CacheEntry,
    FileAnalysis,
    FileCache,
    FunctionDict,
)
from raiseattention.config import CacheConfig


class TestCacheEntry:
    """tests for the CacheEntry dataclass."""

    def test_creation(self) -> None:
        """Test cache entry creation."""
        data = FileAnalysis(
            file_path=Path("/test.py"),
            functions={},
            imports={},
            timestamp=time.time(),
        )

        entry = CacheEntry(
            data=data,
            mtime=1234567890.0,
            size=100,
            content_hash="abc123",
            timestamp=time.time(),
        )

        assert entry.mtime == 1234567890.0
        assert entry.size == 100
        assert entry.content_hash == "abc123"


class TestFileCache:
    """tests for the FileCache class."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that cache directory is created on init."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(enabled=True)

        _ = FileCache(config, cache_dir)

        assert cache_dir.exists()

    def test_init_creates_gitignore(self, tmp_path: Path) -> None:
        """Test that .gitignore is created in parent directory."""
        cache_dir = tmp_path / ".raiseattention" / "cache"
        config = CacheConfig(enabled=True)

        _ = FileCache(config, cache_dir)

        gitignore_path = tmp_path / ".raiseattention" / ".gitignore"
        assert gitignore_path.exists()
        assert gitignore_path.read_text() == "*\n"

    def test_init_does_not_overwrite_existing_gitignore(self, tmp_path: Path) -> None:
        """Test that existing .gitignore is not overwritten."""
        raiseattention_dir = tmp_path / ".raiseattention"
        raiseattention_dir.mkdir(parents=True)
        gitignore_path = raiseattention_dir / ".gitignore"
        _ = gitignore_path.write_text("existing content\n")

        cache_dir = raiseattention_dir / "cache"
        config = CacheConfig(enabled=True)
        _ = FileCache(config, cache_dir)

        assert gitignore_path.read_text() == "existing content\n"

    def test_store_recreates_gitignore_after_directory_deletion(self, tmp_path: Path) -> None:
        """Test that .gitignore is recreated when cache dir is deleted and recreated via store()."""
        import shutil

        raiseattention_dir = tmp_path / ".raiseattention"
        cache_dir = raiseattention_dir / "cache"
        gitignore_path = raiseattention_dir / ".gitignore"

        # create cache - this creates .gitignore
        config = CacheConfig(enabled=True)
        cache = FileCache(config, cache_dir)

        assert gitignore_path.exists(), ".gitignore should exist after init"

        # delete entire .raiseattention directory
        shutil.rmtree(raiseattention_dir)
        assert not raiseattention_dir.exists()

        # create a test file to store
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("x = 1")
        analysis = FileAnalysis(
            file_path=test_file,
            functions={},
            imports={},
            timestamp=time.time(),
        )

        # store should recreate directory AND .gitignore
        cache.store(test_file, analysis)

        assert cache_dir.exists(), "cache dir should be recreated"
        assert gitignore_path.exists(), ".gitignore should be recreated after store()"
        assert gitignore_path.read_text() == "*\n"

    def test_store_and_get(self, tmp_path: Path) -> None:
        """Test storing and retrieving cache entries."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(enabled=True)
        cache = FileCache(config, cache_dir)

        # create a test file
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("x = 1")

        # use cast to create a minimal FunctionDict for testing
        test_func_dict = cast(
            dict[str, FunctionDict],
            {"test_func": {"name": "test_func"}},
        )
        analysis = FileAnalysis(
            file_path=test_file,
            functions=test_func_dict,
            imports={},
            timestamp=time.time(),
        )

        # store
        cache.store(test_file, analysis)

        # retrieve
        retrieved = cache.get(test_file)

        assert retrieved is not None
        assert retrieved.functions["test_func"]["name"] == "test_func"

    def test_get_returns_none_when_disabled(self, tmp_path: Path) -> None:
        """Test that get returns None when cache is disabled."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(enabled=False)
        cache = FileCache(config, cache_dir)

        test_file = tmp_path / "test.py"
        _ = test_file.write_text("x = 1")

        result = cache.get(test_file)

        assert result is None

    def test_invalidation_on_file_change(self, tmp_path: Path) -> None:
        """Test that cache is invalidated when file changes."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(enabled=True, ttl_hours=24)
        cache = FileCache(config, cache_dir)

        # create and cache a file
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("x = 1")

        analysis = FileAnalysis(
            file_path=test_file,
            functions={},
            imports={},
            timestamp=time.time(),
        )
        cache.store(test_file, analysis)

        # modify the file
        time.sleep(0.01)  # ensure different mtime
        _ = test_file.write_text("x = 2")

        # cache should be invalid
        retrieved = cache.get(test_file)
        assert retrieved is None

    def test_invalidate_removes_entry(self, tmp_path: Path) -> None:
        """Test explicit invalidation of cache entries."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(enabled=True)
        cache = FileCache(config, cache_dir)

        test_file = tmp_path / "test.py"
        _ = test_file.write_text("x = 1")

        analysis = FileAnalysis(
            file_path=test_file,
            functions={},
            imports={},
            timestamp=time.time(),
        )
        cache.store(test_file, analysis)

        # invalidate
        cache.invalidate(test_file)

        # should be gone
        retrieved = cache.get(test_file)
        assert retrieved is None

    def test_clear_removes_all(self, tmp_path: Path) -> None:
        """Test clearing all cache entries."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(enabled=True)
        cache = FileCache(config, cache_dir)

        # create multiple entries
        for i in range(3):
            test_file = tmp_path / f"test{i}.py"
            _ = test_file.write_text(f"x = {i}")
            analysis = FileAnalysis(
                file_path=test_file,
                functions={},
                imports={},
                timestamp=time.time(),
            )
            cache.store(test_file, analysis)

        # clear
        cache.clear()

        # all should be gone
        for i in range(3):
            test_file = tmp_path / f"test{i}.py"
            assert cache.get(test_file) is None

    def test_prune_removes_stale(self, tmp_path: Path) -> None:
        """Test pruning stale cache entries."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(enabled=True)
        cache = FileCache(config, cache_dir)

        # create an entry for a file that exists
        existing_file = tmp_path / "existing.py"
        _ = existing_file.write_text("x = 1")
        analysis = FileAnalysis(
            file_path=existing_file,
            functions={},
            imports={},
            timestamp=time.time(),
        )
        cache.store(existing_file, analysis)

        # create a file, store it, then delete it to make it stale
        stale_file = tmp_path / "stale.py"
        _ = stale_file.write_text("x = 1")
        analysis2 = FileAnalysis(
            file_path=stale_file,
            functions={},
            imports={},
            timestamp=time.time(),
        )
        cache.store(stale_file, analysis2)
        stale_file.unlink()  # delete the file to make it stale

        # prune
        pruned = cache.prune()

        assert pruned >= 1

    def test_get_stats(self, tmp_path: Path) -> None:
        """Test getting cache statistics."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(enabled=True)
        cache = FileCache(config, cache_dir)

        # create an entry
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("x = 1")
        analysis = FileAnalysis(
            file_path=test_file,
            functions={},
            imports={},
            timestamp=time.time(),
        )
        cache.store(test_file, analysis)

        stats = cache.get_stats()

        assert "memory_entries" in stats
        assert "disk_entries" in stats
        assert stats["memory_entries"] == 1


class TestCacheTTL:
    """tests for cache time-to-live functionality."""

    def test_ttl_expiration(self, tmp_path: Path) -> None:
        """Test that entries expire after ttl."""
        cache_dir = tmp_path / "cache"
        # set very short ttl for testing
        config = CacheConfig(enabled=True, ttl_hours=0)
        cache = FileCache(config, cache_dir)

        test_file = tmp_path / "test.py"
        _ = test_file.write_text("x = 1")

        # create entry with old timestamp
        analysis = FileAnalysis(
            file_path=test_file,
            functions={},
            imports={},
            timestamp=time.time() - 1,  # 1 second ago
        )

        # manually create entry with expired timestamp
        entry = CacheEntry(
            data=analysis,
            mtime=test_file.stat().st_mtime,
            size=test_file.stat().st_size,
            content_hash=cache._hash_file(test_file),  # pyright: ignore[reportPrivateUsage]
            timestamp=time.time() - 3600,  # 1 hour ago
        )

        cache._memory_cache[str(test_file.resolve())] = entry  # pyright: ignore[reportPrivateUsage]

        # should be expired (ttl=0 means immediate expiration)
        # actually, let's test with a more reasonable scenario
        # the ttl check is: time.time() - entry.timestamp > ttl_hours * 3600
        # with ttl_hours=0, everything older than now is expired

        # let's just verify the logic works
        retrieved = cache.get(test_file)
        # with ttl=0, the entry should be considered expired
        # but since we set timestamp to 1 hour ago, it definitely should be expired
        assert retrieved is None
