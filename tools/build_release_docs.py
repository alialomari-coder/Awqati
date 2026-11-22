"""Build the final Arabic and English Awqati user guides.

The Arabic source accepts explicit Markdown headings and legacy plain text.
This tool applies Markdown structure, then creates small, accessible, dependency-free HTML files for
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
EN_SOURCE = ROOT / "docs" / "awqati_user_guide_en.md"


AR_HEADINGS = {
	"الساعة العالمية — 5.0.0-dev13": 1,
	"قائمة المؤقتات — 5.0.0-dev13": 1,
	"نظرة عامة": 1,
	"طريقة الاستخدام": 1,
	"تحديد الموقع": 2,
	"عرض اتجاه القبلة": 2,
	"تفعيل جميع التنبيهات التلقائية": 2,
	"تفعيل ساعات الهدوء": 2,
	"نسخ معلومات التشخيص": 2,
	"فحص تحديثات البيانات": 2,
	"أقسام إعدادات الإضافة": 1,
	"مواقيت الصلاة": 2,
	"تفعيل تنبيهات المواقيت": 3,
	"فتح نافذة مواقيت اليوم": 3,
	"التحقق من مواقيت اليوم عبر الإنترنت": 3,
	"طريقة حساب مواقيت الصلاة": 3,
	"حساب العصر": 3,
	"معالجة خطوط العرض العليا": 3,
	"مدة بقاء الصلاة الحالية بعد الإقامة، بالدقائق": 3,
	"الوقت المراد ضبطه": 3,
	"إعدادات الوقت المختار": 3,
	"تصحيح الوقت بالدقائق": 3,
	"التنبيه قبل دخول الوقت": 3,
	"إجراء التنبيه قبل دخول الوقت": 3,
	"إجراء التنبيه عند دخول الوقت": 3,
	"إعدادات الإقامة للصلوات الخمس": 3,
	"المدة بين الأذان والإقامة": 3,
	"التنبيه قبل الإقامة": 3,
	"إجراء التنبيه قبل الإقامة": 3,
	"التنبيه البعدي للأوقات الأخرى": 3,
	"الساعة": 2,
	"اختر إعدادات الساعة": 3,
	"صيغة النطق": 3,
	"نظام الساعات": 3,
	"تمثيل النطق": 3,
	"نطق الثواني": 3,
	"نطق عبارة «صفر دقيقة»": 3,
	"تجربة النطق": 3,
	"تفعيل تنبيهات الساعة التلقائية": 3,
	"إجراء تنبيه الساعة": 3,
	"التاريخ": 2,
	"التقويم الأساسي": 3,
	"تضمين معلومات التقويم العربي في معلومات اليوم": 3,
	"فتح نافذة معلومات اليوم": 3,
	"اختر التقويم المراد ضبطه": 3,
	"صيغة التاريخ": 3,
	"تصحيح التاريخ الهجري القمري": 3,
	"تنبيهات الأذكار": 2,
	"تفعيل تنبيهات الأذكار": 3,
	"أذكار الصباح": 3,
	"أذكار المساء": 3,
	"ساعة الجمعة": 3,
	"الورد اليومي": 3,
	"إجراء التنبيه": 3,
	"تفعيل الأذكار الدورية": 3,
	"خارطة الاختصارات": 1,
	"تلقي ملاحظاتكم": 1,
	"سجل التغييرات": 1,
	"الإصدار 4.0.0": 2,
	"الإصدار 3.2": 2,
	"الإصدار 3.1": 2,
	"الإصدار 3.0": 2,
	"الإصدار 2.1": 2,
	"الإصدار 1.3": 2,
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
	text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
	text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
	text = re.sub(r"\[([^]]+)]\(((?:https?://|mailto:)[^)]+)\)", r'<a href="\2">\1</a>', text)
	text = text.replace("&lt;br&gt;", "<br>")
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
	# The approved Word guide has already supplied explicit semantic structure.
	# Do not apply legacy heading inference or rewrite its text.
	arabic_markdown = arabic_source
	english_markdown = EN_SOURCE.read_text(encoding="utf-8")
	AR_MARKDOWN.parent.mkdir(parents=True, exist_ok=True)
	AR_MARKDOWN.write_text(arabic_markdown, encoding="utf-8", newline="\n")
	(AR_MARKDOWN.parent / "readme.html").write_text(
		markdown_to_html(arabic_markdown, lang="ar", direction="rtl", title="دليل استخدام أوقاتي 8.2.3"),
		encoding="utf-8",
		newline="\n",
	)
	EN_MARKDOWN.write_text(english_markdown, encoding="utf-8", newline="\n")
	(EN_MARKDOWN.parent / "readme.html").write_text(
		markdown_to_html(english_markdown, lang="en", direction="ltr", title="Awqati 8.2.3 user guide"),
		encoding="utf-8",
		newline="\n",
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
