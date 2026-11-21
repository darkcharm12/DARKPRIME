"""WSGI entry point (used by gunicorn behind nginx)."""
from server.app import create_app

app = create_app()
