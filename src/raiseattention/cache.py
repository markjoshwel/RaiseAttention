"""
multi-tier caching system for raiseattention.

implements file-level, dependency, and incremental caching
with proper invalidation strategies.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar, final

from .config import CacheConfig

if TYPE_CHECKING:
    pass

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """
    a single cache entry with metadata.

    attributes:
        `data: T`
            cached data
        `mtime: float`
            file modification time
        `size: int`
            file size in bytes
        `content_hash: str`
            sha-256 hash of file content
        `timestamp: float`
            when this entry was cached
    """

    data: T
    mtime: float
    size: int
    content_hash: str
    timestamp: float


@dataclass
class FileAnalysis:
    """
    analysis result for a single file.

    attributes:
        `file_path: Path`
            path to the analysed file
        `functions: dict`
            function information from ast visitor
        `imports: dict`
            import mappings
        `timestamp: float`
            when analysis was performed
        `try_except_blocks: list`
            try-except block information
    """

    file_path: Path
    functions: dict[str, Any]
    imports: dict[str, str]
    timestamp: float
    try_except_blocks: list[dict[str, Any]] = field(default_factory=list)


@final
class FileCache:
    """
    file-level cache for analysis results.

    caches parsed ast and exception signatures for each file
    with mtime, size, and content hash invalidation.

    attributes:
        `config: CacheConfig`
            cache configuration
        `cache_dir: Path`
            directory for persistent cache storage
        `_memory_cache: dict[str, CacheEntry]`
            in-memory cache storage
    """

    config: CacheConfig
    cache_dir: Path
    _memory_cache: dict[str, CacheEntry[FileAnalysis]]

    def __init__(self, config: CacheConfig, cache_dir: Path | None = None) -> None:
        """
        Initialise file cache.

        arguments:
            `config: CacheConfig`
                cache configuration
            `cache_dir: Path | None`
                directory for cache files (default: .raiseattention/cache)
        """
        self.config = config
        if cache_dir is not None:
            self.cache_dir = cache_dir
        else:
            # respect xdg cache home if set, otherwise use local .raiseattention
            base_dir = Path(os.environ.get("XDG_CACHE_HOME", ".raiseattention"))
            self.cache_dir = base_dir.joinpath("cache")
        self._memory_cache: dict[str, CacheEntry[FileAnalysis]] = {}

        if self.config.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_persistent_cache()

    def get(self, file_path: str | Path) -> FileAnalysis | None:
        """
        Retrieve cached analysis if file hasn't changed.

        arguments:
            `file_path: str | Path`
                path to the file

        returns: `FileAnalysis | None`
            cached analysis or none if invalid/missing
        """
        if not self.config.enabled:
            return None

        file_path = Path(file_path)
        cache_key = str(file_path.resolve())

        # check memory cache first
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if self._is_valid(entry, file_path):
                return entry.data
            else:
                del self._memory_cache[cache_key]

        # check persistent cache
        cache_file = self._get_cache_file(cache_key)
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    disk_entry: CacheEntry[FileAnalysis] = pickle.load(f)  # pyright: ignore[reportAny]

                if self._is_valid(disk_entry, file_path):
                    # promote to memory cache
                    self._memory_cache[cache_key] = disk_entry
                    return disk_entry.data
                else:
                    # invalid entry, remove
                    cache_file.unlink()
            except (pickle.PickleError, OSError):
                pass

        return None

    def store(self, file_path: str | Path, analysis: FileAnalysis) -> None:
        """
        cache analysis result with metadata.

        arguments:
            `file_path: str | Path`
                path to the file
            `analysis: FileAnalysis`
                analysis result to cache
        """
        if not self.config.enabled:
            return

        file_path = Path(file_path)
        cache_key = str(file_path.resolve())

        # compute metadata
        stat = file_path.stat()
        content_hash = self._hash_file(file_path)

        entry = CacheEntry(
            data=analysis,
            mtime=stat.st_mtime,
            size=stat.st_size,
            content_hash=content_hash,
            timestamp=time.time(),
        )

        # store in memory
        self._memory_cache[cache_key] = entry

        # evict old entries if necessary
        self._evict_if_needed()

        # store persistently
        cache_file = self._get_cache_file(cache_key)
        try:
            with open(cache_file, "wb") as f:
                pickle.dump(entry, f)
        except OSError:
            pass

    def invalidate(self, file_path: str | Path) -> None:
        """
        Invalidate cache entry for a file.

        arguments:
            `file_path: str | Path`
                path to the file
        """
        file_path = Path(file_path)
        cache_key = str(file_path.resolve())

        # remove from memory
        if cache_key in self._memory_cache:
            del self._memory_cache[cache_key]

        # remove from disk
        cache_file = self._get_cache_file(cache_key)
        if cache_file.exists():
            with suppress(OSError):
                cache_file.unlink()

    def clear(self) -> None:
        """Clear all cache entries."""
        self._memory_cache.clear()

        if self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.cache"):
                with suppress(OSError):
                    cache_file.unlink()

    def prune(self) -> int:
        """
        Remove stale cache entries for deleted files.

        returns: `int`
            number of entries pruned
        """
        pruned = 0

        # prune memory cache
        keys_to_remove = []
        for cache_key in list(self._memory_cache.keys()):
            if not Path(cache_key).exists():
                keys_to_remove.append(cache_key)

        for key in keys_to_remove:
            del self._memory_cache[key]
            pruned += 1

        # prune persistent cache
        if self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.cache"):
                try:
                    with open(cache_file, "rb") as f:
                        entry: CacheEntry[FileAnalysis] = pickle.load(f)  # pyright: ignore[reportAny]

                    if not entry.data.file_path.exists():
                        cache_file.unlink()
                        pruned += 1
                except (pickle.PickleError, OSError, AttributeError):
                    # corrupt or old format, remove
                    try:
                        cache_file.unlink()
                        pruned += 1
                    except OSError:
                        pass

        return pruned

    def get_stats(self) -> dict[str, int]:
        """
        Get cache statistics.

        returns: `dict[str, int]`
            dictionary with cache statistics
        """
        disk_entries = 0
        if self.cache_dir.exists():
            disk_entries = len(list(self.cache_dir.glob("*.cache")))

        return {
            "memory_entries": len(self._memory_cache),
            "disk_entries": disk_entries,
            "total_entries": len(self._memory_cache) + disk_entries,
        }

    def _is_valid(self, entry: CacheEntry[FileAnalysis], file_path: Path) -> bool:
        """
        check if a cache entry is still valid.

        arguments:
            `entry: CacheEntry[FileAnalysis]`
                cache entry to validate
            `file_path: Path`
                path to the file

        returns: `bool`
            true if entry is valid
        """
        # check if file still exists
        if not file_path.exists():
            return False

        # check ttl
        if time.time() - entry.timestamp > self.config.ttl_hours * 3600:
            return False

        # check mtime and size (fast)
        stat = file_path.stat()
        if entry.mtime != stat.st_mtime or entry.size != stat.st_size:
            return False

        # check content hash (definitive)
        current_hash = self._hash_file(file_path)
        return entry.content_hash == current_hash

    def _hash_file(self, file_path: Path) -> str:
        """
        Compute sha-256 hash of file content.

        arguments:
            `file_path: Path`
                path to the file

        returns: `str`
            hexadecimal hash string
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _get_cache_file(self, cache_key: str) -> Path:
        """
        Get cache file path for a cache key.

        arguments:
            `cache_key: str`
                cache key

        returns: `Path`
            path to cache file
        """
        # hash the key to create a safe filename
        key_hash = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{key_hash}.cache"

    def _evict_if_needed(self) -> None:
        """Evict old entries if memory cache exceeds limit."""
        if len(self._memory_cache) <= self.config.max_file_entries:
            return

        # sort by timestamp and remove oldest
        sorted_entries = sorted(self._memory_cache.items(), key=lambda x: x[1].timestamp)

        to_remove = len(sorted_entries) - self.config.max_file_entries
        for i in range(to_remove):
            del self._memory_cache[sorted_entries[i][0]]

    def _load_persistent_cache(self) -> None:
        """Load cache entries from disk into memory (lazy loading)."""
        # we don't load all entries into memory immediately
        # instead, we load them on-demand in get()
        pass


@final
class DependencyCache:
    """
    cache for external library exception signatures.

    caches exception signatures of dependencies by package name and version.
    stored globally and shared across projects.

    attributes:
        `config: CacheConfig`
            cache configuration
        `cache_dir: Path`
            global cache directory
    """

    config: CacheConfig
    cache_dir: Path

    def __init__(self, config: CacheConfig) -> None:
        """
        Initialise dependency cache.

        arguments:
            `config: CacheConfig`
                cache configuration
        """
        self.config = config

        # global cache in user's home directory
        if sys.platform == "win32":
            base_dir = Path(os.environ.get("LOCALAPPDATA", "~")).expanduser()
        else:
            base_dir = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser()

        self.cache_dir = base_dir.joinpath("raiseattention/dependencies")

        if self.config.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, package: str, version: str) -> dict[str, Any] | None:
        """
        Get cached exception signatures for a package version.

        arguments:
            `package: str`
                package name
            `version: str`
                package version

        returns: `dict[str, Any] | None`
            cached exception signatures or none
        """
        if not self.config.enabled:
            return None

        cache_key = f"{package}@{version}"
        cache_file = self._get_cache_file(cache_key)

        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    result: dict[str, Any] = pickle.load(f)  # pyright: ignore[reportAny]
                    return result
            except (pickle.PickleError, OSError):
                pass

        return None

    def store(self, package: str, version: str, exceptions: dict[str, Any]) -> None:
        """
        cache exception signatures for a package version.

        arguments:
            `package: str`
                package name
            `version: str`
                package version
            `exceptions: dict[str, Any]`
                exception signatures to cache
        """
        if not self.config.enabled:
            return

        cache_key = f"{package}@{version}"
        cache_file = self._get_cache_file(cache_key)

        try:
            with open(cache_file, "wb") as f:
                pickle.dump(exceptions, f)
        except OSError:
            pass

    def _get_cache_file(self, cache_key: str) -> Path:
        """
        Get cache file path for a cache key.

        arguments:
            `cache_key: str`
                cache key

        returns: `Path`
            path to cache file
        """
        key_hash = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{key_hash}.dep"
