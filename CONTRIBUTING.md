# Contributing to VibeMol

Thanks for your interest! VibeMol is MIT-licensed and built to be expanded. This guide covers
local setup and conventions.

## Project structure

This is a monorepo:

- `packages/backend/` — the `vibemol` Python package (FastAPI server, parsers, selection
  engine, geometry, commands, plugins).
- `packages/frontend/` — the TypeScript + Three.js single-page app.

## Local setup

```bash
# Backend (Python 3.11+)
python3 -m venv .venv && source .venv/bin/activate
pip install -e "packages/backend[dev]"

# Frontend (Node 18+)
cd packages/frontend && npm install
```

## Running

```bash
vibemol serve              # API + built frontend at http://localhost:8000
# in another terminal, for hot-reload:
cd packages/frontend && npm run dev
```

## Quality gates

Before opening a PR, make sure these pass:

```bash
# backend (run from the package dir so its pyproject config is picked up)
cd packages/backend && ruff check . && mypy vibemol && pytest && cd -

# frontend
cd packages/frontend && npm run lint && npm run typecheck && npm test && cd -
```

CI runs the same checks on every pull request.

## Conventions

- **Backend** owns scene state; the **frontend** owns the camera. Don't round-trip camera
  changes. New structural features mutate backend state and stream geometry to the client.
- Stream **binary** buffers for geometry — never JSON arrays of vertices.
- New PyMOL-compatible commands go in `vibemol/commands/` and register with the command
  registry. Add a selection-engine test (string → expected atom count) for selection changes.
- Keep the wire protocol defined once in `vibemol/protocol/` and mirror types in the frontend
  `src/protocol/`.

## License

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE).
