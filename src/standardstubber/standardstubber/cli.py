"""
cli for standardstubber.

provides commands to generate .pyras stub files from cpython source.
"""

from __future__ import annotations

import argparse
import logging
import lzma
import shutil
import signal
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Generator

from .analyser import CPythonAnalyser, find_c_modules
from .models import StubMetadata
from .writer import write_stub_file_incremental

logger = logging.getLogger(__name__)

# generator identifier
GENERATOR: Final[str] = "standardstubber@0.1.0"

# global temp dir tracker for signal handler cleanup
_temp_dirs: list[Path] = []


def _cleanup_temp_dirs(signum: int | None = None, frame: object | None = None) -> None:
    """clean up all tracked temp directories, even on interrupt."""
    for temp_dir in _temp_dirs:
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug("cleaned up temp dir: %s", temp_dir)
            except Exception:
                pass
    if signum is not None:
        # re-raise the signal after cleanup
        sys.exit(128 + signum)


@contextmanager
def managed_temp_dir(prefix: str = "standardstubber-") -> Generator[Path, None, None]:
    """
    create a temp directory that will be cleaned up even on keyboardinterrupt.

    arguments:
        `prefix: str`
            prefix for the temp directory name

    yields: `Path`
        path to the temp directory
    """
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    _temp_dirs.append(temp_dir)
    try:
        yield temp_dir
    finally:
        if temp_dir in _temp_dirs:
            _temp_dirs.remove(temp_dir)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def main(args: list[str] | None = None) -> int:
    """
    main entry point for standardstubber cli.

    arguments:
        `args: list[str] | None`
            command-line arguments (uses sys.argv if none)

    returns: `int`
        exit code (0 for success)
    """
    # set up signal handler for graceful cleanup on interrupt
    signal.signal(signal.SIGINT, _cleanup_temp_dirs)
    signal.signal(signal.SIGTERM, _cleanup_temp_dirs)

    parser = argparse.ArgumentParser(
        prog="standardstubber",
        description="generate .pyras exception stubs from cpython source",
    )
    parser.add_argument(
        "--cpython",
        type=Path,
        required=True,
        help="path to cpython source tree or .tar.xz archive",
    )
    parser.add_argument(
        "--version",
        type=str,
        required=True,
        help="pep 440 version specifier (e.g., '>=3.12,<3.13')",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="output .pyras file path",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="enable verbose logging",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable debug logging",
    )
    parser.add_argument(
        "--no-propagation",
        action="store_true",
        help="disable call graph propagation analysis (faster but less accurate)",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=None,
        help="number of parallel jobs (default: cpu count)",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="output timing breakdown per phase (deprecated, use -v)",
    )

    parsed = parser.parse_args(args)

    # configure logging
    if parsed.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    elif parsed.verbose or parsed.profile:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(message)s")

    # handle tarball extraction
    cpython_path: Path = parsed.cpython

    if cpython_path.suffix in (".xz", ".gz", ".tar"):
        # extract tarball to temp directory with automatic cleanup
        with managed_temp_dir(prefix="standardstubber-") as temp_dir:
            extracted = extract_tarball(cpython_path, temp_dir)
            if extracted is None:
                print(f"error: failed to extract tarball: {parsed.cpython}", file=sys.stderr)
                return 1
            cpython_path = extracted

            return generate_stubs(
                cpython_root=cpython_path,
                version_spec=parsed.version,
                output_path=parsed.output,
                use_propagation=not parsed.no_propagation,
                jobs=parsed.jobs,
            )
    else:
        # direct path to source tree
        return generate_stubs(
            cpython_root=cpython_path,
            version_spec=parsed.version,
            output_path=parsed.output,
            use_propagation=not parsed.no_propagation,
            jobs=parsed.jobs,
        )


def extract_tarball(tarball_path: Path, dest_dir: Path) -> Path | None:
    """
    extract a cpython source tarball.

    arguments:
        `tarball_path: Path`
            path to .tar.xz or .tar.gz archive
        `dest_dir: Path`
            directory to extract to

    returns: `Path | None`
        path to extracted cpython root, or none on failure
    """
    logger.info("extracting: %s", tarball_path)

    try:
        # handle .tar.xz files
        if tarball_path.name.endswith(".tar.xz"):
            with lzma.open(tarball_path) as xz:
                with tarfile.open(fileobj=xz) as tar:
                    tar.extractall(dest_dir, filter="data")
        else:
            with tarfile.open(tarball_path) as tar:
                tar.extractall(dest_dir, filter="data")

        # find the extracted directory (usually Python-X.Y.Z)
        for item in dest_dir.iterdir():
            if item.is_dir() and item.name.startswith("Python-"):
                return item

        # fallback: return dest_dir if it has Include/
        if (dest_dir / "Include").exists():
            return dest_dir

        return None

    except (OSError, tarfile.TarError, lzma.LZMAError) as e:
        logger.error("failed to extract tarball: %s", e)
        return None


def _analyse_worker(
    c_file: Path,
    module_name: str,
    cpython_root: Path,
    use_propagation: bool,
) -> tuple[str, list[tuple[str, frozenset[str], str, str]], float]:
    """
    worker function for parallel analysis.

    returns (module_name, raw_stubs, elapsed_time) where raw_stubs is a list of
    (qualname, raises, confidence, notes) tuples for incremental writing.
    """
    import time

    # re-instantiate analyser per worker to ensure thread safety with libclang
    analyser = CPythonAnalyser(cpython_root=cpython_root)
    start_time = time.perf_counter()

    try:
        if use_propagation:
            graph = analyser.analyse_module_with_propagation(c_file, module_name)
            stubs = graph.get_exported_stubs()
        else:
            stubs = analyser.analyse_module_file(c_file, module_name)

        # convert to raw tuples for serialisation and incremental writing
        raw_stubs = [
            (stub.qualname, stub.raises, stub.confidence.value, stub.notes) for stub in stubs
        ]
    except Exception:
        # ensure workers don't crash main process
        return module_name, [], 0.0

    elapsed = time.perf_counter() - start_time
    return module_name, raw_stubs, elapsed


def generate_stubs(
    cpython_root: Path,
    version_spec: str,
    output_path: Path,
    use_propagation: bool = True,
    jobs: int | None = None,
) -> int:
    """
    generate .pyras stubs from cpython source.

    arguments:
        `cpython_root: Path`
            path to cpython source tree
        `version_spec: str`
            pep 440 version specifier
        `output_path: Path`
            output .pyras file path
        `use_propagation: bool`
            whether to use call graph propagation analysis (default true)
        `jobs: int | None`
            number of parallel jobs (default: cpu count)

    returns: `int`
        exit code (0 for success)
    """
    import time
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from multiprocessing import cpu_count

    if not cpython_root.exists():
        print(f"error: cpython root not found: {cpython_root}", file=sys.stderr)
        return 1

    if not (cpython_root / "Include").exists():
        print(f"error: invalid cpython source (no Include/): {cpython_root}", file=sys.stderr)
        return 1

    mode = "with propagation" if use_propagation else "local only"
    num_jobs = jobs if jobs is not None else (cpu_count() or 1)

    logger.info("analysing cpython source (%s): %s", mode, cpython_root)
    logger.info("parallelism: %d workers", num_jobs)

    # find all c modules
    c_modules = find_c_modules(cpython_root)
    logger.info("found %d c modules", len(c_modules))

    if not c_modules:
        print("error: no c modules found", file=sys.stderr)
        return 1

    # collect raw stub data as (qualname, raises, confidence, notes) tuples
    all_raw_stubs: list[tuple[str, frozenset[str], str, str]] = []
    total_modules = len(c_modules)
    total_time = 0.0
    start_global = time.perf_counter()

    with ProcessPoolExecutor(max_workers=num_jobs) as executor:
        futures = {
            executor.submit(_analyse_worker, c_file, module_name, cpython_root, use_propagation): (
                i,
                module_name,
            )
            for i, (c_file, module_name) in enumerate(c_modules, 1)
        }

        for future in as_completed(futures):
            i, module_name = futures[future]
            try:
                _, raw_stubs, elapsed = future.result()
                total_time += elapsed
                all_raw_stubs.extend(raw_stubs)

                if raw_stubs:
                    logger.info(
                        "  [%d/%d] %s: %d functions (%.2fs)",
                        i,
                        total_modules,
                        module_name,
                        len(raw_stubs),
                        elapsed,
                    )
                elif logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "  [%d/%d] %s: 0 functions (%.2fs)", i, total_modules, module_name, elapsed
                    )
            except Exception as e:
                logger.error("failed to analyse %s: %s", module_name, e)

    global_elapsed = time.perf_counter() - start_global
    logger.info(
        "total functions analysed: %d (%.1fs total time, %.1fs wall time)",
        len(all_raw_stubs),
        total_time,
        global_elapsed,
    )

    # create stub file with incremental writer
    metadata = StubMetadata(
        name="stdlib",
        version=version_spec,
        generator=GENERATOR,
        generated_at=datetime.now(timezone.utc),
    )

    # write stub file using incremental approach (deduplicates and writes directly)
    num_written = write_stub_file_incremental(output_path, metadata, all_raw_stubs)
    print(f"wrote {num_written} unique stubs to: {output_path} ({global_elapsed:.1f}s)")

    return 0


if __name__ == "__main__":
    import multiprocessing

    # required for windows
    multiprocessing.freeze_support()
    sys.exit(main())
