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
    cache_dir = Path.home() / ".cache" / "standardstubber"
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
    extract_dir = cache_dir / cache_key

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
) -> tuple[str, list[tuple[str, frozenset[str], str]]]:
    """
    analyse a single c module file.

    args: (c_file, cpython_root, module_name)
    returns: (module_name, [(qualname, raises, confidence), ...])
    """
    c_file, cpython_root, module_name = args

    # import here to avoid issues with multiprocessing
    from standardstubber.analyser import CPythonAnalyser

    analyser = CPythonAnalyser(cpython_root=cpython_root)
    stubs = analyser.analyse_module_file(c_file, module_name)

    # convert to serialisable format
    results = [(stub.qualname, stub.raises, stub.confidence.value) for stub in stubs]
    return module_name, results


def generate_stubs_for_version(
    tarball: Path,
    version_spec: str,
    output: Path,
    max_workers: int = 16,
) -> tuple[str, int, str]:
    """generate stubs for a single python version with parallel module analysis."""
    from standardstubber.analyser import find_c_modules
    from standardstubber.models import Confidence, FunctionStub, StubFile, StubMetadata

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

        all_stubs: list[FunctionStub] = []
        completed = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(analyse_single_module, task): task for task in tasks}

            for future in as_completed(futures):
                module_name, results = future.result()
                completed += 1

                for qualname, raises, confidence_str in results:
                    stub = FunctionStub(
                        qualname=qualname,
                        raises=raises,
                        confidence=Confidence(confidence_str),
                    )
                    all_stubs.append(stub)

                if results:
                    print(
                        f"  [{version}] ({completed}/{len(tasks)}) {module_name}: {len(results)} functions"
                    )

        # create stub file
        metadata = StubMetadata(
            name="stdlib",
            version=version_spec,
            generator=GENERATOR,
            generated_at=datetime.now(timezone.utc),
        )

        stub_file = StubFile(metadata=metadata, stubs=all_stubs)
        output.parent.mkdir(parents=True, exist_ok=True)
        stub_file.write(output)

        print(f"[{version}] done: {len(all_stubs)} stubs written to {output}")
        return version, len(all_stubs), ""

    except Exception as e:
        import traceback

        return version, 0, f"{e}\n{traceback.format_exc()}"


def main() -> int:
    """generate stubs for all python versions."""
    versions = [
        ("Python-3.10.19", ">=3.10,<3.11"),
        ("Python-3.11.14", ">=3.11,<3.12"),
        ("Python-3.12.12", ">=3.12,<3.13"),
        ("Python-3.13.11", ">=3.13,<3.14"),
        ("Python-3.14.2", ">=3.14,<3.15"),
    ]

    resources_dir = Path("src/standardstubber/resources")
    output_dir = Path("src/raiseattention/stubs/stdlib")
    output_dir.mkdir(parents=True, exist_ok=True)

    # detect number of cores
    num_cores = os.cpu_count() or 4
    print(f"using {num_cores} cores for parallel module analysis")
    print()

    results: list[tuple[str, int, str]] = []

    for tarball_name, version_spec in versions:
        tarball = resources_dir / f"{tarball_name}.tar.xz"
        if not tarball.exists():
            print(f"warning: tarball not found: {tarball}")
            continue

        version = tarball_name.split("-")[1].rsplit(".", 1)[0]
        output = output_dir / f"python-{version}.pyras"

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
    sys.exit(main())
