# author: asim@iovox.com
# version: 2025.07.21
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
#   6. Installs Git hooks using pre-commit.
#

# Stop the script if any command fails
$ErrorActionPreference = "Stop"

Write-Host "Starting Python project setup for Windows"

#Configuration
# Set the desired Python version for the virtual environment.
$pythonVersion = "3.11"
# Set the name of your package. This will be used for the directory inside 'src'.
$packageName = "new_project"


# Install Core Tools
Write-Host "Installing uv and ruff"
try {
    irm https://astral.sh/uv/install.ps1 | iex
    irm https://astral.sh/ruff/install.ps1 | iex
} catch {
    Write-Host "Error installing core tools. Please check your internet connection and try again."
    exit 1
}


# Update PATH for the Current Session
$userProfile = [Environment]::GetFolderPath("UserProfile")
$localBinPath = Join-Path $userProfile ".local\bin"
if (-not ($env:Path -like "*$localBinPath*")) {
    $env:Path = "$localBinPath;$env:Path"
    Write-Host "PATH updated for this session."
}

# Create Virtual Environment if it doesn't exist
if (-not (Test-Path ".venv" -PathType Container)) {
    Write-Host "Creating virtual environment (.venv) with Python $pythonVersion"
    uv venv -p $pythonVersion | Out-Null
}

# Create project structure and pyproject.toml if they don't exist
if (-not (Test-Path "pyproject.toml" -PathType Leaf)) {
    Write-Host "No pyproject.toml found. Creating a default project file and structure."

    # Create the standard 'src' layout directory for the package
    New-Item -ItemType Directory -Path "src\$packageName" -Force | Out-Null
    # Create the __init__.py to make it a package
    New-Item -ItemType File -Path "src\$packageName\__init__.py" | Out-Null

    # Create a pyproject.toml: uses `uv build`
@"
[project]
name = "$packageName"
version = "0.1.0"
description = "A new project."
authors = [{ name = "Your Name", email = "your@email.com" }]
dependencies = [
    "pre-commit>=3.0.0",
]
requires-python = ">=$pythonVersion"
readme = "README.md"


# 'uv' managed build as default.

"@ | Out-File -Encoding UTF8 "pyproject.toml"
} else {
    Write-Host "Existing pyproject.toml found."
}

# Add Ruff Configuration to pyproject.toml if it doesn't exist
$pyprojectPath = "pyproject.toml"
$ruffConfig = @"

[tool.ruff]
# Exclude common directories from linting and formatting.
exclude = [
    ".bzr", ".direnv", ".eggs", ".git", ".hg", ".mypy_cache", ".nox",
    ".pants.d", ".ruff_cache", ".svn", ".tox", ".venv", "__pypackages__",
    "_build", "buck-out", "build", "dist", "node_modules", "venv",
]
line-length = 88
indent-width = 4
target-version = "py$pythonVersion"
[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I"]
"@
$pyprojectContent = Get-Content $pyprojectPath -Raw
if (-not ($pyprojectContent -match '\[tool\.ruff\]')) {
    Write-Host "Adding default ruff configuration to pyproject.toml"
    Add-Content -Path $pyprojectPath -Value $ruffConfig
}


# Create Pre-commit Configuration if it doesn't exist
if (-not (Test-Path ".pre-commit-config.yaml" -PathType Leaf)) {
    Write-Host "Creating .pre-commit-config.yaml"
@"
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
"@ | Out-File -Encoding UTF8 ".pre-commit-config.yaml"
}

# Sync Environment: This is the key step for new and existing projects.
# It reads 'pyproject.toml', resolves all dependencies (including sub-dependencies),
# and installs everything into the virtual environment.
Write-Host "Syncing environment to install all dependencies..."
uv pip sync pyproject.toml | Out-Null

# Ensure we are in a Git repository before installing hooks
git rev-parse --is-inside-work-tree | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not a Git repository. Initializing Git..."
    git init
    git add .
    # Use a try/catch to handle cases where there's nothing to commit
    try {
        git commit -m "Initial commit from setup script"
    } catch {
        Write-Host "Initial commit skipped (possibly nothing to commit)."
    }
}

# Install Git Hooks using uv run to execute in the venv
Write-Host "Installing git hooks..."
uv run pre-commit install --install-hooks
uv run pre-commit install --hook-type pre-push

# Final Instructions
Write-Host ""
Write-Host "Setup complete. Your environment is ready."
Write-Host "To activate the virtual environment, run the following command in your terminal:"
Write-Host ".\.venv\Scripts\activate"
Write-Host "Once activated, you can add packages with 'uv add <package_name>'"
