{
  description = "Graphēon - Python 3.12 + Node.js development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

        # Python 3.12 - stable, well-supported by all packages
        python = pkgs.python312;
        pythonPackages = python.pkgs;

      in {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            # Python 3.12
            python
            pythonPackages.pip
            pythonPackages.virtualenv

            # Node.js for React frontend
            pkgs.nodejs_22
            pkgs.nodePackages.npm

            # Development tools
            pkgs.sqlite
            pkgs.jq
            pkgs.curl
            pkgs.git
            pkgs.gh

            # Optional: useful for network tools testing
            pkgs.nmap
          ];

          shellHook = ''
            echo "🌐 Network Aggregator Development Environment"
            echo "Python: $(python --version)"
            echo "Node: $(node --version)"
            echo "SQLite: $(sqlite3 --version | cut -d' ' -f1)"
            echo ""

            # Create and activate Python virtual environment
            if [ ! -d ".venv" ]; then
              echo "Creating Python virtual environment..."
              python -m venv .venv
            fi
            source .venv/bin/activate

            # Install Python dependencies if requirements files exist
            if [ -f "backend/requirements.txt" ]; then
              pip install -q -r backend/requirements.txt
            fi
            if [ -f "backend/requirements-dev.txt" ]; then
              pip install -q -r backend/requirements-dev.txt
            fi

            # Install Node dependencies if package.json exists
            if [ -f "frontend/package.json" ] && [ ! -d "frontend/node_modules" ]; then
              echo "Installing frontend dependencies..."
              (cd frontend && npm install)
            fi

            echo ""
            echo "Ready! Run 'cd backend && uvicorn main:app --reload' for API"
            echo "       Run 'cd frontend && npm run dev' for UI"
          '';

          # Environment variables
          DATABASE_URL = "sqlite:///./data/network.db";
          PYTHONDONTWRITEBYTECODE = "1";
        };
      }
    );
}
