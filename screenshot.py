import json


def build_navigation_html(url: str) -> str:
    serialized_url = json.dumps(url, ensure_ascii=True).replace("<", "\\u003c")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<script>setTimeout(() => window.location.replace({serialized_url}), 0);</script>"
        "</head><body data-maibot-web-screenshot-loading></body></html>"
    )
