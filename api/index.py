import sys
import os

# Ensure backend directory is in sys.path so app modules are discoverable
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app

# Vercel looks for the ASGI/WSGI callable 'app' or 'handler'
handler = app
