"""
cli for standardstubber.

provides commands to generate .pyras stub files from cpython source.
"""

from __future__ import annotations

import argparse
import logging
import lzma
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from .analyser import CPythonAnalyser, find_c_modules
from .models import Confidence, FunctionStub, StubFile, StubMetadata

logger = logging.getLogger(__name__)

# generator identifier
GENERATOR: Final[str] = "standardstubber@0.1.0"


def main(args: list[str] | None = None) -> int:
    """
    main entry point for standardstubber cli.

    arguments:
        `args: list[str] | None`
            command-line arguments (uses sys.argv if none)

    returns: `int`
        exit code (0 for success)
    """
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

    parsed = parser.parse_args(args)

    # configure logging
    if parsed.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    elif parsed.verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(message)s")

    # handle tarball extraction
    cpython_path: Path = parsed.cpython
    temp_dir: Path | None = None

    if cpython_path.suffix in (".xz", ".gz", ".tar"):
        # extract tarball to temp directory
        import tempfile

        temp_dir = Path(tempfile.mkdtemp(prefix="standardstubber-"))
        extracted = extract_tarball(cpython_path, temp_dir)
        if extracted is None:
            print(f"error: failed to extract tarball: {parsed.cpython}", file=sys.stderr)
            return 1
        cpython_path = extracted

    try:
        return generate_stubs(
            cpython_root=cpython_path,
            version_spec=parsed.version,
            output_path=parsed.output,
        )
    finally:
        # cleanup temp directory
        if temp_dir is not None and temp_dir.exists():
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)


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


def generate_stubs(
    cpython_root: Path,
    version_spec: str,
    output_path: Path,
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

    returns: `int`
        exit code (0 for success)
    """
    if not cpython_root.exists():
        print(f"error: cpython root not found: {cpython_root}", file=sys.stderr)
        return 1

    if not (cpython_root / "Include").exists():
        print(f"error: invalid cpython source (no Include/): {cpython_root}", file=sys.stderr)
        return 1

    logger.info("analysing cpython source: %s", cpython_root)

    # find all c modules
    c_modules = find_c_modules(cpython_root)
    logger.info("found %d c modules", len(c_modules))

    if not c_modules:
        print("error: no c modules found", file=sys.stderr)
        return 1

    # analyse each module
    analyser = CPythonAnalyser(cpython_root=cpython_root)
    all_stubs: list[FunctionStub] = []

    total_modules = len(c_modules)
    for i, (c_file, module_name) in enumerate(c_modules, 1):
        stubs = analyser.analyse_module_file(c_file, module_name)
        all_stubs.extend(stubs)
        if stubs:
            logger.info("  [%d/%d] %s: %d functions", i, total_modules, module_name, len(stubs))
        elif logger.isEnabledFor(logging.DEBUG):
            logger.debug("  [%d/%d] %s: 0 functions", i, total_modules, module_name)

    logger.info("total functions analysed: %d", len(all_stubs))

    # create stub file
    metadata = StubMetadata(
        name="stdlib",
        version=version_spec,
        generator=GENERATOR,
        generated_at=datetime.now(timezone.utc),
    )

    stub_file = StubFile(metadata=metadata, stubs=all_stubs)

    # ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # write stub file
    stub_file.write(output_path)
    print(f"wrote {len(all_stubs)} stubs to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
