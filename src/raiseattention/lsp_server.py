"""
language server protocol implementation for raiseattention.

provides real-time exception analysis via lsp, including diagnostics,
hover information, and code actions.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, final

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from .analyser import Diagnostic, ExceptionAnalyser
from .config import Config

if TYPE_CHECKING:
    pass


@final
class RaiseAttentionLanguageServer(LanguageServer):
    """
    lsp server for raiseattention exception analysis.

    provides:
    - real-time diagnostics for unhandled exceptions
    - hover information showing exception signatures
    - code actions to add exception handlers

    attributes:
        `analyzer: ExceptionAnalyser`
            exception analysis engine
        `config: Config`
            configuration settings
        `_pending_changes: dict[str, list[types.TextDocumentContentChangeEvent]]`
            pending document changes waiting for debounce
        `_debounce_task: asyncio.Task[None] | None`
            current debounce timer task
    """

    config: Config
    analyzer: ExceptionAnalyser
    _pending_changes: dict[str, list[types.TextDocumentContentChangeEvent]]
    _debounce_task: asyncio.Task[None] | None

    def __init__(self, config: Config | None = None) -> None:
        """
        initialise the lsp server.

        arguments:
            `config: Config | None`
                configuration settings (default: auto-load from workspace)
        """
        super().__init__("raiseattention", "0.1.0")  # pyright: ignore[reportUnknownMemberType]

        self.config = config or Config.load()
        self.analyzer = ExceptionAnalyser(self.config)
        self._pending_changes = {}
        self._debounce_task = None

        # register handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register lsp method handlers."""

        @self.feature(types.TEXT_DOCUMENT_DID_OPEN)
        def on_open(params: types.DidOpenTextDocumentParams) -> None:
            """Handle document open."""
            self._analyse_document(params.text_document.uri)

        _ = on_open  # registered via decorator

        @self.feature(types.TEXT_DOCUMENT_DID_CHANGE)
        def on_change(params: types.DidChangeTextDocumentParams) -> None:
            """Handle document change with debouncing."""
            uri = params.text_document.uri

            # store changes
            if uri not in self._pending_changes:
                self._pending_changes[uri] = []
            self._pending_changes[uri].extend(params.content_changes)

            # reset debounce timer
            if self._debounce_task:
                self._debounce_task.cancel()

            self._debounce_task = asyncio.create_task(self._debounced_analysis(uri))

        _ = on_change  # registered via decorator

        @self.feature(types.TEXT_DOCUMENT_DID_SAVE)
        def on_save(params: types.DidSaveTextDocumentParams) -> None:
            """Handle document save."""
            self._analyse_document(params.text_document.uri)

        _ = on_save  # registered via decorator

        @self.feature(types.TEXT_DOCUMENT_DID_CLOSE)
        def on_close(params: types.DidCloseTextDocumentParams) -> None:
            """Handle document close."""
            uri = params.text_document.uri
            if uri in self._pending_changes:
                del self._pending_changes[uri]

        _ = on_close  # registered via decorator

        @self.feature(types.TEXT_DOCUMENT_HOVER)
        def on_hover(params: types.HoverParams) -> types.Hover | None:
            """Handle hover requests."""
            return self._get_hover_info(params)

        _ = on_hover  # registered via decorator

    async def _debounced_analysis(self, uri: str) -> None:
        """
        Perform debounced analysis after delay.

        arguments:
            `uri: str`
                document uri
        """
        # wait for debounce interval
        await asyncio.sleep(self.config.lsp.debounce_ms / 1000)

        # clear pending changes for this uri
        if uri in self._pending_changes:
            del self._pending_changes[uri]

        # perform analysis
        self._analyse_document(uri)

    def _analyse_document(self, uri: str) -> None:
        """
        analyse a document and publish diagnostics.

        arguments:
            `uri: str`
                document uri
        """
        # convert uri to file path
        if not uri.startswith("file://"):
            return

        file_path = uri[7:]  # remove 'file://' prefix

        # analyse
        result = self.analyzer.analyse_file(file_path)

        # convert to lsp diagnostics
        diagnostics = [self._to_lsp_diagnostic(d) for d in result.diagnostics]

        # publish
        self.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(
                uri=uri,
                diagnostics=diagnostics,
            )
        )

    def _to_lsp_diagnostic(self, diagnostic: Diagnostic) -> types.Diagnostic:
        """
        Convert internal diagnostic to lsp diagnostic.

        arguments:
            `diagnostic: Diagnostic`
                internal diagnostic

        returns: `types.Diagnostic`
            lsp diagnostic
        """
        severity_map = {
            "error": types.DiagnosticSeverity.Error,
            "warning": types.DiagnosticSeverity.Warning,
            "info": types.DiagnosticSeverity.Information,
        }

        return types.Diagnostic(
            range=types.Range(
                start=types.Position(
                    line=diagnostic.line - 1,  # lsp uses 0-indexed lines
                    character=diagnostic.column,
                ),
                end=types.Position(
                    line=diagnostic.line - 1,
                    character=diagnostic.column + 1,
                ),
            ),
            message=diagnostic.message,
            severity=severity_map.get(diagnostic.severity, types.DiagnosticSeverity.Error),
            source="raiseattention",
            code="unhandled-exception",
        )

    def _get_hover_info(self, params: types.HoverParams) -> types.Hover | None:
        """
        Get hover information for a position.

        arguments:
            `params: types.HoverParams`
                hover parameters

        returns: `types.Hover | None`
            hover information or none
        """
        # convert uri to file path
        uri = params.text_document.uri
        if not uri.startswith("file://"):
            return None

        file_path = uri[7:]

        # get analysis for this file
        result = self.analyzer.analyse_file(file_path)

        # find function at position
        line = params.position.line + 1  # convert to 1-indexed

        for diagnostic in result.diagnostics:
            if diagnostic.line == line:
                # create hover content
                content = f"**Unhandled Exception**: {', '.join(diagnostic.exception_types)}"

                return types.Hover(
                    contents=types.MarkupContent(
                        kind=types.MarkupKind.Markdown,
                        value=content,
                    ),
                )

        return None


def create_server(config: Config | None = None) -> RaiseAttentionLanguageServer:
    """
    create and configure the lsp server.

    arguments:
        `config: Config | None`
            configuration settings

    returns: `RaiseAttentionLanguageServer`
        configured lsp server
    """
    return RaiseAttentionLanguageServer(config)


def run_server_stdio(config: Config | None = None) -> None:
    """
    run the lsp server over stdio.

    arguments:
        `config: Config | None`
            configuration settings
    """
    server = create_server(config)
    server.start_io()


def run_server_tcp(host: str = "127.0.0.1", port: int = 2087, config: Config | None = None) -> None:
    """
    run the lsp server over tcp.

    arguments:
        `host: str`
            host address to bind
        `port: int`
            port to listen on
        `config: Config | None`
            configuration settings
    """
    server = create_server(config)
    server.start_tcp(host, port)
