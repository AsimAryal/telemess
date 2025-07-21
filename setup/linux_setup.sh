#!/bin/bash
# author: asim@iovox.com
# version: 2025.02.07
# description:
#   This script provides a robust, one-step setup for a Python project.
#   It is safe to run on a brand new project or on an existing project
#   that has been cloned from a repository.
#
# What it does:
#   1. Installs 'uv' and 'ruff' if they are not present.
#   2. Creates a virtual environment in './.venv' if one doesn't exist.
#   3. Ensures a 'pyproject.toml' file and the corresponding package directory exist, creating defaults if needed.
#   4. Ensures standard configurations for 'ruff' and 'pre-commit' are present.
#   5. Syncs the virtual environment by resolving all dependencies from 'pyproject.toml'.
#   6. Installs Git hooks.
#

set -e

echo "Starting Python project setup for Linux/macOS"

# Configuration
# Set the desired Python version for the virtual environment.
PYTHON_VERSION="3.11"
PROJECT_NAME="src" # Use 'src' for the package directory name

# Install Core Tools
echo "Installing uv and ruff"
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -LsSf https://astral.sh/ruff/install.sh | sh

# Update PATH for the Current Session
export PATH="$HOME/.cargo/bin:$PATH"
echo "PATH updated for this session."

# Create Virtual Environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment (.venv) with Python $PYTHON_VERSION"
    uv venv -p "$PYTHON_VERSION" > /dev/null
fi

# Create project structure and pyproject.toml if they don't exist
if [ ! -f "pyproject.toml" ]; then
    echo "No pyproject.toml found. Creating a default project file and structure."

    # Create the package directory that hatchling needs
    mkdir -p "$PROJECT_NAME"
    # Create the __init__.py to make it a package
    touch "$PROJECT_NAME/__init__.py"

    cat <<EOF > pyproject.toml
[project]
name = "new_project"
version = "0.1.0"
description = "new_project_description"
authors = [{ name = "Your Name", email = "your@email.com" }]
dependencies = [
    "pre-commit>=3.0.0",
]
requires-python = ">=3.11"
readme = "README.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# Explicitly tell hatch where to find the code to prevent build errors
[tool.hatch.build.targets.wheel]
packages = ["$PROJECT_NAME"]
EOF
else
    echo "Existing pyproject.toml found."
fi

# Add Ruff Configuration to pyproject.toml if it doesn't exist
PYPROJECT_FILE="pyproject.toml"
if ! grep -q "\[tool.ruff\]" "$PYPROJECT_FILE"; then
    echo "Adding default ruff configuration to pyproject.toml"
    cat <<EOF >> "$PYPROJECT_FILE"

[tool.ruff]
# Exclude common directories from linting and formatting.
exclude = [
    ".bzr", ".direnv", ".eggs", ".git", ".hg", ".mypy_cache", ".nox",
    ".pants.d", ".ruff_cache", ".svn", ".tox", ".venv", "__pypackages__",
    "_build", "buck-out", "build", "dist", "node_modules", "venv",
]
line-length = 88
indent-width = 4
target-version = "py311"
[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I"]
EOF
fi

# Create Pre-commit Configuration if it doesn't exist
if [ ! -f ".pre-commit-config.yaml" ]; then
    echo "Creating .pre-commit-config.yaml"
    cat <<EOF > .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ["--maxkb=1024"]
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
EOF
fi

# Sync Environment: This is the key step for new and existing projects.
# It reads 'pyproject.toml', resolves all dependencies (including sub-dependencies),
# creates/updates uv.lock, and installs everything into the virtual environment.
echo "Syncing environment to install all dependencies..."
uv pip sync pyproject.toml > /dev/null

# Ensure we are in a Git repository
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "Not a Git repository. Initializing Git..."
    git init
    git add .
    git commit -m "Initial commit from setup script" || echo "Initial commit skipped (possibly nothing to commit)."
fi

# Install Git Hooks
echo "Installing git hooks"
uv run pre-commit install --install-hooks
uv run pre-commit install --hook-type pre-push

# Final Instructions
echo "Setup complete. Your environment is ready."
echo "To activate the virtual environment, run the following command in your terminal:"
echo "source .venv/bin/activate"
echo "Once activated, add new packages using 'uv add <package-name>'"
