from __future__ import annotations

import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))
if str(ROOT / ".build-deps") not in sys.path:
	sys.path.insert(0, str(ROOT / ".build-deps"))

from babel.messages.pofile import read_po  # noqa: E402
from awqati.domain import Instant, Location, PrayerEventName  # noqa: E402
from awqati.nvda_adapter.commands import CommandContent  # noqa: E402


class Translator:
	def __init__(self, language: str) -> None:
		self.language = language
		if language == "ar":
			with (ROOT / "addon/locale/ar/LC_MESSAGES/nvda.po").open("rb") as stream:
				self.catalog = read_po(stream, locale="ar")

	def __call__(self, message: str) -> str:
		if self.language == "en":
			return message
		translated = self.catalog.get(message)
		return translated.string if translated and translated.string else message


class CorrectiveCommandLocalizationTests(unittest.TestCase):
	def test_requested_arabic_messages_are_exact_and_english_sources_unchanged(self) -> None:
		arabic = Translator("ar")
		expected = {
			"The current prayer is {name}; it began {duration} ago.": "الصلاة الحالية هي {name}؛ وقد دخلَ وقتُها قبل {duration}.",
			"The next prayer is {name} at {time}; in {duration}.": "الصلاة القادمة هي {name} عند {time}؛ أي بعد {duration}.",
			"The next time is {name} at {time}; in {duration}.": "الوقت القادم هو {name} عند {time}؛ أي بعد {duration}.",
			"The previous prayer was {name} at {time}; {duration} ago.": "الصلاة السابقة كانت {name} عند {time}؛ أي قبل {duration}.",
			"The previous time was {name} at {time}; {duration} ago.": "الوقت السابق كان {name} عند {time}؛ أي قبل {duration}.",
			"The time for {prayer} prayer is approaching, with {duration} remaining.": "اقترب دخول وقت صلاة {prayer}، فقد بقي عليه {duration}.",
			"Sunrise is approaching, with {duration} remaining.": "اقترب وقت الشروق، فقد بقي عليه {duration}.",
			"The middle of the night is approaching, with {duration} remaining.": "اقترب وقت انتصاف الليل، فقد بقي عليه {duration}.",
			"The last third of the night is approaching, with {duration} remaining.": "اقترب دخول وقت الثلث الأخير من الليل، فقد بقي عليه {duration}.",
			"It is now time for {prayer} prayer.": "حان الآن وقت دخول صلاة {prayer}.",
			"All automatic Awqati alerts have been enabled.": "تم تفعيل جميع التنبيهات التلقائية.",
			"All automatic Awqati alerts have been disabled.": "تم تعطيل جميع التنبيهات التلقائية.",
			"No Awqati alert has been presented yet.": "لم يتم عرض أي تنبيه حتى الآن.",
			"This Awqati command is unavailable until a valid location is assigned.": "هذا الأمر غير متاح حتى يتم تعيين موقع صالح.",
			"Awqati settings could not be loaded. The existing file was not replaced.": "تعذر تحميل الإعدادات . لم يُستبدل الملف الموجود.",
			"Awqati could not save the location. Your previous settings were preserved.": "تعذر حفظ الموقع. حُفظت الإعدادات السابقة دون تغيير.",
			"Choose an allowed option.": "اختر أحد الخيارات المسموح بها.",
			"Choose a valid Awqati sound file.": "اختر ملفًا صوتيًا صالحًا.",
			"Awqati could not save the settings. Your previous applied settings were preserved.": "تعذر حفظ الإعدادات. حُفظت الإعدادات السابقة المعتمدة دون تغيير.",
			"Awqati diagnostic information has been copied to the clipboard.": "تم نسخ معلومات التشخيص إلى الحافظة.",
			"Could not copy Awqati diagnostic information to the clipboard.": "تعذر نسخ معلومات التشخيص إلى الحافظة.",
			"Awqati data updates were installed safely. Restart NVDA to use them.": "ثُبتت تحديثات البيانات بأمان. أعد تشغيل NVDA لاستخدامها.",
			"Awqati data is already up to date.": "البيانات محدثة بالفعل.",
		}
		for english, translated in expected.items():
			with self.subTest(english=english):
				self.assertEqual(english, Translator("en")(english))
				self.assertEqual(translated, arabic(english))

	@staticmethod
	def event(name, hour):
		return SimpleNamespace(
			name=name,
			kind=SimpleNamespace(value="prayer" if name is PrayerEventName.DHUHR else "time"),
			occurs_at=datetime(2026, 9, 16, hour, 0, tzinfo=timezone.utc),
		)

	def content_with_state(self):
		content = object.__new__(CommandContent)
		state = SimpleNamespace(
			as_of=Instant(datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)),
			priority=SimpleNamespace(),
			next_event=self.event(PrayerEventName.DHUHR, 11),
			previous_event=self.event(PrayerEventName.SUNRISE, 5),
		)
		content._state = lambda: state
		return content

	def test_f11_current_and_previous_templates_are_fully_arabic_or_english(self) -> None:
		content = self.content_with_state()
		arabic = Translator("ar")
		current_ar = content.current_details(arabic)
		previous_ar = content.previous_details(arabic)
		self.assertIn("الصلاة القادمة هي الظهر", current_ar)
		self.assertIn("الوقت السابق كان الشروق", previous_ar)
		for forbidden in ("The next", "The previous", "minutes", "ago"):
			self.assertNotIn(forbidden, current_ar + previous_ar)
		current_en = content.current_details(Translator("en"))
		previous_en = content.previous_details(Translator("en"))
		self.assertIn("The next prayer is Dhuhr", current_en)
		self.assertIn("The previous time was Sunrise", previous_en)

	def test_daily_prayer_times_heading_names_and_templates_follow_language(self) -> None:
		content = object.__new__(CommandContent)
		location = Location("riyadh", "Riyadh", 24.7136, 46.6753, "UTC")
		content._location = lambda: location
		content.zones = SimpleNamespace(get_timezone=lambda _name: timezone.utc)
		content.now = SimpleNamespace(now=lambda: Instant(datetime(2026, 9, 16, 10, tzinfo=timezone.utc)))
		content._request = lambda day: day
		def prayer_times(day):
			base = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
			return SimpleNamespace(
				fajr=base + timedelta(hours=5), sunrise=base + timedelta(hours=6),
				dhuhr=base + timedelta(hours=12), asr=base + timedelta(hours=15),
				maghrib=base + timedelta(hours=18), isha=base + timedelta(hours=19), metadata=None,
			)
		content.prayers = SimpleNamespace(calculate=prayer_times)
		arabic = content.daily_prayer_times(Translator("ar"))
		english = content.daily_prayer_times(Translator("en"))
		self.assertTrue(arabic.startswith("مواقيت اليوم:"))
		self.assertIn("الفجر، الساعة 05:00", arabic)
		self.assertNotIn("Today's prayer times", arabic)
		self.assertTrue(english.startswith("Today's prayer times:"))
		self.assertIn("Fajr: 05:00", english)

	def test_alert_status_is_fully_localized_and_does_not_repeat_product_name(self) -> None:
		values = SimpleNamespace(
			general=SimpleNamespace(all_automatic_alerts_enabled=True, quiet_hours=SimpleNamespace(enabled=False)),
			prayer=SimpleNamespace(alerts_enabled=True),
			clock=SimpleNamespace(automatic_alert_enabled=False),
			adhkar=SimpleNamespace(alerts_enabled=True, recurring=SimpleNamespace(enabled=False)),
		)
		content = object.__new__(CommandContent)
		content._settings = lambda: values
		arabic = content.alert_status(Translator("ar"))
		english = content.alert_status(Translator("en"))
		self.assertTrue(arabic.startswith("حالة التنبيهات:"))
		self.assertNotIn("Awqati", arabic)
		self.assertNotIn("enabled", arabic)
		self.assertNotIn("disabled", arabic)
		self.assertTrue(english.startswith("Alert status:"))
		self.assertIn("enabled", english)
		self.assertIn("disabled", english)


class InputGestureDescriptionTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.plugin = ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py"
		cls.tree = ast.parse(cls.plugin.read_text(encoding="utf-8"))
		cls.arabic = Translator("ar")

	def descriptions(self):
		result = {}
		for node in self.tree.body:
			if not isinstance(node, ast.ClassDef) or node.name != "GlobalPlugin":
				continue
			for method in node.body:
				if not isinstance(method, ast.FunctionDef) or not method.name.startswith("script_"):
					continue
				decorator = next((item for item in method.decorator_list if isinstance(item, ast.Call)), None)
				if decorator is None:
					continue
				description = next(keyword.value for keyword in decorator.keywords if keyword.arg == "description")
				message = description.args[0].value
				result[method.name] = (message, self.arabic(message))
		return result

	def test_all_twenty_one_visible_commands_have_direct_english_and_arabic_descriptions(self) -> None:
		descriptions = self.descriptions()
		self.assertEqual(21, len(descriptions))
		self.assertEqual(21, len({english for english, _arabic in descriptions.values()}))
		for method, (english, arabic) in descriptions.items():
			with self.subTest(method=method):
				self.assertTrue(english.endswith("."))
				self.assertTrue(arabic.endswith("."))
				self.assertNotEqual(english, arabic)
				self.assertNotIn("في أوقاتي", arabic)
				self.assertNotIn("غير معين", arabic)

	def test_owner_approved_arabic_descriptions_are_exact(self) -> None:
		descriptions = self.descriptions()
		expected = {
			"script_openSettings": "فتح إعدادات أوقاتي.",
			"script_prayerInfo": "بالضغط عليه مرة واحدة يعلن عن تفاصيل الوقت الحالي، وبالضغط عليه مرتين يعلن عن الوقت السابق، وبالضغط عليه ثلاث مرات يعلن عن مواقيت اليوم.",
			"script_dailyInformation": "بالضغط عليه مرة واحدة يعلن عن معلومات اليوم الفلكية، وبالضغط عليه مرتين يعلن عن معلومات اليوم في التقويم العربي، وبالضغط عليه ثلاث مرات يفتح نافذة معلومات اليوم.",
			"script_prayerVerification": "بالضغط عليه مرة واحدة يتحقق من مواقيت اليوم عبر الإنترنت، وبالضغط عليه مرتين يفتح نافذة مواقيت اليوم.",
		}
		for method, value in expected.items():
			self.assertEqual(value, descriptions[method][1])


if __name__ == "__main__":
	unittest.main()
