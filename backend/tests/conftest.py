"""
Forces the test suite onto an isolated in-memory SQLite database
instead of whatever INFRAOS_DATABASE_URL / infraos.db would otherwise
be used locally -- this must run before any app module is imported,
since app/db.py reads the env var at import time.
"""
import os

os.environ["INFRAOS_DATABASE_URL"] = "sqlite:///:memory:"
