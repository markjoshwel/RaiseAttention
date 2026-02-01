{
  description = "raiseattention - static exception flow analyser for python";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs = {
        pyproject-nix.follows = "pyproject-nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs = {
        pyproject-nix.follows = "pyproject-nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
  };

  outputs = { self, nixpkgs, pyproject-nix, pyproject-build-systems, uv2nix }:
    let
      inherit (nixpkgs) lib;
      systems = lib.systems.flakeExposed;
      forAllSystems = lib.genAttrs systems;
      
      # Load workspace from uv.lock
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

    in {
      packages = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python312;
          
          # Base package set from pyproject.nix
          baseSet = pkgs.callPackage pyproject-nix.build.packages { inherit python; };
          
          # Workspace overlay from uv.lock
          workspaceOverlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
          
          # Combine overlays: build-systems first, then workspace
          # Order matters! Build systems must be available for workspace packages
          pythonSet = baseSet.overrideScope (lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            workspaceOverlay
          ]);
          
        in {
          libsoulsearching = pythonSet.libsoulsearching;
          raiseattention = pythonSet.raiseattention;
          default = pythonSet.raiseattention;
        });

      devShells = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python312;
          
          baseSet = pkgs.callPackage pyproject-nix.build.packages { inherit python; };
          workspaceOverlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
          
          pythonSet = baseSet.overrideScope (lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            workspaceOverlay
          ]);
          
          venv = pythonSet.mkVirtualEnv "raiseattention-dev-env" workspace.deps.all;
          
        in {
          default = pkgs.mkShell {
            name = "raiseattention-dev";
            packages = [ venv pkgs.uv pkgs.ruff pkgs.mypy pkgs.basedpyright ];
            env = {
              UV_PYTHON_DOWNLOADS = "never";
              UV_PYTHON = "${venv}/bin/python";
            };
            shellHook = ''
              echo "raiseattention dev shell (pure uv2nix)"
              echo "python: $(python --version)"
              echo ""
              echo "run all tests:"
              echo "  uv run pytest tests -v"
              echo "  uv run pytest src/libsoulsearching/tests -v"
            '';
          };

          integration = pkgs.mkShell {
            name = "raiseattention-integration";
            packages = [ 
              venv pkgs.uv pkgs.ruff pkgs.mypy pkgs.basedpyright
              pkgs.poetry pkgs.pipenv pkgs.pdm pkgs.rye pkgs.hatch pkgs.pyenv
              pkgs.patchelf pkgs.glibc
            ];
            env = {
              UV_PYTHON_DOWNLOADS = "never";
              UV_PYTHON = "${venv}/bin/python";
              POETRY_BINARY = "${pkgs.poetry}/bin/poetry";
              PIPENV_BINARY = "${pkgs.pipenv}/bin/pipenv";
              PDM_BINARY = "${pkgs.pdm}/bin/pdm";
              UV_BINARY = "${pkgs.uv}/bin/uv";
              RYE_BINARY = "${pkgs.rye}/bin/rye";
              HATCH_BINARY = "${pkgs.hatch}/bin/hatch";
              PYENV_BINARY = "${pkgs.pyenv}/bin/pyenv";
            };
            shellHook = ''
              echo "raiseattention integration shell"
              echo ""
              echo "run unit tests:"
              echo "  uv run pytest src/libsoulsearching/tests/test_core.py src/libsoulsearching/tests/test_cli.py -v"
              echo ""
              echo "run real integration tests (creates actual projects):"
              echo "  uv run pytest src/libsoulsearching/tests/test_integration_real.py -v"
              echo ""
              
              # on NixOS, patch Rye's bundled binaries to work with NixOS's dynamic linker
              # Rye downloads dynamically-linked binaries that expect FHS paths like /lib64/ld-linux-x86-64.so.2
              if [ -f /etc/NIXOS ]; then
                echo "NixOS detected - patching Rye binaries..."
                
                # Function to patch a single binary
                patchRyeBin() {
                  if [ -f "$1" ]; then
                    # check if already patched (contains nix/store in interpreter path)
                    if ! patchelf --print-interpreter "$1" 2>/dev/null | grep -q "nix/store"; then
                      echo "  patching: $1"
                      patchelf --set-interpreter "${pkgs.glibc}/lib/ld-linux-x86-64.so.2" "$1" || true
                    fi
                  fi
                }
                
                # patch Rye's bundled uv binaries using find
                if [ -d "$HOME/.rye/uv" ]; then
                  find "$HOME/.rye/uv" -name "uv" -type f 2>/dev/null | while read -r uv; do
                    patchRyeBin "$uv"
                  done
                fi
                
                # patch Rye's bundled Python interpreters
                if [ -d "$HOME/.rye/py" ]; then
                  find "$HOME/.rye/py" -name "python3" -type f 2>/dev/null | while read -r py; do
                    patchRyeBin "$py"
                  done
                fi
                
                echo "Rye binaries patched (if any were found)"
              fi
            '';
          };
        });

      checks = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python312;
          
          baseSet = pkgs.callPackage pyproject-nix.build.packages { inherit python; };
          workspaceOverlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
          
          pythonSet = baseSet.overrideScope (lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            workspaceOverlay
          ]);
          
          venv = pythonSet.mkVirtualEnv "raiseattention-check-env" workspace.deps.all;
          
        in {
          # unit tests only - integration tests require external tools that don't
          # work well in the sandboxed nix build environment (different behavior)
          unit-tests = pkgs.runCommand "unit-tests" { nativeBuildInputs = [ venv ]; } ''
            export HOME=$(mktemp -d)
            export XDG_CACHE_HOME=$HOME/.cache
            cp -r ${./.} $HOME/project
            cd $HOME/project
            ${venv}/bin/python -m pytest tests -v --tb=short
            ${venv}/bin/python -m pytest src/libsoulsearching/tests/test_core.py src/libsoulsearching/tests/test_cli.py src/libsoulsearching/tests/test_detectors_edge_cases.py -v --tb=short
            ${venv}/bin/python -m pytest src/libsightseeing/tests -v --tb=short
            touch $out
          '';
          });

      apps = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python312;

          baseSet = pkgs.callPackage pyproject-nix.build.packages { inherit python; };
          workspaceOverlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

          pythonSet = baseSet.overrideScope (lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            workspaceOverlay
          ]);

          venv = pythonSet.mkVirtualEnv "raiseattention-app-env" workspace.deps.all;

           unit-tests-script = pkgs.writeShellScriptBin "unit-tests" ''
              export HOME=$(mktemp -d)
              export XDG_CACHE_HOME=$HOME/.cache
              cp -r ${./.} $HOME/project
              cd $HOME/project
              ${venv}/bin/python -m pytest tests -v --tb=short
              ${venv}/bin/python -m pytest src/libsoulsearching/tests/test_core.py src/libsoulsearching/tests/test_cli.py src/libsoulsearching/tests/test_detectors_edge_cases.py -v --tb=short
              ${venv}/bin/python -m pytest src/libsightseeing/tests -v --tb=short
            '';

           lint-script = pkgs.writeShellScriptBin "lint" ''
             export HOME=$(mktemp -d)
             cp -r ${./.} $HOME/project
             cd $HOME/project
             echo "running ruff check..."
             ${venv}/bin/python -m ruff check src tests
             echo "running ruff format check..."
             ${venv}/bin/python -m ruff format --check src tests
             echo "running mypy..."
             ${venv}/bin/python -m mypy src/libsoulsearching
             echo "lint complete"
           '';

           integration-tests-script = pkgs.writeShellScriptBin "integration-tests" ''
            export HOME=$(mktemp -d)

            # on NixOS, patch Rye's bundled binaries before running tests
            if [ -f /etc/NIXOS ]; then
              patchRyeBin() {
                if [ -f "$1" ]; then
                  if ! ${pkgs.patchelf}/bin/patchelf --print-interpreter "$1" 2>/dev/null | grep -q "nix/store"; then
                    ${pkgs.patchelf}/bin/patchelf --set-interpreter "${pkgs.glibc}/lib/ld-linux-x86-64.so.2" "$1" || true
                  fi
                fi
              }

              if [ -d "$HOME/.rye/uv" ]; then
                find "$HOME/.rye/uv" -name "uv" -type f 2>/dev/null | while read -r uv; do
                  patchRyeBin "$uv"
                done
              fi

              if [ -d "$HOME/.rye/py" ]; then
                find "$HOME/.rye/py" -name "python3" -type f 2>/dev/null | while read -r py; do
                  patchRyeBin "$py"
                done
              fi
            fi

            cp -r ${./.} $HOME/project
            cd $HOME/project
            ${venv}/bin/python -m pytest src/libsoulsearching/tests/test_integration_real.py -v --tb=short
          '';

        in {
          unit-tests = {
            type = "app";
            program = "${unit-tests-script}/bin/unit-tests";
          };
          integration-tests = {
            type = "app";
            program = "${integration-tests-script}/bin/integration-tests";
          };
          lint = {
            type = "app";
            program = "${lint-script}/bin/lint";
          };
        });
    };
}
