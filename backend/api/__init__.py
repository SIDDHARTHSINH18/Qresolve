"""API package.

Kept free of imports on purpose: the HTTP layer is a client of the core
pipeline in backend/api/solve.py, and importing that pipeline (from the CLI or
any local runner) must not pull FastAPI or uvicorn into the process.
"""
