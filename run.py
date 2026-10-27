"""AstroPi early-development server. Trusted LAN only."""
import argparse
from astropi.web import create_app

def main() -> None:
    parser = argparse.ArgumentParser(description="AstroPi read-only status UI")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    create_app().run(host=args.host, port=args.port, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
