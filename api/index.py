import sys
import os
from urllib.parse import parse_qs, urlencode

# Ensure backend directory is in sys.path so app modules are discoverable
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app as base_app


class VercelPathMiddleware:
    """
    ASGI middleware that restores the original request path when deployed
    under Vercel serverless rewrites (which redirect to /api/index.py).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
            params = parse_qs(query_string)
            if "__vercel_path" in params and params["__vercel_path"]:
                new_path = params.pop("__vercel_path")[0]
                scope["path"] = new_path
                scope["raw_path"] = new_path.encode("utf-8")
                # Re-encode remaining query params so endpoints don't see __vercel_path
                new_qs = urlencode(params, doseq=True)
                scope["query_string"] = new_qs.encode("utf-8")
            elif scope.get("path") in ("/api/index.py", "/index.py", "/api"):
                # Fallback to x-matched-path header if present
                for header_name, header_val in scope.get("headers", []):
                    if header_name.lower() == b"x-matched-path":
                        val = header_val.decode("utf-8", errors="ignore")
                        scope["path"] = val
                        scope["raw_path"] = header_val
                        break
        await self.app(scope, receive, send)


app = VercelPathMiddleware(base_app)
handler = app
