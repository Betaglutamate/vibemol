# VibeMol

A free, open-source, **web-native molecular viewer** — PyMOL's core functionality, in the
browser. Run it on your laptop or in the cloud, drive it with a PyMOL-compatible command
console, and extend it with plugins.

> Status: **early development** (Phase 0 — walking skeleton). See
> [ARCHITECTURE.md](ARCHITECTURE.md) for the design and roadmap.

## Why

PyMOL is the de-facto desktop tool for molecular visualization, but it is heavyweight to
install, awkward to embed, and hard to extend. VibeMol aims to mirror its essentials in a
zero-install web app that is MIT-licensed and built to be expanded by a community.

## Architecture at a glance

- **Backend (Python)** — parses structures (PDB/mmCIF/SDF/MOL2/XYZ), evaluates a PyMOL-style
  atom-selection language, and computes geometry. The backend owns the *scene*.
- **Frontend (TypeScript + Three.js)** — renders everything with WebGL and owns the *camera*,
  so orbit/zoom/pan are instant.
- **Hybrid compute** — heavy work runs server-side; the browser just renders. No server GPU
  needed; scales cheaply in the cloud.

```
browser (Three.js renderer, camera)  <--WebSocket-->  python (FastAPI, scene + geometry)
```

## Quick start (development)

Requires Python 3.11+ and Node 18+.

```bash
# 1. Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e "packages/backend[dev]"

# 2. Frontend
cd packages/frontend && npm install && npm run build && cd -

# 3. Run (serves the built frontend + API on http://localhost:8000)
vibemol serve
```

For frontend hot-reload during development, run `npm run dev` in `packages/frontend`
(proxies the API/WebSocket to the backend on port 8000).

## License

[MIT](LICENSE) — © 2026 VibeMol contributors. Contributions welcome; see
[CONTRIBUTING.md](CONTRIBUTING.md).
