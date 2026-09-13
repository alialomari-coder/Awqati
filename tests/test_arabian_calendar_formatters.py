from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import ArabianCalendarService, ArabicArabianCalendarFormatter  # noqa: E402
from awqati.infrastructure import BundledArabianCalendarRepository  # noqa: E402


SAAD_BULA = "«إذا طلع سعد بلع، اقتحم الربع، ولحق الهبع، وصيد المرع، وصار في الأرض لمع.»"


class ArabianCalendarFormatterTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.service = ArabianCalendarService(BundledArabianCalendarRepository())
		cls.formatter = ArabicArabianCalendarFormatter()

	def test_short_saad_bula_saying_appears_only_on_february_23(self) -> None:
		first = self.formatter.format_short(self.service.read_date(date(2024, 2, 23)))
		later = self.formatter.format_short(self.service.read_date(date(2024, 2, 27)))
		self.assertIn(SAAD_BULA, first)
		self.assertNotIn(SAAD_BULA, later)
		self.assertEqual(later, "سنة سهيل: اليوم 188. الطالع: سعد بلع، اليوم الخامس منه. وهو من موسم العقارب: عقرب الدم.")
		self.assertNotIn("من 14", later)
		self.assertNotIn("، واليوم", later)

	def test_detailed_february_27_leap_content_is_complete(self) -> None:
		text = self.formatter.format_detailed(self.service.read_date(date(2024, 2, 27)))
		self.assertIn("وفي التقويم العربي: اليوم هو اليوم 188 من سنة سهيل. وهذه السنة كبيسة، عدد أيامها 366، وقد بقي منها 178 يومًا.", text)
		self.assertIn("الفترة: من 23 فبراير إلى 7 مارس.", text)
		self.assertIn("اليوم 5 من 14.", text)
		self.assertIn("المنزلة:", text)
		self.assertIn("المادة التراثية:", text)
		self.assertIn("النوء القديم:", text)
		self.assertIn("التقسيم الشعبي: عقرب الدم.", text)
		self.assertIn(SAAD_BULA, text)
		self.assertNotIn("sourceRefs", text)
		self.assertNotIn("MAIN_REF", text)

	def test_august_24_start_event_occurs_once(self) -> None:
		start = self.formatter.format_detailed(self.service.read_date(date(2024, 8, 24)))
		next_day = self.formatter.format_detailed(self.service.read_date(date(2024, 8, 25)))
		self.assertIn("أحداث البداية:", start)
		self.assertIn("أول أيام سنة سهيل", start)
		self.assertNotIn("أحداث البداية:", next_day)
		self.assertNotIn("أول أيام سنة سهيل", next_day)


if __name__ == "__main__":
	unittest.main()
