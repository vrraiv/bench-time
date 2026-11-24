"""Serve the built preview site (site/dist) locally with clean URLs, as the Worker does:
/questions serves questions.html. The reply API (/api/*) is not served, so pages show
"Replies unavailable".

    uv run --no-sync python scripts/serve_dist.py [port]
"""

from __future__ import annotations

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "site" / "dist"


class CleanURLHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path, _, rest = self.path.partition("?")
        base = path.split("#", 1)[0]
        if base != "/" and not Path(base).suffix and (DIST / f"{base.lstrip('/')}.html").exists():
            self.path = f"{base}.html" + (f"?{rest}" if rest else "")
        return super().send_head()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    handler = partial(CleanURLHandler, directory=str(DIST))
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
