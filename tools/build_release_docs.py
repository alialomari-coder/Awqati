"""Build the final Arabic and English Awqati user guides.

The Arabic source is owner-approved plain text.  This tool applies Markdown
structure only, then creates small, accessible, dependency-free HTML files for
both supported languages.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
AR_SOURCE = ROOT / "docs" / "دليل_أوقاتي_العربي_المعتمد.md"
AR_MARKDOWN = ROOT / "addon" / "doc" / "ar" / "readme.md"
EN_MARKDOWN = ROOT / "addon" / "doc" / "en" / "readme.md"


AR_HEADINGS = {
	"نظرة عامة": 1,
	"طريقة الاستخدام": 2,
	"تحديد الموقع": 3,
	"عرض اتجاه القبلة": 3,
	"تفعيل جميع التنبيهات التلقائية": 3,
	"تفعيل ساعات الهدوء": 3,
	"نسخ معلومات التشخيص": 3,
	"فحص تحديثات البيانات": 3,
	"أقسام إعدادات الإضافة": 2,
	"مواقيت الصلاة": 3,
	"تفعيل تنبيهات المواقيت": 4,
	"فتح نافذة مواقيت اليوم": 4,
	"التحقق من مواقيت اليوم عبر الإنترنت": 4,
	"طريقة حساب مواقيت الصلاة": 4,
	"حساب العصر": 4,
	"معالجة خطوط العرض العليا": 4,
	"مدة بقاء الصلاة الحالية بعد الإقامة، بالدقائق": 4,
	"الوقت المراد ضبطه": 4,
	"إعدادات الوقت المختار": 4,
	"تصحيح الوقت بالدقائق": 4,
	"التنبيه قبل دخول الوقت": 4,
	"إجراء التنبيه قبل دخول الوقت": 4,
	"إجراء التنبيه عند دخول الوقت": 4,
	"إعدادات الإقامة للصلوات الخمس": 4,
	"المدة بين الأذان والإقامة": 4,
	"التنبيه قبل الإقامة": 4,
	"إجراء التنبيه قبل الإقامة": 4,
	"التنبيه البعدي للأوقات الأخرى": 4,
	"الساعة": 3,
	"اختر إعدادات الساعة": 4,
	"صيغة النطق": 4,
	"نظام الساعات": 4,
	"تمثيل النطق": 4,
	"نطق الثواني": 4,
	"نطق عبارة «صفر دقيقة»": 4,
	"تجربة النطق": 4,
	"تفعيل تنبيهات الساعة التلقائية": 4,
	"إجراء تنبيه الساعة": 4,
	"التاريخ": 3,
	"التقويم الأساسي": 4,
	"تضمين معلومات التقويم العربي في معلومات اليوم": 4,
	"فتح نافذة معلومات اليوم": 4,
	"اختر التقويم المراد ضبطه": 4,
	"صيغة التاريخ": 4,
	"تصحيح التاريخ الهجري القمري": 4,
	"تنبيهات الأذكار": 3,
	"تفعيل تنبيهات الأذكار": 4,
	"أذكار الصباح": 4,
	"أذكار المساء": 4,
	"ساعة الجمعة": 4,
	"الورد اليومي": 4,
	"إجراء التنبيه": 4,
	"تفعيل الأذكار الدورية": 4,
	"خارطة الاختصارات": 2,
	"تلقي ملاحظاتكم": 2,
	"سجل التغييرات": 2,
	"الإصدار 4.0.0": 3,
	"الإصدار 3.2": 3,
	"الإصدار 3.1": 3,
	"الإصدار 3.0": 3,
	"الإصدار 2.1": 3,
	"الإصدار 1.3": 3,
}


def build_arabic_markdown(source: str) -> str:
	output: list[str] = []
	for raw_line in source.splitlines():
		line = raw_line.rstrip()
		if not line:
			output.append("")
			continue
		level = AR_HEADINGS.get(line)
		if level:
			if output and output[-1] != "":
				output.append("")
			output.extend(("#" * level + " " + line, ""))
		elif line.startswith("•"):
			output.append("- " + line[1:].lstrip())
		else:
			output.append(line)
	while output and output[-1] == "":
		output.pop()
	return "\n".join(output) + "\n"


def _inline(text: str) -> str:
	text = escape(text, quote=False)
	text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
	text = re.sub(r"\[([^]]+)]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
	if re.fullmatch(r"[^\s@]+@[^\s@]+", text):
		return f'<a href="mailto:{text}">{text}</a>'
	return text


def markdown_to_html(markdown: str, *, lang: str, direction: str, title: str) -> str:
	lines = markdown.splitlines()
	body: list[str] = []
	paragraph: list[str] = []
	list_type: str | None = None

	def flush_paragraph() -> None:
		if paragraph:
			body.append("<p>" + " ".join(_inline(part) for part in paragraph) + "</p>")
			paragraph.clear()

	def close_list() -> None:
		nonlocal list_type
		if list_type:
			body.append(f"</{list_type}>")
			list_type = None

	for line in lines:
		heading = re.fullmatch(r"(#{1,6})\s+(.+)", line)
		ordered = re.fullmatch(r"\d+\.\s+(.+)", line)
		unordered = re.fullmatch(r"-\s+(.+)", line)
		if heading:
			flush_paragraph()
			close_list()
			level = len(heading.group(1))
			body.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
		elif ordered or unordered:
			flush_paragraph()
			new_type = "ol" if ordered else "ul"
			if list_type != new_type:
				close_list()
				body.append(f"<{new_type}>")
				list_type = new_type
			body.append(f"<li>{_inline((ordered or unordered).group(1))}</li>")
		elif not line.strip():
			flush_paragraph()
			close_list()
		else:
			close_list()
			paragraph.append(line.strip())
	flush_paragraph()
	close_list()
	return "\n".join((
		"<!doctype html>",
		f'<html lang="{lang}" dir="{direction}">',
		"<head>",
		'<meta charset="utf-8">',
		'<meta name="viewport" content="width=device-width, initial-scale=1">',
		f"<title>{escape(title)}</title>",
		"</head>",
		"<body>",
		*body,
		"</body>",
		"</html>",
		"",
	))


def main() -> int:
	arabic_source = AR_SOURCE.read_text(encoding="utf-8-sig")
	arabic_markdown = build_arabic_markdown(arabic_source)
	english_markdown = EN_MARKDOWN.read_text(encoding="utf-8")
	AR_MARKDOWN.parent.mkdir(parents=True, exist_ok=True)
	AR_MARKDOWN.write_text(arabic_markdown, encoding="utf-8", newline="\n")
	(AR_MARKDOWN.parent / "readme.html").write_text(
		markdown_to_html(arabic_markdown, lang="ar", direction="rtl", title="دليل استخدام أوقاتي 4.0.0"),
		encoding="utf-8",
		newline="\n",
	)
	(EN_MARKDOWN.parent / "readme.html").write_text(
		markdown_to_html(english_markdown, lang="en", direction="ltr", title="Awqati 4.0.0 user guide"),
		encoding="utf-8",
		newline="\n",
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
