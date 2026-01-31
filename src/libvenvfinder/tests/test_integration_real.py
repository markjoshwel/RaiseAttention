"""
real integration tests for libvenvfinder.

these tests actually invoke poetry, pipenv, pdm, uv, rye, hatch to create
real projects and verify venv detection works correctly.

requires the tools to be installed - tests will skip if not available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from libvenvfinder import find_venv, ToolType


def get_tool_path(tool_name: str) -> str | None:
    """get tool binary path from nix env or system path."""
    # check nix env vars first (set by flake.nix)
    nix_var = f"{tool_name.upper()}_BINARY"
    if nix_path := os.environ.get(nix_var):
        if os.path.exists(nix_path):
            return nix_path
    # fall back to system path
    return shutil.which(tool_name)


# pytest markers for tool availability
requires_poetry = pytest.mark.skipif(not get_tool_path("poetry"), reason="poetry not available")
requires_pipenv = pytest.mark.skipif(not get_tool_path("pipenv"), reason="pipenv not available")
requires_pdm = pytest.mark.skipif(not get_tool_path("pdm"), reason="pdm not available")
requires_uv = pytest.mark.skipif(not get_tool_path("uv"), reason="uv not available")
requires_rye = pytest.mark.skipif(not get_tool_path("rye"), reason="rye not available")
requires_hatch = pytest.mark.skipif(not get_tool_path("hatch"), reason="hatch not available")


class TestRealPoetryIntegration:
    """integration tests using real poetry."""

    @requires_poetry
    def test_poetry_init_and_venv_detection(self, tmp_path: Path) -> None:
        """test that poetry init + venv creation is detected."""
        poetry_bin = get_tool_path("poetry")
        assert poetry_bin is not None

        # change to temp directory
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # init poetry project non-interactively
            subprocess.run(
                [poetry_bin, "init", "--name", "test-project", "--no-interaction"],
                capture_output=True,
                text=True,
                check=False,
            )

            # create lock file (required for detection)
            subprocess.run(
                [poetry_bin, "lock"],
                capture_output=True,
                text=True,
                check=False,
            )

            # create venv
            subprocess.run(
                [poetry_bin, "env", "use", "python3"],
                capture_output=True,
                text=True,
                check=False,
            )

            # detect venv
            venv_info = find_venv(tmp_path)
            assert venv_info is not None
            assert venv_info.tool == ToolType.POETRY

        finally:
            os.chdir(original_cwd)


class TestRealPipenvIntegration:
    """integration tests using real pipenv."""

    @requires_pipenv
    def test_pipenv_install_and_detection(self, tmp_path: Path) -> None:
        """test that pipenv install creates detectable venv."""
        pipenv_bin = get_tool_path("pipenv")
        assert pipenv_bin is not None

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # create simple pipfile
            pipfile = tmp_path / "Pipfile"
            pipfile.write_text("""
[[source]]
url = "https://pypi.org/simple"
verify_ssl = true
name = "pypi"

[packages]

[dev-packages]

[requires]
python_version = "3.12"
""")

            # install (creates venv)
            env = os.environ.copy()
            env["PIPENV_YES"] = "1"  # auto-confirm
            subprocess.run(
                [pipenv_bin, "install"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=120,
            )

            # detect venv
            venv_info = find_venv(tmp_path)
            assert venv_info is not None
            assert venv_info.tool == ToolType.PIPENV

        finally:
            os.chdir(original_cwd)


class TestRealPdmIntegration:
    """integration tests using real pdm."""

    @requires_pdm
    def test_pdm_init_and_detection(self, tmp_path: Path) -> None:
        """test that pdm init + venv creation is detected."""
        pdm_bin = get_tool_path("pdm")
        assert pdm_bin is not None

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # init pdm project
            subprocess.run(
                [pdm_bin, "init", "--non-interactive", "--python", "python3"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            # create venv
            subprocess.run(
                [pdm_bin, "venv", "create"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            # create lock file (required for detection)
            subprocess.run(
                [pdm_bin, "lock"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            # detect venv
            venv_info = find_venv(tmp_path)
            assert venv_info is not None
            assert venv_info.tool == ToolType.PDM

        finally:
            os.chdir(original_cwd)


class TestRealUvIntegration:
    """integration tests using real uv."""

    @requires_uv
    def test_uv_init_and_detection(self, tmp_path: Path) -> None:
        """test that uv init + venv sync is detected."""
        uv_bin = get_tool_path("uv")
        assert uv_bin is not None

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # init uv project
            subprocess.run(
                [uv_bin, "init", "--name", "test-project", "--python", "3.12"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            # sync (creates venv)
            subprocess.run(
                [uv_bin, "sync"],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )

            # detect venv
            venv_info = find_venv(tmp_path)
            assert venv_info is not None
            assert venv_info.tool == ToolType.UV

        finally:
            os.chdir(original_cwd)


class TestRealRyeIntegration:
    """integration tests using real rye."""

    @requires_rye
    def test_rye_init_and_detection(self, tmp_path: Path) -> None:
        """test that rye init creates detectable venv."""
        rye_bin = get_tool_path("rye")
        assert rye_bin is not None

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # init rye project
            subprocess.run(
                [rye_bin, "init", "--name", "test-project"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            # create lock file (ensures correct tool detection)
            subprocess.run(
                [rye_bin, "lock"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            # sync to create venv
            subprocess.run(
                [rye_bin, "sync"],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )

            # Debug: check what files exist
            print(f"=== Debug: Files in {tmp_path} ===")
            for f in tmp_path.iterdir():
                print(f"  {f.name}")
            print(f"  rye.lock exists: {tmp_path.joinpath('rye.lock').exists()}")
            print(f"  .python-version exists: {tmp_path.joinpath('.python-version').exists()}")
            print(f"  .venv exists: {tmp_path.joinpath('.venv').exists()}")
            if tmp_path.joinpath(".python-version").exists():
                print(
                    f"  .python-version content: {tmp_path.joinpath('.python-version').read_text().strip()}"
                )

            # detect venv
            venv_info = find_venv(tmp_path)
            print(f"=== Debug: venv_info = {venv_info} ===")
            assert venv_info is not None
            assert venv_info.tool == ToolType.RYE

        finally:
            os.chdir(original_cwd)


class TestRealHatchIntegration:
    """integration tests using real hatch."""

    @requires_hatch
    def test_hatch_new_and_detection(self, tmp_path: Path) -> None:
        """test that hatch new creates detectable project."""
        hatch_bin = get_tool_path("hatch")
        assert hatch_bin is not None

        original_cwd = os.getcwd()
        project_dir = tmp_path / "test-project"

        try:
            # create new project
            subprocess.run(
                [hatch_bin, "new", "test-project", str(project_dir)],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            if project_dir.exists():
                os.chdir(project_dir)

                # create venv
                subprocess.run(
                    [hatch_bin, "env", "create"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=60,
                )

                # detect venv
                venv_info = find_venv(project_dir)
                assert venv_info is not None
                assert venv_info.tool == ToolType.HATCH

        finally:
            os.chdir(original_cwd)
