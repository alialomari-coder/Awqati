"""Official Action API and conservative semantic HTML extraction, stdlib only."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

from ..application.data_update_service import DataUpdateError
from ..domain.on_this_day import Day, Entry, Context, Link, Section, Failure, OnThisDayError, SECTION_KEYS
from .network_services import HttpsTransport
from .on_this_day_links import safe_wikipedia_url

AR_MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")
EN_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
LABELS = {"ar": ("أحداث", "مواليد", "وفيات", "أعياد ومناسبات"),
          "en": ("Events", "Births", "Deaths", "Holidays and observances")}
HEADINGS = {f"h{i}" for i in range(1, 7)}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
SKIP_CLASSES = {"reference", "mw-editsection", "mw-empty-elt", "noprint", "reflist", "navbox", "hatnote"}
YEAR = re.compile(r"^(\d{1,4}(?:\s*(?:ق\s*\.\s*م\.?|BCE?\.?))?)(?:\s*[–—−ـ-]\s*|\s*$)", re.I)


class Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    @property
    def skipped(self):
        return (self.tag in {"script", "style", "figure"} or
                bool(SKIP_CLASSES.intersection(self.attrs.get("class", "").split())) or
                self.attrs.get("role") == "note" or "hidden" in self.attrs or
                self.attrs.get("aria-hidden") == "true" or
                "display:none" in self.attrs.get("style", "").replace(" ", ""))


class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.broken = False
        self.feed(html)
        self.close()
        if len(self.stack) != 1 or self.broken:
            raise OnThisDayError(Failure.EXTRACTION, "unbalanced HTML")

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if len(self.stack) == 1 or self.stack[-1].tag != tag:
            self.broken = True
        else:
            self.stack.pop()

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def text(node, *, own=False):
    if isinstance(node, str):
        return node
    if node.skipped or (own and node.tag in {"ul", "ol"}):
        return ""
    if node.tag == "br":
        return " "
    return "".join(text(child, own=own) for child in node.children)


def clean(value):
    return " ".join(value.replace("\u200e", "").replace("\u200f", "").split())


def walk(node):
    if isinstance(node, Node) and not node.skipped:
        yield node
        for child in node.children:
            yield from walk(child)


def heading_text(html):
    return clean(text(Tree(html).root))


def readable_item(node, language):
    """Extract plain text plus safe anchor spans; never retain source HTML."""
    pieces, anchors = [], []
    length = 0

    def collect(child):
        nonlocal length
        if isinstance(child, str):
            pieces.append(child)
            length += len(child)
            return
        if child.skipped or child.tag in {"ul", "ol"}:
            return
        start = length
        if child.tag == "br":
            pieces.append(" ")
            length += 1
        else:
            for descendant in child.children:
                collect(descendant)
        if child.tag == "a":
            if any(isinstance(n, Node) and n is not child and n.tag == "a" for n in walk(child)):
                raise OnThisDayError(Failure.EXTRACTION, "nested anchors are unsupported")
            url = safe_wikipedia_url(child.attrs.get("href"), language)
            if url:
                anchors.append((start, length, url))

    collect(node)
    raw = "".join(pieces)
    normalized, mapping = [], {}
    pending_space = False
    for index, char in enumerate(raw):
        if char in "\u200e\u200f":
            continue
        if char.isspace():
            pending_space = bool(normalized)
            continue
        if pending_space:
            normalized.append(" ")
            pending_space = False
        mapping[index] = len(normalized)
        normalized.append(char)
    plain = "".join(normalized)
    links = []
    for start, end, url in anchors:
        visible = [mapping[i] for i in range(start, end) if i in mapping]
        if visible:
            a, b = visible[0], visible[-1] + 1
            links.append(Link(plain[a:b], url, a, b))
    return plain, tuple(links)


def extract_section(nodes, key, language):
    entries = []

    def visit_list(node, year=None, context=()):
        for item in node.children:
            if isinstance(item, str):
                if clean(item):
                    raise OnThisDayError(Failure.EXTRACTION, "text outside a list item")
                continue
            if item.skipped:
                continue
            if item.tag != "li":
                raise OnThisDayError(Failure.EXTRACTION, "unexpected list child")
            own, links = readable_item(item, language)
            lists = []
            def find_lists(container):
                for child in container.children:
                    if not isinstance(child, Node) or child.skipped:
                        continue
                    if child.tag in {"ul", "ol"}:
                        lists.append(child)
                    else:
                        if child.tag in {"table", "dl"}:
                            raise OnThisDayError(Failure.EXTRACTION, "unsupported list structure")
                        find_lists(child)
            find_lists(item)
            match = YEAR.match(own) if key != "observances" else None
            effective_year = match.group(1) if match else year
            body = own[match.end():] if match else own
            if key != "observances" and effective_year is None:
                raise OnThisDayError(Failure.EXTRACTION, "historical item without a reliable year")
            if body:
                entries.append(Entry(own, effective_year, context, links))
            elif not lists:
                raise OnThisDayError(Failure.EXTRACTION, "empty list item")
            nested_context = context + ((Context(own, links),) if own else ())
            for nested in lists:
                visit_list(nested, effective_year, nested_context)

    def visit(node):
        if isinstance(node, str):
            if clean(node):
                raise OnThisDayError(Failure.EXTRACTION, "unrecognized content outside lists")
            return
        if node.skipped or node.tag in HEADINGS:
            return
        if node.tag in {"ul", "ol"}:
            visit_list(node)
        elif node.tag in {"div", "section", "span"}:
            for child in node.children:
                visit(child)
        elif node.tag in {"style", "link", "meta", "hr"} or not clean(text(node)):
            return
        else:
            raise OnThisDayError(Failure.EXTRACTION, f"unsupported section element: {node.tag}")
    for node in nodes:
        visit(node)
    return tuple(entries)


def parse_document(document, local_date, language):
    """Never publish a partially parsed section; other sections stay independent."""
    if not isinstance(document, dict):
        raise OnThisDayError(Failure.RESPONSE, "JSON root must be an object")
    if "error" in document:
        code = document["error"].get("code", "") if isinstance(document["error"], dict) else ""
        kind = (Failure.UNAVAILABLE if code == "missingtitle" else
                Failure.RATE_LIMIT if code in {"ratelimited", "maxlag"} else Failure.API)
        raise OnThisDayError(kind, f"MediaWiki API error: {code}")
    if document.get("warnings"):
        raise OnThisDayError(Failure.RESPONSE, "MediaWiki returned API warnings")
    try:
        parsed = document["parse"]
        title, revision, html = parsed["title"], parsed["revid"], parsed["text"]
        toc = parsed["tocdata"]["sections"]
        if (not isinstance(title, str) or not title or type(revision) is not int or revision <= 0
                or not isinstance(html, str) or not isinstance(toc, list)):
            raise ValueError("invalid metadata")
        tree = Tree(html)
        # Flatten transparent wrappers, preserving list subtrees and heading order.
        blocks = []
        def flatten(node):
            if isinstance(node, str) or node.skipped:
                blocks.append(node)
            elif node.tag in {"div", "section"} or node is tree.root:
                for child in node.children:
                    flatten(child)
            else:
                blocks.append(node)
        flatten(tree.root)
        headings = [(i, int(n.tag[1]), clean(text(n))) for i, n in enumerate(blocks)
                    if isinstance(n, Node) and n.tag in HEADINGS]
        sections = []
        for key, label in zip(SECTION_KEYS, LABELS[language]):
            matches = [(i, level) for i, level, name in headings if name == label]
            toc_matches = [item for item in toc if heading_text(item["line"]) == label]
            if not matches and not toc_matches:
                sections.append(Section(key, failure=Failure.UNAVAILABLE, detail="section absent"))
                continue
            try:
                if len(matches) != 1 or len(toc_matches) != 1:
                    raise OnThisDayError(Failure.EXTRACTION, "ambiguous or inconsistent heading")
                start, level = matches[0]
                if toc_matches[0]["hLevel"] != level:
                    raise OnThisDayError(Failure.EXTRACTION, "TOC heading level mismatch")
                end = next((i for i, depth, _ in headings if i > start and depth <= level), len(blocks))
                entries = extract_section(blocks[start + 1:end], key, language)
                sections.append(Section(key, entries, None if entries else Failure.UNAVAILABLE))
            except OnThisDayError as error:
                sections.append(Section(key, failure=error.kind, detail=str(error)))
        return Day(local_date, language, title, revision,
                   f"https://{language}.wikipedia.org/w/index.php?title={quote(title)}&oldid={revision}",
                   datetime.now(timezone.utc).isoformat(), tuple(sections))
    except OnThisDayError:
        raise
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise OnThisDayError(Failure.RESPONSE, "invalid parse response schema") from error


def retry_seconds(value):
    try:
        return max(60.0, float(value))
    except (ValueError, TypeError):
        try:
            return max(60.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 60.0


class WikipediaTransport(HttpsTransport):
    # Reuse HTTPS/cancellation/size/redirect protection; inspect the preserved cause.
    MAX_BYTES = 16 * 1024 * 1024

    def read_json(self, url, *, timeout, cancellation):
        try:
            raw = self.read_bytes(url, timeout=timeout, cancellation=cancellation)
        except DataUpdateError as error:
            cause = error.__cause__
            if isinstance(cause, HTTPError):
                kind = (Failure.RATE_LIMIT if cause.code == 429 else
                        Failure.SERVER if 500 <= cause.code <= 599 else Failure.ACCESS)
                raise OnThisDayError(kind, f"Wikipedia HTTP {cause.code}",
                                     retry_after=retry_seconds(cause.headers.get("Retry-After"))) from error
            kind = Failure.CONNECTION if isinstance(cause, (URLError, OSError, socket.timeout)) else Failure.RESPONSE
            raise OnThisDayError(kind, str(error)) from error
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise OnThisDayError(Failure.RESPONSE, "invalid JSON") from error


class WikipediaDayProvider:
    def __init__(self, transport=None):
        self.transport = transport or WikipediaTransport()

    def fetch(self, local_date, language, cancellation):
        if language not in LABELS:
            raise OnThisDayError(Failure.UNAVAILABLE, "unsupported language")
        title = (f"{local_date.day} {AR_MONTHS[local_date.month - 1]}" if language == "ar" else
                 f"{EN_MONTHS[local_date.month - 1]} {local_date.day}")
        query = urlencode(dict(action="parse", page=title, prop="tocdata|text|revid", format="json",
                              formatversion=2, redirects=1, disableeditsection=1, maxlag=5))
        cancellation.raise_if_cancelled()
        document = self.transport.read_json(f"https://{language}.wikipedia.org/w/api.php?{query}",
                                            timeout=30, cancellation=cancellation)
        cancellation.raise_if_cancelled()
        result = parse_document(document, local_date, language)
        cancellation.raise_if_cancelled()
        return result
