import argparse
import json
import os
from urllib.request import Request, urlopen


def _default_url():
    explicit = (os.getenv("HEALTHCHECK_URL") or "").strip()
    if explicit:
        return explicit
    public_url = (os.getenv("PUBLIC_GAME_URL") or "").strip().rstrip("/")
    if public_url:
        return f"{public_url}/healthz"
    return "http://127.0.0.1/healthz"


def main():
    parser = argparse.ArgumentParser(description="Check public game health endpoint")
    parser.add_argument("--url", default=_default_url(), help="Health endpoint URL")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout seconds")
    args = parser.parse_args()

    try:
        req = Request(args.url, method="GET")
        with urlopen(req, timeout=float(args.timeout)) as resp:
            status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
            body = resp.read().decode("utf-8", errors="replace")
        payload = {
            "ok": 200 <= status < 300,
            "status": status,
            "url": args.url,
            "body": body[:400],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload["ok"] else 1
    except Exception as exc:
        payload = {
            "ok": False,
            "status": 0,
            "url": args.url,
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
