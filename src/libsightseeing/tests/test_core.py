"""tests for the libsightseeing package."""

from __future__ import annotations

from pathlib import Path

from libsightseeing import SourceResolver, find_files


class TestFindFiles:
    """tests for the find_files convenience function."""

    def test_find_files_basic(self, tmp_path: Path) -> None:
        """test basic file finding."""
        # create test files
        (tmp_path / "file1.py").write_text("x = 1")
        (tmp_path / "file2.py").write_text("y = 2")
        (tmp_path / "readme.md").write_text("# readme")

        files = find_files(tmp_path, include=["*.py"])

        assert len(files) == 2
        assert all(f.suffix == ".py" for f in files)

    def test_find_files_with_exclude(self, tmp_path: Path) -> None:
        """test file finding with exclude patterns."""
        (tmp_path / "main.py").write_text("main")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "script.py").write_text("venv script")

        files = find_files(tmp_path, include=["*.py"])

        # .venv is excluded by default
        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_find_files_respects_gitignore(self, tmp_path: Path) -> None:
        """test that .gitignore files are respected."""
        (tmp_path / "main.py").write_text("main")
        (tmp_path / "ignored.py").write_text("ignored")
        (tmp_path / ".gitignore").write_text("ignored.py\n")

        files = find_files(tmp_path, include=["*.py"])

        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_find_files_include_ignored(self, tmp_path: Path) -> None:
        """test including gitignored files."""
        (tmp_path / "main.py").write_text("main")
        (tmp_path / "ignored.py").write_text("ignored")
        (tmp_path / ".gitignore").write_text("ignored.py\n")

        files = find_files(tmp_path, include=["*.py"], respect_gitignore=False)

        assert len(files) == 2


class TestSourceResolver:
    """tests for the SourceResolver class."""

    def test_resolver_initialization(self, tmp_path: Path) -> None:
        """test resolver initialisation."""
        resolver = SourceResolver(root=tmp_path)

        assert resolver.root == tmp_path.resolve()
        assert resolver.respect_gitignore is True
        assert ".venv" in resolver.exclude

    def test_resolver_resolve_empty_directory(self, tmp_path: Path) -> None:
        """test resolving an empty directory."""
        resolver = SourceResolver(root=tmp_path)
        files = resolver.resolve()

        assert files == ()

    def test_resolver_resolve_with_files(self, tmp_path: Path) -> None:
        """test resolving files."""
        (tmp_path / "file.py").write_text("x = 1")

        resolver = SourceResolver(root=tmp_path, include=["*.py"])
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "file.py"

    def test_resolver_nonexistent_root(self, tmp_path: Path) -> None:
        """test resolver with non-existent root."""
        nonexistent = tmp_path / "does_not_exist"
        resolver = SourceResolver(root=nonexistent)
        files = resolver.resolve()

        assert files == ()

    def test_resolver_nested_directories(self, tmp_path: Path) -> None:
        """test resolver with nested directories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("main")
        (tmp_path / "src" / "utils").mkdir()
        (tmp_path / "src" / "utils" / "helper.py").write_text("helper")

        resolver = SourceResolver(root=tmp_path, include=["**/*.py"])
        files = resolver.resolve()

        assert len(files) == 2
        file_names = {f.name for f in files}
        assert file_names == {"main.py", "helper.py"}


class TestGitignoreRespect:
    """tests for .gitignore handling."""

    def test_gitignore_in_root(self, tmp_path: Path) -> None:
        """test .gitignore in root directory."""
        (tmp_path / "keep.py").write_text("keep")
        (tmp_path / "ignore.py").write_text("ignore")
        (tmp_path / ".gitignore").write_text("ignore.py\n")

        resolver = SourceResolver(root=tmp_path, include=["*.py"])
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "keep.py"

    def test_gitignore_in_subdirectories(self, tmp_path: Path) -> None:
        """test .gitignore files in subdirectories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("main")
        (tmp_path / "src" / "temp.py").write_text("temp")
        (tmp_path / "src" / ".gitignore").write_text("temp.py\n")

        resolver = SourceResolver(root=tmp_path, include=["**/*.py"])
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_gitignore_negation(self, tmp_path: Path) -> None:
        """test .gitignore negation patterns."""
        (tmp_path / "all.py").write_text("all")
        (tmp_path / "except.py").write_text("except")
        (tmp_path / ".gitignore").write_text("*.py\n!except.py\n")

        resolver = SourceResolver(root=tmp_path, include=["*.py"])
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "except.py"


class TestPatternMatching:
    """tests for include/exclude pattern matching."""

    def test_include_pattern(self, tmp_path: Path) -> None:
        """test include patterns."""
        (tmp_path / "main.py").write_text("main")
        (tmp_path / "readme.md").write_text("readme")

        resolver = SourceResolver(root=tmp_path, include=["*.py"])
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_exclude_pattern(self, tmp_path: Path) -> None:
        """test exclude patterns."""
        (tmp_path / "main.py").write_text("main")
        (tmp_path / "test.py").write_text("test")

        resolver = SourceResolver(
            root=tmp_path,
            include=["*.py"],
            exclude=["test.py"],
        )
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_globstar_pattern(self, tmp_path: Path) -> None:
        """test ** glob patterns."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("main")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test.py").write_text("test")

        resolver = SourceResolver(root=tmp_path, include=["src/**/*.py"])
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "main.py"
