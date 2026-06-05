# vibemol (backend)

The Python backend for [VibeMol](https://github.com/) — a web-native, open-source molecular
viewer. Parses molecular structures, evaluates a PyMOL-style atom-selection language, computes
geometry, and streams it to a WebGL frontend over WebSocket.

```bash
pip install -e ".[dev]"   # from this directory
vibemol serve             # API + WebSocket on http://localhost:8000
```

See the repository root `README.md` and `ARCHITECTURE.md` for the full picture. MIT-licensed.
