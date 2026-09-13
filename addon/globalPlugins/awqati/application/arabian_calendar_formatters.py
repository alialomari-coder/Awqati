"""Arabic presentation boundary for Arabian calendar readings."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain import ArabianCalendarReading, MonthDay, SuhailCycleType


@runtime_checkable
class ArabianCalendarFormatter(Protocol):
	def format_short(self, reading: ArabianCalendarReading) -> str:
		...

	def format_detailed(self, reading: ArabianCalendarReading) -> str:
		...


_ORDINALS = {
	1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع", 5: "الخامس",
	6: "السادس", 7: "السابع", 8: "الثامن", 9: "التاسع", 10: "العاشر",
	11: "الحادي عشر", 12: "الثاني عشر", 13: "الثالث عشر", 14: "الرابع عشر",
}
_MONTHS = {
	1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
	7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


class ArabicArabianCalendarFormatter:
	language = "ar"

	def format_short(self, reading: ArabianCalendarReading) -> str:
		season = reading.season.name
		if reading.folk_subdivision:
			season += f": {reading.folk_subdivision}"
		text = (
			f"سنة سهيل: اليوم {reading.suhail_day}. الطالع: {reading.talaa.name}، "
			f"اليوم {_ORDINALS[reading.talaa_day]} منه. وهو من موسم {season}."
		)
		if reading.short_saying:
			text += f" ومن المأثور فيه: {reading.short_saying.text}"
		return text

	def format_detailed(self, reading: ArabianCalendarReading) -> str:
		cycle = "كبيسة" if reading.cycle_type is SuhailCycleType.LEAP else "بسيطة"
		sections = [(
			f"وفي التقويم العربي: اليوم هو اليوم {reading.suhail_day} من سنة سهيل. "
			f"وهذه السنة {cycle}، عدد أيامها {reading.cycle_length}، "
			f"وقد بقي منها {reading.days_remaining} يومًا."
		)]
		talaa = reading.talaa
		sections.append("\n".join((
			f"الطالع الحالي: {talaa.name}.",
			f"الفترة: من {_month_day(talaa.start)} إلى {_month_day(talaa.end)}.",
			f"اليوم {reading.talaa_day} من {reading.talaa_length}.",
		)))
		season_lines = [f"الموسم الجامع: {reading.season.name}."]
		if reading.folk_subdivision:
			season_lines.append(f"التقسيم الشعبي: {reading.folk_subdivision}.")
		season_lines.extend(reading.season.notes)
		sections.append("\n".join(season_lines))
		mansion = []
		if reading.mansion and reading.mansion.description:
			mansion.append(f"المنزلة: {reading.mansion.description}")
		if reading.mansion and reading.mansion.name_origin:
			mansion.append(f"أصل الاسم: {reading.mansion.name_origin}")
		if mansion:
			sections.append("\n".join(mansion))
		if talaa.heritage_notes:
			sections.append("المادة التراثية:\n" + "\n".join(talaa.heritage_notes))
		if reading.naw:
			sections.append("النوء القديم:\n" + reading.naw.description)
		if talaa.sayings:
			sections.append("الأقوال المأثورة:\n" + "\n".join(s.text for s in talaa.sayings))
		if reading.overlapping_periods:
			lines = []
			for period in reading.overlapping_periods:
				lines.append(
					f"{period.name}: من {_month_day(period.start)} إلى {_month_day(period.end)}. "
					f"{period.description}"
				)
			sections.append("الفترات المتداخلة:\n" + "\n".join(lines))
		if reading.start_events:
			sections.append("أحداث البداية:\n" + "\n".join(e.text for e in reading.start_events))
		return "\n\n".join(sections)


def _month_day(value: MonthDay) -> str:
	return f"{value.day} {_MONTHS[value.month]}"
