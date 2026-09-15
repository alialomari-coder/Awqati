"""Session recurrence on a stable elapsed-time grid, without timers or output."""

from datetime import timedelta

from ..domain import AlertEvent, AlertEventType, Instant
from ..domain.alerts import utc
from ..domain.settings import RecurringDhikrId
from .general_policy import in_scope, alert_scope_enabled


class RecurringDhikrProducer:
	"""Keep the grid separate from the enabled items assigned to its slots.

	Membership changes affect strictly future slots. The last elapsed item's
	canonical position determines the next enabled item, so disabling an item
	never consumes a slot and re-enabling inserts it in canonical order.
	All state belongs to this session; published changes arrive via the source.
	"""

	def __init__(self, settings):
		self._settings = settings
		self.reset()

	def reset(self):
		self._first = None
		self._items = ()
		self._sequence_slot = 0
		self._next_index = 0
		self._last_identity = None

	@staticmethod
	def _enabled(config):
		return tuple(identity for identity in RecurringDhikrId if config.items[identity].enabled)

	def _start(self, now, config):
		self.reset()
		self._first = utc(now) + timedelta(minutes=config.interval_minutes)
		self._items = self._enabled(config)

	def _identity_at(self, slot):
		return self._items[(slot - self._sequence_slot + self._next_index) % len(self._items)]

	def settings_changed(self, previous, current, now):
		old, new = previous.adhkar.recurring, current.adhkar.recurring
		if (previous.general.all_automatic_alerts_enabled != current.general.all_automatic_alerts_enabled
				or previous.adhkar.alerts_enabled != current.adhkar.alerts_enabled
				or old.enabled != new.enabled or old.interval_minutes != new.interval_minutes):
			if alert_scope_enabled(current, "adhkar.recurring"):
				self._start(now, new)
			else:
				self.reset()
			return
		items = self._enabled(new)
		if self._enabled(old) == items or not alert_scope_enabled(current, "adhkar.recurring"):
			return
		if self._first is None:
			# No grid has been started yet; session startup supplies its anchor.
			return
		interval = timedelta(minutes=new.interval_minutes)
		first_future = max(0, (utc(now) - self._first) // interval + 1)
		if self._items and first_future > self._sequence_slot:
			self._last_identity = self._identity_at(first_future - 1)
		self._sequence_slot = first_future
		self._items = items
		self._next_index = 0
		if items and self._last_identity is not None:
			order = tuple(RecurringDhikrId)
			previous_position = order.index(self._last_identity)
			self._next_index = next((i for i, identity in enumerate(items)
				if order.index(identity) > previous_position), 0)

	def produce(self, from_now, until, *, reason="rebuild", scope=None):
		if utc(until) <= utc(from_now):
			raise ValueError("alert window end must follow from_now")
		settings = self._settings()
		config = settings.adhkar.recurring
		if not alert_scope_enabled(settings, "adhkar.recurring"):
			return ()
		if self._first is None:
			self._start(from_now, config)
		# An empty cycle retains its grid, but has no events or separate wakeup.
		if not self._items:
			return ()
		interval = timedelta(minutes=config.interval_minutes)
		index = max(self._sequence_slot, 0, (utc(from_now) - self._first) // interval)
		when = self._first + index * interval
		if when < utc(from_now) or (reason in ("resume", "systemTimeChanged", "recurringMembershipChanged")
				and when == utc(from_now)):
			index += 1
			when += interval
		result = []
		while when < utc(until):
			identity = self._identity_at(index)
			item_scope = "adhkar.recurring." + identity.value
			if in_scope(item_scope, scope):
				output = config.items[identity].alert
				key = f"adhkar:recurring:{identity.value}:{when.isoformat()}"
				result.append(AlertEvent(key, AlertEventType.RECURRING_DHIKR, Instant(when),
					action=output.action, message_id="alert.adhkar.recurring",
					sound_ref=output.sound.value if output.sound else None,
					source="RecurringDhikrProducer", scope=item_scope,
					metadata={"dhikr_id": identity.value}))
			index += 1
			when += interval
		return tuple(result)
