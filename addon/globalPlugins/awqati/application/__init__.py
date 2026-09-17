"""Application-layer contracts and orchestration boundaries."""

from .calendar_formatters import ArabicDateFormatter, DateFormatter, EnglishDateFormatter
from .calendar_service import CalendarService
from .astronomy_service import AstronomyService
from .arabian_calendar_formatters import (
	ArabianCalendarFormatter,
	ArabicArabianCalendarFormatter,
	EnglishArabianCalendarFormatter,
)
from .arabian_calendar_service import ArabianCalendarService
from .daily_info_service import DailyInfoService
from .daily_info_formatters import ArabicDailyInfoFormatter, DailyInfoFormatter, EnglishDailyInfoFormatter

from .clock_formatters import (
	ArabicWordClockFormatter,
	ClockFormatter,
	EnglishWordClockFormatter,
	NumericClockFormatter,
)
from .clock_service import ClockService, PrayerRequestFactory
from .prayer_alert_producer import PrayerAlertProducer
from .clock_alert_producer import ClockAlertProducer
from .prayer_clock_rebuild_source import PrayerClockRebuildSource
from .adhkar_alert_producer import AdhkarAlertProducer
from .daily_wird_producer import DailyWirdProducer
from .recurring_dhikr_producer import RecurringDhikrProducer
from .alert_formatters import format_prayer_alert, format_clock_alert, format_adhkar_alert
from .islamic_terms import GLOSSARY_IDENTITIES, TermKind, normalize_language, source_message, term_kind, term_text
from .alert_presenter import AlertPresenter, AudioOutput, OutputResult, SpeechOutput, format_alert_message
from .events import EventDispatcher
from .alert_scheduler import (
	AlertCoordinator, AlertScheduler, GRACE_PERIODS, PresentationLease,
	priority_for, resolve_civil_time, timer_delivery_instant,
)
from .general_policy import (
	AlertPolicyDecision,
	AutomaticAlertKind,
	LOCATION_REQUIRED_MESSAGE,
	automatic_alert_policy,
	first_run_location_required,
	is_quiet_time,
	location_requirement_message,
	manual_commands_allowed,
)
from .location_service import LocationNotFoundError, LocationService
from .location_setup import CustomLocationValidationError, LocationSelectionResult, LocationSetupService
from .settings_service import ClosedSettingsDraftError, SettingsDraft, SettingsService
from .operation import CancellationToken, OperationCancelled
from .data_update_service import (
	DataPackageManifest, DataUpdateError, DataUpdateResult, DataUpdateService,
	SUPPORTED_DATA_PACKAGES, UpdateChannelUnavailable,
)
from .online_prayer_verifier import (
	OnlinePrayerRequest, OnlinePrayerVerificationError, OnlinePrayerVerifier,
	PrayerTimeDifference, PrayerVerificationResult,
)
from .diagnostics_service import DiagnosticsService, DiagnosticsSnapshot
from .qibla_formatters import ArabicQiblaFormatter, EnglishQiblaFormatter, QiblaFormatter
from .qibla_service import QiblaService
from .prayer_service import PrayerService
from .prayer_state import (
	DEFAULT_CURRENT_PRAYER_DURATION_MINUTES,
	DEFAULT_EVENT_PRE_ALERT_MINUTES,
	DEFAULT_IQAMA_ALERT_BEFORE_MINUTES,
	DEFAULT_IQAMA_DELAYS_MINUTES,
	MAX_CURRENT_PRAYER_DURATION_MINUTES,
	CurrentPrayer,
	EventPreAlertSettings,
	IqamaRule,
	IqamaSettings,
	PrayerStatePriority,
	PrayerStateService,
	PrayerTimelineState,
	WaitingWindow,
)
from .ports import (
	ArabianCalendarRepository,
	CalendarProvider,
	CalculationMethodProvider,
	CountryInfo,
	CoordinateProvider,
	LocationDetectionError,
	LocationMatch,
	LocationRepository,
	NowProvider,
	SettingsRepository,
	TimezoneProvider,
)

__all__ = [
	"AdhkarAlertProducer",
	"DailyWirdProducer",
	"RecurringDhikrProducer",
	"PrayerAlertProducer",
	"ClockAlertProducer",
	"PrayerClockRebuildSource",
	"format_prayer_alert",
	"format_clock_alert",
	"format_adhkar_alert",
	"GLOSSARY_IDENTITIES",
	"TermKind",
	"normalize_language",
	"source_message",
	"term_kind",
	"term_text",
	"AlertPresenter",
	"AudioOutput",
	"OutputResult",
	"SpeechOutput",
	"format_alert_message",
	"ArabianCalendarFormatter",
	"ArabianCalendarRepository",
	"ArabianCalendarService",
	"ArabicArabianCalendarFormatter",
	"EnglishArabianCalendarFormatter",
	"ArabicDateFormatter",
	"ArabicQiblaFormatter",
	"AstronomyService",
	"CalculationMethodProvider",
	"ArabicWordClockFormatter",
	"AlertPolicyDecision",
	"AutomaticAlertKind",
	"ClockFormatter",
	"ClockService",
	"ClosedSettingsDraftError",
	"CalendarProvider",
	"CalendarService",
	"DateFormatter",
	"DailyInfoService",
	"DailyInfoFormatter",
	"ArabicDailyInfoFormatter",
	"EnglishDailyInfoFormatter",
	"EnglishDateFormatter",
	"EnglishQiblaFormatter",
	"EnglishWordClockFormatter",
	"CountryInfo",
	"CoordinateProvider",
	"CustomLocationValidationError",
	"CurrentPrayer",
	"DEFAULT_CURRENT_PRAYER_DURATION_MINUTES",
	"DEFAULT_EVENT_PRE_ALERT_MINUTES",
	"DEFAULT_IQAMA_ALERT_BEFORE_MINUTES",
	"DEFAULT_IQAMA_DELAYS_MINUTES",
	"EventDispatcher",
	"AlertCoordinator",
	"AlertScheduler",
	"GRACE_PERIODS",
	"PresentationLease",
	"priority_for",
	"resolve_civil_time",
	"timer_delivery_instant",
	"EventPreAlertSettings",
	"IqamaRule",
	"IqamaSettings",
	"LocationDetectionError",
	"LocationMatch",
	"LocationNotFoundError",
	"LocationRepository",
	"LocationSelectionResult",
	"LocationService",
	"LocationSetupService",
	"LOCATION_REQUIRED_MESSAGE",
	"MAX_CURRENT_PRAYER_DURATION_MINUTES",
	"NowProvider",
	"NumericClockFormatter",
	"PrayerRequestFactory",
	"PrayerStatePriority",
	"PrayerStateService",
	"PrayerService",
	"PrayerTimelineState",
	"QiblaFormatter",
	"QiblaService",
	"SettingsDraft",
	"SettingsRepository",
	"SettingsService",
	"CancellationToken",
	"OperationCancelled",
	"DataPackageManifest",
	"DataUpdateError",
	"DataUpdateResult",
	"DataUpdateService",
	"SUPPORTED_DATA_PACKAGES",
	"UpdateChannelUnavailable",
	"OnlinePrayerRequest",
	"OnlinePrayerVerificationError",
	"OnlinePrayerVerifier",
	"PrayerTimeDifference",
	"PrayerVerificationResult",
	"DiagnosticsService",
	"DiagnosticsSnapshot",
	"TimezoneProvider",
	"WaitingWindow",
	"automatic_alert_policy",
	"first_run_location_required",
	"is_quiet_time",
	"location_requirement_message",
	"manual_commands_allowed",
]
