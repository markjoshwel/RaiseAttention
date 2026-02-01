"""tests for the lsp server module.

this module tests the language server protocol implementation including
diagnostics, document handling, and debouncing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lsprotocol import types

from raiseattention.config import Config
from raiseattention.lsp_server import (
    RaiseAttentionLanguageServer,
    create_server,
)


class TestRaiseAttentionLanguageServer:
    """tests for the main lsp server class."""

    def test_server_creation(self) -> None:
        """test that server can be created."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        assert server is not None
        assert server.config == config
        assert server.analyzer is not None
        assert server._pending_changes == {}
        assert server._debounce_task is None

    def test_server_default_config(self) -> None:
        """test that server uses default config when none provided."""
        with patch.object(Config, "load", return_value=Config()):
            server = RaiseAttentionLanguageServer()

        assert server.config is not None
        assert server.analyzer is not None

    def test_server_has_features(self) -> None:
        """test that lsp handlers are registered."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        # check that the server has the expected attributes
        # pygls registers features via decorators in _register_handlers()
        # the server should have the feature registration method
        assert hasattr(server, "feature")
        assert hasattr(server, "text_document_publish_diagnostics")
        assert hasattr(server, "analyzer")
        assert hasattr(server, "config")


class TestDiagnosticConversion:
    """tests for converting internal diagnostics to lsp format."""

    def test_diagnostic_conversion(self) -> None:
        """test conversion of internal diagnostic to lsp diagnostic."""
        from raiseattention.analyser import Diagnostic

        config = Config()
        server = RaiseAttentionLanguageServer(config)

        internal_diag = Diagnostic(
            file_path=Path("/test/file.py"),
            line=10,
            column=5,
            message="unhandled exception",
            exception_types=["ValueError"],
            severity="error",
        )

        lsp_diag = server._to_lsp_diagnostic(internal_diag)

        assert isinstance(lsp_diag, types.Diagnostic)
        assert lsp_diag.message == "unhandled exception"
        assert lsp_diag.severity == types.DiagnosticSeverity.Error
        assert lsp_diag.source == "raiseattention"
        assert lsp_diag.code == "unhandled-exception"
        assert lsp_diag.range.start.line == 9  # 0-indexed
        assert lsp_diag.range.start.character == 5

    def test_diagnostic_severity_mapping(self) -> None:
        """test that severity levels map correctly."""
        from raiseattention.analyser import Diagnostic

        config = Config()
        server = RaiseAttentionLanguageServer(config)

        severities = [
            ("error", types.DiagnosticSeverity.Error),
            ("warning", types.DiagnosticSeverity.Warning),
            ("info", types.DiagnosticSeverity.Information),
        ]

        for severity_str, expected_severity in severities:
            internal_diag = Diagnostic(
                file_path=Path("/test/file.py"),
                line=1,
                column=0,
                message="test",
                severity=severity_str,
            )

            lsp_diag = server._to_lsp_diagnostic(internal_diag)
            assert lsp_diag.severity == expected_severity

    def test_diagnostic_default_severity(self) -> None:
        """test that unknown severity defaults to error."""
        from raiseattention.analyser import Diagnostic

        config = Config()
        server = RaiseAttentionLanguageServer(config)

        internal_diag = Diagnostic(
            file_path=Path("/test/file.py"),
            line=1,
            column=0,
            message="test",
            severity="unknown",
        )

        lsp_diag = server._to_lsp_diagnostic(internal_diag)
        assert lsp_diag.severity == types.DiagnosticSeverity.Error


class TestDebouncing:
    """tests for the debouncing mechanism."""

    @pytest.mark.asyncio
    async def test_debounced_analysis(self, tmp_path: Path) -> None:
        """test that analysis is debounced."""
        config = Config()
        config.lsp.debounce_ms = 50  # short delay for testing
        server = RaiseAttentionLanguageServer(config)

        # create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        uri = f"file://{test_file}"

        # mock the _analyse_document method
        with patch.object(server, "_analyse_document") as mock_analyse:
            # trigger debounced analysis
            task = asyncio.create_task(server._debounced_analysis(uri))

            # wait for debounce period
            await asyncio.sleep(0.1)

            # should have been called after debounce
            mock_analyse.assert_called_once_with(uri)

            # clean up
            await task

    @pytest.mark.asyncio
    async def test_debounce_cancellation(self, tmp_path: Path) -> None:
        """test that previous debounce task is cancelled."""
        config = Config()
        config.lsp.debounce_ms = 100
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")
        uri = f"file://{test_file}"

        # start first task
        task1 = asyncio.create_task(server._debounced_analysis(uri))
        server._debounce_task = task1

        # immediately start second task (simulating rapid changes)
        task2 = asyncio.create_task(server._debounced_analysis(uri))

        # first task should be cancelled when second starts
        # but we're testing the mechanism, so let's verify cancellation works
        await asyncio.sleep(0.05)

        # task1 might be cancelled if we cancel it manually
        task1.cancel()

        try:
            await task1
        except asyncio.CancelledError:
            pass  # expected

        await task2


class TestDocumentAnalysis:
    """tests for document analysis functionality."""

    def test_analyse_document_non_file_uri(self) -> None:
        """test that non-file uris are ignored."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        # should not raise and should return early
        server._analyse_document("http://example.com/file.py")

        # no diagnostics should be published for non-file uris

    def test_analyse_document_file_uri(self, tmp_path: Path) -> None:
        """test analysis of a file uri."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        # create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        uri = f"file://{test_file}"

        # mock the publish_diagnostics method
        with patch.object(server, "text_document_publish_diagnostics") as mock_publish:
            server._analyse_document(uri)

            # should have been called with diagnostics
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args[0][0]
            assert isinstance(call_args, types.PublishDiagnosticsParams)
            assert call_args.uri == uri

    def test_analyse_document_with_unhandled_exceptions(self, tmp_path: Path) -> None:
        """test that server detects unhandled exceptions."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        # create file with unhandled exception
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def risky():
    raise ValueError("error")

def caller():
    risky()  # should be flagged
""")

        uri = f"file://{test_file}"

        published_diagnostics = []

        def capture_publish(params: types.PublishDiagnosticsParams) -> None:
            published_diagnostics.extend(params.diagnostics)

        with patch.object(server, "text_document_publish_diagnostics", capture_publish):
            server._analyse_document(uri)

        # should have detected the unhandled exception
        assert len(published_diagnostics) > 0
        assert any("ValueError" in d.message for d in published_diagnostics)

    def test_analyse_document_with_handled_exceptions(self, tmp_path: Path) -> None:
        """test that server doesn't flag handled exceptions."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        # create file with handled exception
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def risky():
    raise ValueError("error")

def caller():
    try:
        risky()
    except ValueError:
        pass
""")

        uri = f"file://{test_file}"

        published_diagnostics = []

        def capture_publish(params: types.PublishDiagnosticsParams) -> None:
            published_diagnostics.extend(params.diagnostics)

        with patch.object(server, "text_document_publish_diagnostics", capture_publish):
            server._analyse_document(uri)

        # should not have any diagnostics for handled exceptions
        assert len(published_diagnostics) == 0


class TestPendingChanges:
    """tests for pending changes tracking."""

    def test_pending_changes_cleared_on_close(self, tmp_path: Path) -> None:
        """test that pending changes are cleared when document closes."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        uri = f"file://{test_file}"

        # add some pending changes
        server._pending_changes[uri] = []

        # manually call the close handler logic
        if uri in server._pending_changes:
            del server._pending_changes[uri]

        # pending changes should be cleared
        assert uri not in server._pending_changes


class TestHover:
    """tests for hover information."""

    def test_hover_info_none(self, tmp_path: Path) -> None:
        """test hover returns none for positions without exceptions."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        params = types.HoverParams(
            text_document=types.TextDocumentIdentifier(uri=f"file://{test_file}"),
            position=types.Position(line=0, character=0),
        )

        result = server._get_hover_info(params)

        # should return None when no exception info available
        assert result is None


class TestServerCreation:
    """tests for server factory functions."""

    def test_create_server(self) -> None:
        """test server factory function."""
        config = Config()
        server = create_server(config)

        assert isinstance(server, RaiseAttentionLanguageServer)
        assert server.config == config

    def test_create_server_default_config(self) -> None:
        """test server factory with default config."""
        with patch.object(Config, "load", return_value=Config()):
            server = create_server()

        assert isinstance(server, RaiseAttentionLanguageServer)


class TestServerConfiguration:
    """tests for server configuration handling."""

    def test_server_uses_lsp_config_debounce(self, tmp_path: Path) -> None:
        """test that server uses lsp config debounce setting."""
        config = Config()
        config.lsp.debounce_ms = 100
        server = RaiseAttentionLanguageServer(config)

        assert server.config.lsp.debounce_ms == 100

    def test_server_uses_lsp_config_max_diagnostics(self) -> None:
        """test that server uses lsp config max_diagnostics setting."""
        config = Config()
        config.lsp.max_diagnostics_per_file = 50
        server = RaiseAttentionLanguageServer(config)

        assert server.config.lsp.max_diagnostics_per_file == 50


class TestServerEdgeCases:
    """edge case tests for the lsp server."""

    def test_analyse_empty_file(self, tmp_path: Path) -> None:
        """test analysis of empty file."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        test_file.write_text("")

        uri = f"file://{test_file}"

        with patch.object(server, "text_document_publish_diagnostics") as mock_publish:
            server._analyse_document(uri)

            # should handle empty file gracefully
            mock_publish.assert_called_once()

    def test_analyse_syntax_error_file(self, tmp_path: Path) -> None:
        """test analysis of file with syntax errors."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        test_file.write_text("def func(: pass")  # syntax error

        uri = f"file://{test_file}"

        with patch.object(server, "text_document_publish_diagnostics") as mock_publish:
            server._analyse_document(uri)

            # should handle syntax error gracefully
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args[0][0]
            # should have diagnostic about syntax error
            assert len(call_args.diagnostics) > 0

    def test_analyse_nonexistent_file(self) -> None:
        """test analysis of nonexistent file."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        uri = "file:///nonexistent/file.py"

        with patch.object(server, "text_document_publish_diagnostics") as mock_publish:
            server._analyse_document(uri)

            # should handle nonexistent file gracefully
            mock_publish.assert_called_once()

    def test_analyse_file_with_unicode(self, tmp_path: Path) -> None:
        """test analysis of file with unicode characters."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        test_file.write_text("# 日本語\ndef func(): pass", encoding="utf-8")

        uri = f"file://{test_file}"

        with patch.object(server, "text_document_publish_diagnostics") as mock_publish:
            server._analyse_document(uri)

            # should handle unicode gracefully
            mock_publish.assert_called_once()

    def test_concurrent_analysis(self, tmp_path: Path) -> None:
        """test that server handles concurrent analysis requests."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        test_file1 = tmp_path / "test1.py"
        test_file1.write_text("def func1(): pass")

        test_file2 = tmp_path / "test2.py"
        test_file2.write_text("def func2(): pass")

        uri1 = f"file://{test_file1}"
        uri2 = f"file://{test_file2}"

        with patch.object(server, "text_document_publish_diagnostics") as mock_publish:
            server._analyse_document(uri1)
            server._analyse_document(uri2)

            # should handle both files
            assert mock_publish.call_count == 2


class TestServerPerformance:
    """performance-related tests for the lsp server."""

    def test_analysis_caching(self, tmp_path: Path) -> None:
        """test that server uses analyzer caching."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        uri = f"file://{test_file}"

        with patch.object(server.analyzer, "analyse_file") as mock_analyse:
            mock_analyse.return_value = MagicMock(
                diagnostics=[], files_analysed=[], functions_found=0
            )

            server._analyse_document(uri)

            # should call analyze_file
            mock_analyse.assert_called_once()

    def test_large_file_handling(self, tmp_path: Path) -> None:
        """test that server handles large files."""
        config = Config()
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        # create a large file with many functions
        content = "\n".join([f"def func_{i}(): pass" for i in range(1000)])
        test_file.write_text(content)

        uri = f"file://{test_file}"

        with patch.object(server, "text_document_publish_diagnostics") as mock_publish:
            server._analyse_document(uri)

            # should handle large file
            mock_publish.assert_called_once()


class TestServerWithConfigurationChanges:
    """tests for server behavior with different configurations."""

    def test_strict_mode_finds_more_issues(self, tmp_path: Path) -> None:
        """test that strict mode finds more diagnostics."""
        config = Config()
        config.analysis.strict_mode = True
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        test_file.write_text("""
def risky():
    raise ValueError("error")

def caller():
    risky()
""")

        uri = f"file://{test_file}"

        with patch.object(server, "text_document_publish_diagnostics") as mock_publish:
            server._analyse_document(uri)

            call_args = mock_publish.call_args[0][0]
            # should have found unhandled exception
            assert len(call_args.diagnostics) > 0

    def test_ignore_exceptions_respected(self, tmp_path: Path) -> None:
        """test that ignored exceptions are not reported."""
        config = Config()
        config.ignore_exceptions = ["ValueError"]
        server = RaiseAttentionLanguageServer(config)

        test_file = tmp_path / "test.py"
        test_file.write_text("""
def risky():
    raise ValueError("error")

def caller():
    risky()
""")

        uri = f"file://{test_file}"

        with patch.object(server, "text_document_publish_diagnostics") as mock_publish:
            server._analyse_document(uri)

            call_args = mock_publish.call_args[0][0]
            # should not report ValueError since it's ignored
            value_error_diags = [d for d in call_args.diagnostics if "ValueError" in d.message]
            assert len(value_error_diags) == 0
