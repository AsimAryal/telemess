# Python Project Template

This template provides a standardized Python project setup to ensure consistency across development environments, code quality, and version control practices.

-----

## First-Time Setup

After cloning this repository, run the appropriate setup script for your operating system.<br>
These scripts are intended to be run only once.<br>
<b>Set python version you want in the setup script<b> default is 3.11<br>
<b>Set the project name in the setup script<b>

### Linux/macOS

bash <br><br>
`chmod +x setup/linux_setup.sh` <br>
`./setup/linux_setup.sh`


### Windows (PowerShell)

powershell<br>
Run this first:<br>
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

Then run this to setup your environment:<br>
`.\setup\setup_windows.ps1`



-----

## What Gets Installed

The setup process configures your environment with the following tools and files:

| Tool | Purpose |
| :--- | :--- |
| **uv** | A modern Python package manager and virtual environment tool. |
| **ruff** | A fast Python linter and formatter that enforces code style. |
| **pre-commit** | A framework for managing Git hooks to run automated checks. |
| **pyproject.toml** | Central configuration for dependencies and tool settings. |
| **uv.lock** | Lockfile to ensure consistent dependency resolution. |
| **.venv/** | A local virtual environment for isolated package installation. |
| **.pre-commit-config.yaml** | Configuration for standard pre-commit hooks. |

-----

## What the Setup Scripts Do

  * **Install Tools**: Installs `uv`, `ruff`, and `pre-commit` if they are not already installed.
  * **Create Virtual Environment**: Creates a virtual environment in `.venv/` using `uv venv`.
  * **Initialize Project**: Runs `uv init -y` if `pyproject.toml` does not already exist.
  * **Track Dependencies**: Installs `pre-commit` via `uv add` so it is tracked in `pyproject.toml` and `uv.lock`.
  * **Configure Git Hooks**: Creates `.pre-commit-config.yaml` if not present, with hooks for:
      * `ruff` for linting and formatting
      * Fixing trailing whitespace and missing end-of-file newlines
      * Checking for unresolved merge conflicts
      * Checking for accidentally added large files (limit: 1024 KB)
      * Secret scanning via `detect-secrets`
  * **Install Hooks**: Installs Git hooks for both commit and push actions using `pre-commit`.
  * **Sync Dependencies**: Uses `uv pip sync` to install all dependencies listed in `pyproject.toml` and `uv.lock`.

This ensures that your local environment is in sync with project requirements and that all automated checks are enforced from the beginning.

-----

## Ongoing Usage

### Installing New Packages

Use `uv add` to add any new dependencies:

```bash
uv add <package-name>
```

### Synchronizing Dependencies

If joining an existing project or switching machines, run:

```bash
uv sync
```

It automatically looks for a pyproject.toml and a corresponding uv.lock file in your current directory.<br>
It intelligently checks if your uv.lock is out of date with pyproject.toml.<br>
If it is, it first resolves the dependencies and updates uv.lock.<br>
Then, it installs the exact versions from the uv.lock file<br>

### Running Lint Checks Manually

Execute all configured checks on all files:

```bash
pre-commit run --all-files
```

### Updating Pre-commit Hooks

Periodically update the hooks to their latest versions:

```bash
pre-commit autoupdate
```

-----

## Standard README Structure for Your Project

Once the setup is complete, this README should be replaced with project-specific content.<br>
The following structure is recommended:

````markdown
# Project Name

## Overview

A brief description of the project and its purpose.

## Setup

### Linux/macOS

bash
`chmod +x setup.sh` <br>
`./setup/setup.sh`

### Windows (PowerShell)

powershell<br>
Run this first:<br>
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

Then run this to setup your environment:<br>
`.\setup\setup_windows.ps1`



## Usage

Instructions on how to run the application, services, or scripts.

## Linting and Code Quality

To check code formatting and perform other pre-commit checks:

bash<br>
`pre-commit run --all-files`
