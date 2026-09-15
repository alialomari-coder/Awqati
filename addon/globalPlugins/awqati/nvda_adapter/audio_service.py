"""NVDA WAV playback adapter with validated streaming on one worker."""

from __future__ import annotations

from pathlib import Path
import threading
import wave
from typing import Callable

from ..application.alert_presenter import OutputResult
from ..domain import AlertEvent, AlertEventType
from ..infrastructure.audio_files import SoundFileService, validate_wav


class AudioService:
	"""Resolve and stream one WAV at a time without blocking NVDA's main thread."""

	def __init__(self, files: SoundFileService, *, player_factory=None,
			dispatch: Callable[..., None] | None = None, frames_per_chunk: int = 32768,
			diagnostic: Callable[[Exception], None] | None = None) -> None:
		self.files = files
		self._player_factory = player_factory
		self._dispatch = dispatch
		self._frames_per_chunk = frames_per_chunk
		self._diagnostic = diagnostic or self._default_diagnostic
		self._lock = threading.RLock()
		self._cancelled = threading.Event()
		self._player = None
		self._generation = 0
		self._busy = False

	@property
	def busy(self) -> bool:
		with self._lock:
			return self._busy

	def play(self, event: AlertEvent, on_started: Callable[[], None],
			on_finished: Callable[[OutputResult], None]) -> bool:
		def resolve_event() -> Path:
			resolved = self.files.resolve(event)
			if resolved is None:
				raise FileNotFoundError("no valid custom or bundled sound is available")
			return resolved.path
		return self._start(resolve_event, on_started, on_finished)

	def play_preview(self, event_type: AlertEventType, custom_path: Path | None,
			on_started: Callable[[], None], on_finished: Callable[[OutputResult], None]) -> bool:
		def resolve_preview() -> Path:
			if custom_path is not None:
				try:
					validate_wav(custom_path)
					return custom_path
				except (OSError, ValueError):
					pass
			default = self.files.default_path(event_type)
			if default is None:
				raise FileNotFoundError("no valid preview sound is available")
			return default
		return self._start(resolve_preview, on_started, on_finished)

	def play_path(self, path: Path, on_started: Callable[[], None],
			on_finished: Callable[[OutputResult], None]) -> bool:
		return self._start(lambda: Path(path), on_started, on_finished)

	def _start(self, resolver, on_started, on_finished) -> bool:
		with self._lock:
			if self._busy:
				return False
			self._busy = True
			self._generation += 1
			generation = self._generation
			self._cancelled = threading.Event()
		try:
			threading.Thread(target=self._play_worker,
				args=(resolver, generation, on_started, on_finished),
				name="AwqatiAudioPlayback", daemon=True).start()
		except Exception:
			with self._lock:
				self._busy = False
			raise
		return True

	def _play_worker(self, resolver, generation: int, on_started, on_finished) -> None:
		started = completed = False
		error: Exception | None = None
		player = None
		try:
			path = resolver()
			validate_wav(path)
			with wave.open(str(path), "rb") as source:
				player = self._make_player(source)
				with self._lock:
					if generation != self._generation or self._cancelled.is_set():
						return
					self._player = player
				while not self._cancelled.is_set():
					data = source.readframes(self._frames_per_chunk)
					if not data:
						break
					player.feed(data)
					if not started:
						started = True
						self._call(on_started)
				if not self._cancelled.is_set():
					player.idle()
					completed = True
		except Exception as caught:
			error = caught
			self._diagnostic(caught)
		finally:
			cancelled = self._cancelled.is_set()
			if player is not None:
				try: player.close()
				except Exception: pass
			with self._lock:
				if generation != self._generation:
					return
				self._player = None
				self._busy = False
			self._call(on_finished, OutputResult(started, completed, cancelled, error))

	def _make_player(self, source):
		if self._player_factory is not None:
			return self._player_factory(source.getnchannels(), source.getframerate(), source.getsampwidth() * 8)
		import config
		import nvwave
		return nvwave.WavePlayer(channels=source.getnchannels(), samplesPerSec=source.getframerate(),
			bitsPerSample=source.getsampwidth() * 8, outputDevice=config.conf["audio"]["outputDevice"],
			wantDucking=False, purpose=nvwave.AudioPurpose.SOUNDS)

	def _call(self, callback, *args) -> None:
		if self._dispatch is not None:
			self._dispatch(callback, *args)
			return
		try:
			import wx
			wx.CallAfter(callback, *args)
		except ImportError:
			callback(*args)

	@staticmethod
	def _default_diagnostic(error: Exception) -> None:
		try:
			from logHandler import log
			log.debugWarning(f"Awqati audio output unavailable: {error}")
		except ImportError:
			pass

	def cancel(self) -> None:
		with self._lock:
			self._cancelled.set()
			player = self._player
		if player is not None:
			try: player.stop()
			except Exception: pass

	close = cancel
