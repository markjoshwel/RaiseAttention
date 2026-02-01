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

    def test_find_files_with_explicit_exclude(self, tmp_path: Path) -> None:
        """test find_files with explicit exclude parameter."""
        (tmp_path / "main.py").write_text("main")
        (tmp_path / "test.py").write_text("test")

        # when exclude is explicitly provided, it should override defaults
        files = find_files(tmp_path, include=["*.py"], exclude=["test.py"])

        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_find_files_no_include_pattern(self, tmp_path: Path) -> None:
        """test find_files without include pattern finds all files."""
        (tmp_path / "main.py").write_text("main")
        (tmp_path / "readme.md").write_text("readme")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "script.py").write_text("venv script")

        files = find_files(tmp_path)

        # should find main.py and readme.md, but not .venv/script.py
        assert len(files) == 2
        file_names = {f.name for f in files}
        assert file_names == {"main.py", "readme.md"}


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

    def test_gitignore_directory_ignored(self, tmp_path: Path) -> None:
        """test that files in ignored directories are excluded."""
        (tmp_path / "main.py").write_text("main")
        (tmp_path / "build").mkdir()
        (tmp_path / "build" / "output.py").write_text("output")
        (tmp_path / ".gitignore").write_text("build/\n")

        resolver = SourceResolver(root=tmp_path, include=["**/*.py"])
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_gitignore_empty_lines_and_comments(self, tmp_path: Path) -> None:
        """test that empty lines and comments in .gitignore are skipped."""
        (tmp_path / "main.py").write_text("main")
        (tmp_path / "ignored.py").write_text("ignored")
        (tmp_path / ".gitignore").write_text("# this is a comment\n\nignored.py\n")

        resolver = SourceResolver(root=tmp_path, include=["*.py"])
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_gitignore_invalid_encoding(self, tmp_path: Path) -> None:
        """test handling of .gitignore files with invalid encoding."""
        (tmp_path / "main.py").write_text("main")
        gitignore = tmp_path / ".gitignore"
        gitignore.write_bytes(b"\xff\xfeignored.py\n")  # invalid utf-8

        # should not raise, just skip the file
        resolver = SourceResolver(root=tmp_path, include=["*.py"])
        files = resolver.resolve()

        # file should be found since .gitignore couldn't be read
        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_gitignore_permission_error(self, tmp_path: Path) -> None:
        """test handling of .gitignore files that can't be read."""
        (tmp_path / "main.py").write_text("main")
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("ignored.py\n")

        # make file unreadable (this might not work on Windows, so we skip if it fails)
        try:
            gitignore.chmod(0o000)
            resolver = SourceResolver(root=tmp_path, include=["*.py"])
            files = resolver.resolve()
            # should not raise, just skip the file
            assert len(files) == 1
            assert files[0].name == "main.py"
        except (OSError, PermissionError):
            # skip test if we can't change permissions
            pass
        finally:
            # restore permissions for cleanup
            try:
                gitignore.chmod(0o644)
            except (OSError, PermissionError):
                pass

    def test_gitignore_directory_not_file(self, tmp_path: Path) -> None:
        """test that .gitignore directories are skipped."""
        (tmp_path / "main.py").write_text("main")
        # create a directory named .gitignore (edge case)
        (tmp_path / ".gitignore").mkdir()

        resolver = SourceResolver(root=tmp_path, include=["*.py"])
        files = resolver.resolve()

        # should find the file since .gitignore is a directory, not a file
        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_gitignore_parent_directory_traversal(self, tmp_path: Path) -> None:
        """test that parent directory gitignore rules are applied."""
        (tmp_path / "main.py").write_text("main")
        # create a deeply nested file
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        (tmp_path / "a" / "b" / "c" / "deep.py").write_text("deep")
        # ignore the 'b' directory
        (tmp_path / ".gitignore").write_text("a/b/\n")

        resolver = SourceResolver(root=tmp_path, include=["**/*.py"])
        files = resolver.resolve()

        # should only find main.py, not deep.py
        assert len(files) == 1
        assert files[0].name == "main.py"


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

    def test_pattern_file_outside_root(self, tmp_path: Path) -> None:
        """test pattern matching for files outside root (edge case)."""
        from libsightseeing.patterns import PatternMatcher

        # create a file path that's outside the root
        root = tmp_path / "project"
        root.mkdir()
        outside_file = tmp_path / "outside.py"
        outside_file.write_text("outside")

        pm = PatternMatcher(include=["*.py"], exclude=[])
        # this should handle the ValueError and use absolute path
        result = pm.matches(outside_file, root)

        # should match since we use absolute path when relative fails
        assert result is True

    def test_pattern_doublestar_suffix_only(self, tmp_path: Path) -> None:
        """test ** pattern matching with suffix only pattern."""
        (tmp_path / "deep").mkdir()
        (tmp_path / "deep" / "nested").mkdir()
        (tmp_path / "deep" / "nested" / "file.py").write_text("deep")

        resolver = SourceResolver(root=tmp_path, include=["**/file.py"])
        files = resolver.resolve()

        assert len(files) == 1
        assert files[0].name == "file.py"

    def test_pattern_no_include_no_exclude(self, tmp_path: Path) -> None:
        """test pattern matching with no patterns."""
        (tmp_path / "file.txt").write_text("text")

        resolver = SourceResolver(root=tmp_path)
        files = resolver.resolve()

        # should find all files when no patterns specified
        assert len(files) == 1
        assert files[0].name == "file.txt"
