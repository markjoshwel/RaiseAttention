"""
generate all stdlib pyras stubs for python 3.10-3.14.

parallelises module analysis within each python version for maximum throughput.
"""

from __future__ import annotations

import hashlib
import lzma
import os
import sys
import tarfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# generator identifier
GENERATOR = "standardstubber@0.1.0"


def get_cache_dir() -> Path:
    """get the cache directory for extracted tarballs."""
    cache_dir = Path.home().joinpath(".cache", "standardstubber")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_tarball_hash(tarball: Path) -> str:
    """get a short hash of a tarball for cache key."""
    stat = tarball.stat()
    key = f"{tarball.name}:{stat.st_size}:{stat.st_mtime}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def extract_tarball_cached(tarball: Path) -> Path:
    """extract tarball to cache directory if not already extracted."""
    cache_dir = get_cache_dir()
    cache_key = get_tarball_hash(tarball)
    extract_dir = cache_dir.joinpath(cache_key)

    if extract_dir.exists():
        for item in extract_dir.iterdir():
            if item.is_dir() and item.name.startswith("Python-"):
                print(f"  using cached extraction: {item.name}")
                return item

    print(f"  extracting: {tarball.name}")
    extract_dir.mkdir(parents=True, exist_ok=True)

    with lzma.open(tarball) as xz:
        with tarfile.open(fileobj=xz) as tar:
            tar.extractall(extract_dir, filter="data")

    for item in extract_dir.iterdir():
        if item.is_dir() and item.name.startswith("Python-"):
            return item

    raise RuntimeError(f"failed to find Python directory in {extract_dir}")


def analyse_single_module(
    args: tuple[Path, Path, str],
) -> tuple[str, list[tuple[str, frozenset[str], str, str]]]:
    """
    analyse a single c module file with propagation analysis.

    args: (c_file, cpython_root, module_name)
    returns: (module_name, [(qualname, raises, confidence, notes), ...])
    """
    c_file, cpython_root, module_name = args

    # import here to avoid issues with multiprocessing
    from standardstubber.analyser import CPythonAnalyser

    analyser = CPythonAnalyser(cpython_root=cpython_root)

    # use propagation-aware analysis
    graph = analyser.analyse_module_with_propagation(c_file, module_name)
    stubs = graph.get_exported_stubs()

    # convert to serialisable format
    results = [(stub.qualname, stub.raises, stub.confidence.value, stub.notes) for stub in stubs]
    return module_name, results


def generate_stubs_for_version(
    tarball: Path,
    version_spec: str,
    output: Path,
    max_workers: int = 16,
) -> tuple[str, int, str]:
    """generate stubs for a single python version with parallel module analysis."""
    from standardstubber.analyser import find_c_modules
    from standardstubber.models import StubMetadata
    from standardstubber.writer import write_stub_file_incremental

    version = tarball.stem.split("-")[1].rsplit(".", 1)[0]
    print(f"\n[{version}] starting...")

    try:
        cpython_root = extract_tarball_cached(tarball)
        c_modules = find_c_modules(cpython_root)
        print(
            f"[{version}] found {len(c_modules)} c modules, analysing with {max_workers} workers..."
        )

        # prepare tasks: (c_file, cpython_root, module_name)
        tasks = [(c_file, cpython_root, module_name) for c_file, module_name in c_modules]

        # collect raw stub tuples (qualname, raises, confidence, notes)
        all_raw_stubs: list[tuple[str, frozenset[str], str, str]] = []
        completed = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(analyse_single_module, task): task for task in tasks}

            for future in as_completed(futures):
                module_name, results = future.result()
                completed += 1

                # collect raw stubs directly (no FunctionStub objects needed)
                all_raw_stubs.extend(results)

                if results:
                    print(
                        f"  [{version}] ({completed}/{len(tasks)}) {module_name}: {len(results)} functions"
                    )

        # create stub file using incremental writer with deduplication
        metadata = StubMetadata(
            name="stdlib",
            version=version_spec,
            generator=GENERATOR,
            generated_at=datetime.now(timezone.utc),
        )

        num_written = write_stub_file_incremental(output, metadata, all_raw_stubs)

        print(f"[{version}] done: {num_written} unique stubs written to {output}")
        return version, num_written, ""

    except Exception as e:
        import traceback

        return version, 0, f"{e}\n{traceback.format_exc()}"


def main() -> int:
    """generate stubs for all python versions."""
    import argparse
    import logging

    parser = argparse.ArgumentParser(
        prog="generate_all",
        description="generate all stdlib pyras stubs for python 3.10-3.14",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=None,
        help="number of parallel jobs (default: cpu count)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="enable verbose logging",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="enable profiling (implies verbose)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable debug logging",
    )

    args = parser.parse_args()

    # configure logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    elif args.verbose or args.profile:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(message)s")

    resources_dir = Path(__file__).parent.joinpath("resources")
    output_dir = Path(__file__).parent.parent.joinpath("raiseattention", "stubs", "stdlib")
    output_dir.mkdir(parents=True, exist_ok=True)

    # dynamically find tarballs
    tarballs = sorted(resources_dir.glob("Python-*.tar.xz"), key=lambda p: p.name)
    if not tarballs:
        print(f"error: no python tarballs found in {resources_dir}")
        return 1

    print(f"found {len(tarballs)} python versions: {[t.name for t in tarballs]}")

    # detect number of cores
    num_cores = args.jobs if args.jobs is not None else (os.cpu_count() or 4)
    print(f"using {num_cores} cores for parallel module analysis")
    print()

    results: list[tuple[str, int, str]] = []

    for tarball in tarballs:
        # parse version: Python-3.12.12.tar.xz -> 3.12
        try:
            full_version = tarball.name.split("-")[1].replace(".tar.xz", "")
            major, minor, *_ = full_version.split(".")
            version_short = f"{major}.{minor}"
            next_minor = int(minor) + 1
            version_spec = f">={major}.{minor},<{major}.{next_minor}"
        except Exception:
            print(f"warning: ignoring malformed filename: {tarball.name}")
            continue

        output = output_dir.joinpath(f"python-{version_short}.pyras")

        result = generate_stubs_for_version(tarball, version_spec, output, max_workers=num_cores)
        results.append(result)

    # summary
    print()
    print("=" * 60)
    print("summary:")
    total = 0
    failed = 0
    for version, count, error in sorted(results):
        if error:
            print(f"  python {version}: FAILED - {error[:100]}")
            failed += 1
        else:
            print(f"  python {version}: {count} stubs")
            total += count
    print(f"total: {total} stubs across {len(results) - failed} versions")
    print("=" * 60)

    return 1 if failed else 0


if __name__ == "__main__":
    import multiprocessing

    # required for windows
    multiprocessing.freeze_support()
    sys.exit(main())
