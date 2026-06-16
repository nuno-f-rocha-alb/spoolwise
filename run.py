import os

from app import create_app

app = create_app()


def _debug_enabled() -> bool:
    return (os.getenv("FLASK_DEBUG") or "0").strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":
    # Debug (Werkzeug reloader + interactive debugger) is OFF unless FLASK_DEBUG
    # is explicitly enabled. The interactive debugger is an RCE vector, so it must
    # never default on in a container. docker-compose.yml sets FLASK_DEBUG=0.
    app.run(host="0.0.0.0", port=5000, debug=_debug_enabled())
