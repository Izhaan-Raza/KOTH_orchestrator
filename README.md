# KoTH Orchestrator

Distributed King-of-the-Hill competition platform for running replicated challenge rounds with a referee-managed control plane.

![GitHub stars](https://img.shields.io/github/stars/Izhaan-Raza/KOTH_orchestrator?style=for-the-badge&logo=github) ![GitHub forks](https://img.shields.io/github/forks/Izhaan-Raza/KOTH_orchestrator?style=for-the-badge&logo=github) ![GitHub issues](https://img.shields.io/github/issues/Izhaan-Raza/KOTH_orchestrator?style=for-the-badge&logo=github) ![Express.js](https://img.shields.io/badge/Express.js-000000?style=for-the-badge&logo=express&logoColor=white)


## What This Repository Contains

- `referee-server/`: the real control plane, including the FastAPI app, scheduler, scoring, enforcement, recovery logic, dashboards, and tests
- `Series H1/` through `Series H8/`: challenge packs, each with a per-series `docker-compose.yml` and three machine variants
- `qa/`: service load probes, vulnerability validation, deployment checks, and live rule-matrix tooling
- `docs/`: architecture, operations, gameplay, and design documentation

## Operational Model

The production runtime is the distributed referee-managed model:

- challenge nodes host node-local `h1..h8` directories with copied per-series compose files
- the referee host activates and validates one series at a time over SSH
- HAProxy exposure is kept aligned with the currently active series
- scoring is based on quorum ownership of replicated variants, not on a single container's local state

Root-level `docker-compose.yml` and `rotate.sh` are local/dev-only helpers. They are not the production control plane.

## Features

- explicit runtime lifecycle: `stopped`, `starting`, `running`, `paused`, `rotating`, `faulted`, `stopping`
- distributed deploy, validate, rollback, and recovery flows
- quorum-based ownership and scoring
- rule enforcement for `king.txt` tampering, persistence, listener drift, firewall drift, and credential-file drift
- admin dashboard on `:8000` and participant board on `:9000`
- operator team controls for create, ban, and unban

## Repository Layout

```text
.
|-- referee-server/
|-- Series H1/
|-- Series H2/
|-- Series H3/
|-- Series H4/
|-- Series H5/
|-- Series H6/
|-- Series H7/
|-- Series H8/
|-- qa/
|-- docs/
|-- docker-compose.yml
`-- rotate.sh
```

## Local Development

Run the referee service locally:

```bash
cd referee-server
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

For local challenge-only experimentation, use the root `docker-compose.yml` or the per-series `orchestrator_hN.sh` helpers as development conveniences.

## Production Deployment

Use the docs in [`docs/README.md`](docs/README.md), especially:

- [Full Deployment Runbook](docs/operations/full-deployment-runbook.md)
- [Deployment Validation Checklist](docs/operations/deployment-validation-checklist.md)
- [Referee Rule Validation Checklist](docs/operations/referee-rule-validation-checklist.md)

## Documentation

- [Docs Index](docs/README.md)
- [Referee Ruling Engine Architecture](docs/architecture/referee-ruling-engine-architecture.md)
- [Machine Exploit Paths](docs/gameplay/machine-exploit-paths.md)
- [Participant Hard-Bound Rules](docs/gameplay/participant-hard-bound-rules.md)
- [Manual Tester Checklist](docs/operations/manual-tester-checklist.md)
- [Codex H1A Player Prompt](docs/gameplay/codex-h1a-player-prompt.md)

## Safety

Run this project only in infrastructure you own or are explicitly authorized to use. The challenge services are intentionally vulnerable, and parts of the QA tooling execute real exploit probes against those intentionally weak targets.

## 👥 Contributing

Contributions are welcome! Here's how you can help:

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/Izhaan-Raza/KOTH_orchestrator/tree/main.git`
3. **Create** a new branch: `git checkout -b feature/your-feature`
4. **Commit** your changes: `git commit -am 'Add some feature'`
5. **Push** to your branch: `git push origin feature/your-feature`
6. **Open** a pull request

Please ensure your code follows the project's style guidelines and includes tests where applicable.

---
