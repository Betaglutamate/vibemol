# VibeMol Architecture

This document captures the design decisions and roadmap. It is the canonical reference for
contributors.

## Goals

- Mirror PyMOL's **core** functionality in the browser.
- Be **easy to extend** (plugin system, public protocol).
- **MIT-licensed**, free, and community-expandable.
- Run identically **locally or in the cloud** with no server GPU.

## Locked decisions

1. **Hybrid compute** — Python backend parses files, evaluates selections, and computes
   expensive geometry (surfaces, cartoons). The **browser renders everything with WebGL**.
2. **Engine built fresh on permissive FOSS libs** — Gemmi + BioPython (parsing), RDKit
   (chemistry), NumPy/SciPy + scikit-image (geometry), plus our own selection engine and
   command API. No dependency on the C++ pymol-open-source codebase.
3. **Custom Three.js renderer** — full control of a PyMOL-faithful look and command-driven
   behavior.
4. **Single-user first**; the backend stays the authoritative scene owner so real-time
   collaboration can be layered on later without a rewrite.
5. **MIT license.**

## Where state lives

The **backend owns the scene graph** — objects, states, selections, representations, colors,
settings, named scenes (the PyMOL model, split over a network). The **client owns the
camera**, so orbit/zoom/pan are instant and never round-trip.

Flow: a structural command (`load`, `show`, `color`, `select`, surface, …) mutates backend
state → the backend computes geometry → it streams compact binary buffers to the client →
the client updates GPU resources and renders. Camera manipulation stays entirely client-side.

```
                 commands (msgpack)
   browser  ───────────────────────────────▶  python backend
  (Three.js)                                    (FastAPI)
   renderer  ◀───────────────────────────────  scene graph
   + camera     scene diffs + geometry buffers   + geometry compute
```

## Tech stack

| Layer    | Choices |
|----------|---------|
| Backend  | Python 3.11+, FastAPI, Uvicorn, Pydantic v2, Gemmi, RDKit, BioPython, NumPy/SciPy, scikit-image, msgpack |
| Frontend | TypeScript, Vite, Three.js (custom GLSL impostor shaders), React + Zustand, msgpack |
| Protocol | JSON/msgpack for state & commands; raw typed-array buffers for geometry |
| Tooling  | pytest, ruff, mypy; vitest, eslint, prettier, Playwright; pre-commit; GitHub Actions; Docker; MkDocs |

## Repository layout

See the directory tree in the project plan. In short: a monorepo with `packages/backend`
(the `vibemol` Python package) and `packages/frontend` (the Vite/TS app), plus `examples/`,
`docs/`, `docker/`, and CI under `.github/`.

## Roadmap

- **Phase 0 — Foundations & walking skeleton** *(in progress)*: monorepo, server + WS hub,
  `vibemol serve`, and an end-to-end skeleton (parse a PDB → stream atoms → render spheres →
  orbit camera).
- **Phase 1 — Core (MVP)**: I/O (PDB/mmCIF/SDF/MOL2/XYZ + RCSB fetch), structure model,
  selection engine v1, representations (lines/sticks/ball&stick/spheres/nonbonded/dots),
  coloring, command console, object/selection UI, `.vibe` sessions.
- **Phase 2 — Advanced**: cartoon, surfaces, trajectories/states, measurements, alignment,
  sequence viewer, high-quality look (SSAO + outline), scenes & movies.
- **Phase 3 — Extensibility**: backend & frontend plugin APIs, scripting (`.pml` + Python),
  versioned public protocol + client SDKs, plugin template.
- **Phase 4 — Productionization**: auth/workspaces, real-time collaboration, embeddable
  widget, large-structure performance, desktop packaging, docs & release automation.
