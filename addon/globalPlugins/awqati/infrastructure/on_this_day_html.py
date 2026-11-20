"""Escape extracted records and revalidate links at the HTML boundary."""
from html import escape
import re
from .on_this_day_links import safe_wikipedia_url
from ..application.on_this_day_presentation import heading, section_tree, LABELS, N_

# Only a year-only parent is expanded. Actual parent information stays with
# its children in the same list item, in source order, without a nested list.
YEAR_ONLY = re.compile(r"^\d{1,4}(?:\s*(?:ق\s*\.\s*م\.?|BCE?\.?))?\s*[–—−-]?\s*$", re.I)


def historical_items(nodes, language, prefix=""):
    items = []
    def details(children):
        return "".join("<div>" + linked_text(text, links, language)
                       + details(nested) + "</div>" for text, links, nested in children)
    for text, links, children in nodes:
        own = linked_text(text, links, language)
        if children and YEAR_ONLY.fullmatch(text):
            items.extend(historical_items(children, language, prefix + own + " "))
        else:
            items.append(prefix + own + details(children))
    return items


def observance_content(nodes, language, level=2):
    """Source non-leaf nodes are group headings, leaves are counted items."""
    parts, pending, count = [], [], 0
    def flush():
        if pending:
            parts.append("<ul>" + "".join(pending) + "</ul>")
            pending.clear()
    for text, links, children in nodes:
        own = linked_text(text, links, language)
        if children:
            flush()
            tag = f"h{min(level, 6)}"
            child_html, child_count = observance_content(children, language, level + 1)
            parts.append(f"<section><{tag}>{own}</{tag}>{child_html}</section>")
            count += child_count
        else:
            pending.append("<li>" + own + "</li>")
            count += 1
    flush()
    return "".join(parts), count


def summary(key, count, translate):
    unit = {"events": (N_("event"), N_("events")),
            "births": (N_("person"), N_("people")),
            "deaths": (N_("person"), N_("people")),
            "observances": (N_("observance"), N_("observances"))}[key][count != 1]
    return translate(N_("{section}: {count} {unit}")).format(
        section=translate(LABELS[key]), count=count, unit=translate(unit))

def linked_text(text, links, language):
    """Revalidate both destinations and offsets, leaving rejected links as text."""
    pieces, position = [], 0
    for link in links:
        if (type(link.start) is not int or type(link.end) is not int
                or not position <= link.start < link.end <= len(text)
                or text[link.start:link.end] != link.text):
            continue
        url = safe_wikipedia_url(link.url, language)
        if not url:
            continue
        pieces.extend((escape(text[position:link.start]),
                       f'<a href="{escape(url, quote=True)}" rel="noreferrer">{escape(link.text)}</a>'))
        position = link.end
    pieces.append(escape(text[position:]))
    return "".join(pieces)


def render_html(day, key, translate):
    if day.language not in {"ar", "en"}:
        raise ValueError("unsupported document language")
    title = escape(heading(day, key, translate))
    nodes = section_tree(day, key)
    if key == "observances":
        body, count = observance_content(nodes, day.language)
    else:
        items = historical_items(nodes, day.language)
        body = "<ul>" + "".join("<li>" + item + "</li>" for item in items) + "</ul>"
        count = len(items)
    body = '<p>' + escape(summary(key, count, translate)) + '</p>' + body
    source = safe_wikipedia_url(day.source_url, day.language)
    if source:
        body += '<p><a href="{}" rel="noreferrer">{}</a></p>'.format(
            escape(source, quote=True), escape(translate(N_("Original day page on Wikipedia"))))
    return (f'<!doctype html><html lang="{day.language}" dir="{"rtl" if day.language == "ar" else "ltr"}">'
            '<head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'base-uri \'none\'; form-action \'none\'">'
            '<meta name="referrer" content="no-referrer">'
            f'<title>{title}</title></head><body><main><h1>{title}</h1>'
            f'{body}</main></body></html>')

