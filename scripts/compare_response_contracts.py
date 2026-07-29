import hashlib
import json
import re

from perf_harness import DEFAULT_ROUTES, common_parser, isolated_app, logged_in_client, parse_route, request_route


NORMALIZERS = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "<uuid>"),
    (re.compile(r"request_id=[^\"'&< ]+"), "request_id=<normalized>"),
    (re.compile(r"ct[_-]?remain(?:ing)?[\"']?[:=][\"']?\d+", re.I), "ct_remain=0"),
    (re.compile(r"\b\d{10,13}\b"), "<timestamp>"),
]


def normalize_html(html):
    text = html
    for pattern, replacement in NORMALIZERS:
        text = pattern.sub(replacement, text)
    return text


def contract_for_response(response):
    html = normalize_html(response.get_data(as_text=True))
    links = re.findall(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"']", html, flags=re.I)
    buttons = re.findall(r"<button\b[^>]*>(.*?)</button>", html, flags=re.I | re.S)
    forms = re.findall(r"<form\b[^>]*>", html, flags=re.I)
    headings = re.findall(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", html, flags=re.I | re.S)
    data_attrs = re.findall(r"\s(data-[a-zA-Z0-9_-]+)=", html)
    return {
        "status": int(response.status_code),
        "hash": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "bytes": len(html.encode("utf-8")),
        "links": links,
        "button_count": len(buttons),
        "form_count": len(forms),
        "headings": [" ".join(re.sub(r"<[^>]+>", "", h).split()) for h in headings],
        "data_attrs": sorted(set(data_attrs)),
    }


def main():
    parser = common_parser("Capture normalized response contracts for GET pages.")
    args = parser.parse_args()
    routes = [parse_route(route) for route in args.route] if args.route else [route for route in DEFAULT_ROUTES if route[0] == "GET"]
    report = {"routes": []}
    with isolated_app() as (game_app, user_id, username):
        client = logged_in_client(game_app, user_id, username)
        for method, path in routes:
            if method != "GET":
                continue
            response = request_route(client, method, path)
            report["routes"].append({"method": method, "route": path, **contract_for_response(response)})
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
