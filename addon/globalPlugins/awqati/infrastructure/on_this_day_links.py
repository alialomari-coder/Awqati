"""Validate article destinations without accessing or executing them."""
import re
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit


def safe_wikipedia_url(href, language):
    if not isinstance(href, str) or not href or href.startswith("#"):
        return None
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in "\\\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069" for c in unquote(href)):
        return None
    try:
        parts = urlsplit(urljoin(f"https://{language}.wikipedia.org/", href))
        if (parts.scheme not in {"https", "http"} or parts.username is not None or parts.password is not None
                or parts.port is not None or not parts.hostname
                or not re.fullmatch(r"[a-z0-9-]+\.wikipedia\.org", parts.hostname)):
            return None
        query = parse_qs(parts.query)
        if query.get("action", ["view"]) != ["view"] or "redlink" in query:
            return None
        if not ((parts.path.startswith("/wiki/") and len(parts.path) > 6)
                or (parts.path == "/w/index.php" and query.get("title"))):
            return None
        return urlunsplit(("https", parts.hostname, parts.path, parts.query, parts.fragment))
    except (ValueError, UnicodeError):
        return None
