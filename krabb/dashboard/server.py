"""Dashboard HTTP server for krabb — serves static files on port 4242."""

from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve static files from the dashboard/static directory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def log_message(self, format, *args):  # noqa: A002
        pass


def run_dashboard(port: int = 4242) -> None:
    """Start the dashboard HTTP server (blocking)."""
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"krabb dashboard serving on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nkrabb dashboard stopped.")
        server.server_close()


if __name__ == "__main__":
    run_dashboard()
