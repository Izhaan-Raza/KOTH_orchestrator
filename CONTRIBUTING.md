# Contributing to KoTH Orchestrator

Thank you for your interest in contributing to the KoTH Orchestrator! We've designed this platform with a flexible, API-driven architecture that makes extending it very straightforward.

## Architecture Overview (v2)

The project has moved from a monolithic, hardcoded series-based engine to a generalized, dynamic registry architecture.

- **`platform/`**: The core FastAPI server that manages the SQLite registry (Machines, Nodes, Users) and handles remote Docker orchestration via SSH/Paramiko.
- **`referee/`**: The scoring engine that polls the `platform` API for active machines and scores them.
- **`cli/`**: The Terminal UI for operators managing the event from the command line.
- **`examples/`**: A collection of vulnerable test machines.

## How to Contribute

1. **Fork and Clone**: Fork the repository and clone it locally.
2. **Setup Development Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r platform/requirements.txt
   pip install -r referee/requirements.txt
   ```
3. **Run the Platform Locally**:
   ```bash
   cd platform
   python -m uvicorn app:app --reload
   ```
4. **Make your changes**: Whether you're adding new vulnerable machines to `examples/`, enhancing the `cli/`, or optimizing the `platform/` engine, try to keep your PRs atomic and well-documented.

## Code Style

- Use standard PEP 8 formatting for Python code.
- Avoid introducing blocking I/O in the FastAPI `async` routes where possible.
- When creating new `koth-machine.yaml` specs, ensure they pass the API validation (e.g., proper difficulty tags, valid points, and valid root/king.txt paths).

## Reporting Issues

If you find a bug or have a feature request, please open an issue describing the expected behavior, the actual behavior, and steps to reproduce.
