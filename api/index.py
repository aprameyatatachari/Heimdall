"""Vercel entrypoint for the FastAPI application.

Vercel's Python runtime looks for a module under `api/` and serves the ASGI
callable it exports. This file is that shim and nothing else: it puts `backend/`
on the import path and re-exports the application, so the deployed code is the
same code that runs locally with `uvicorn app.main:app`.

Two things this file deliberately does **not** do:

* It does not run migrations. Every invocation of a serverless function could
  run them concurrently, and a schema change during a request is a schema change
  under every other request in flight. Migrations are a release step, run once,
  from the deployment workflow. See docs/deployment.md.
* It does not create state that has to survive the invocation. Vercel may freeze
  or discard a function at any moment; anything that must persist belongs in
  PostgreSQL, which is why `SERVERLESS=true` also switches the engine to
  `NullPool` rather than holding connections open across invocations.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The application package lives in `backend/`, which is not on the path when
# Vercel imports this module from the repository root.
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app as app  # noqa: E402  (path setup must come first)
