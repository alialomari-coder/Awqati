"""Validated WAV storage and resolution outside the NVDA-specific adapter."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import struct
import wave

from ..domain import AlertEvent, AlertEventType, SoundReference


SOUND_CATEGORIES = frozenset({"alerts", "clock", "adhkar"})
LEGACY_SOUND_CATEGORIES = frozenset({"adhan"})
COPY_CHUNK_SIZE = 1024 * 1024


class InvalidWaveFile(ValueError):
	"""The selected file is not a complete supported PCM WAV file."""


@dataclass(frozen=True, slots=True)
class WaveInfo:
	channels: int
	sample_width: int
	frame_rate: int
	frame_count: int


@dataclass(frozen=True, slots=True)
class ResolvedSound:
	path: Path
	source: str


def validate_wav(path: Path) -> WaveInfo:
	"""Validate headers and declared chunk bounds without reading audio payloads."""
	path = Path(path)
	if path.suffix.casefold() != ".wav":
		raise InvalidWaveFile("only WAV sound files are supported")
	try:
		size = path.stat().st_size
		with path.open("rb") as stream:
			header = stream.read(12)
			if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
				raise InvalidWaveFile("invalid RIFF/WAVE header")
			declared_size = struct.unpack("<I", header[4:8])[0] + 8
			if declared_size > size:
				raise InvalidWaveFile("truncated RIFF container")
			found_format = found_data = False
			position = 12
			while position + 8 <= declared_size:
				stream.seek(position)
				chunk_header = stream.read(8)
				if len(chunk_header) != 8:
					raise InvalidWaveFile("truncated WAV chunk header")
				chunk_id, chunk_size = chunk_header[:4], struct.unpack("<I", chunk_header[4:])[0]
				chunk_end = position + 8 + chunk_size
				if chunk_end > size or chunk_end > declared_size:
					raise InvalidWaveFile("truncated WAV chunk")
				found_format |= chunk_id == b"fmt "
				found_data |= chunk_id == b"data" and chunk_size > 0
				position = chunk_end + (chunk_size & 1)
			if not found_format or not found_data:
				raise InvalidWaveFile("WAV requires format and non-empty data chunks")
		with wave.open(str(path), "rb") as source:
			info = WaveInfo(source.getnchannels(), source.getsampwidth(),
				source.getframerate(), source.getnframes())
	except InvalidWaveFile:
		raise
	except (OSError, EOFError, wave.Error, struct.error) as error:
		raise InvalidWaveFile("unreadable WAV file") from error
	if info.channels not in (1, 2):
		raise InvalidWaveFile("only mono and stereo WAV files are supported")
	if info.sample_width not in (1, 2, 3, 4) or info.frame_rate <= 0 or info.frame_count <= 0:
		raise InvalidWaveFile("invalid PCM WAV parameters")
	return info


def safe_reference_path(root: Path, reference: str, *, allow_legacy: bool = True) -> Path:
	"""Resolve a persisted POSIX reference while preventing root escape."""
	if not isinstance(reference, str) or "\\" in reference:
		raise ValueError("invalid sound reference")
	parts = PurePosixPath(reference).parts
	allowed = SOUND_CATEGORIES | (LEGACY_SOUND_CATEGORIES if allow_legacy else frozenset())
	if len(parts) < 3 or parts[0] != "sounds" or parts[1] not in allowed:
		raise ValueError("unsupported sound reference")
	if any(part in ("", ".", "..") or ":" in part for part in parts):
		raise ValueError("unsafe sound reference")
	root = Path(root).resolve()
	path = root.joinpath(*parts).resolve()
	try:
		path.relative_to(root)
	except ValueError as error:
		raise ValueError("sound reference escapes Awqati data") from error
	return path


class SoundFileService:
	"""Own sound directories, validation, defaults, and safe managed cleanup."""

	def __init__(self, user_data_root: Path, addon_root: Path) -> None:
		self.user_data_root = Path(user_data_root)
		self.addon_root = Path(addon_root)

	@property
	def sound_root(self) -> Path:
		return self.user_data_root / "sounds"

	def ensure_sound_directories(self) -> Path:
		self.sound_root.mkdir(parents=True, exist_ok=True)
		for category in sorted(SOUND_CATEGORIES):
			(self.sound_root / category).mkdir(exist_ok=True)
		return self.sound_root

	def custom_path(self, reference: str) -> Path | None:
		try:
			path = safe_reference_path(self.user_data_root, reference)
			validate_wav(path)
		except (OSError, ValueError):
			return None
		return path

	def default_path(self, event_type: AlertEventType) -> Path | None:
		if event_type is not AlertEventType.CLOCK:
			return None
		path = self.addon_root / "sounds" / "clock" / "clock.wav"
		try:
			validate_wav(path)
		except (OSError, ValueError):
			return None
		return path

	def resolve(self, event: AlertEvent) -> ResolvedSound | None:
		if event.sound_ref:
			custom = self.custom_path(event.sound_ref)
			if custom is not None:
				return ResolvedSound(custom, "custom")
		default = self.default_path(event.event_type)
		return ResolvedSound(default, "default") if default is not None else None

	def cleanup_unreferenced_managed(self, used_references: set[str]) -> None:
		"""Delete only files bearing Awqati's explicit managed-copy prefix."""
		used: set[Path] = set()
		for reference in used_references:
			try:
				used.add(safe_reference_path(self.user_data_root, reference))
			except ValueError:
				continue
		for category in SOUND_CATEGORIES:
			directory = self.sound_root / category
			if not directory.is_dir():
				continue
			for path in directory.glob("awqati-managed-*.wav"):
				if path.resolve() not in used:
					try:
						path.unlink()
					except OSError:
						pass

	def is_inside_category(self, path: Path, category: str) -> bool:
		try:
			Path(path).resolve().relative_to((self.sound_root / category).resolve())
			return True
		except ValueError:
			return False

	def reference_for_existing(self, path: Path) -> SoundReference:
		relative = Path(path).resolve().relative_to(self.user_data_root.resolve())
		return SoundReference(PurePosixPath(*relative.parts).as_posix())


def atomic_copy(source: Path, target: Path) -> None:
	"""Stream to a sibling temporary file, then atomically replace the target."""
	temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
	try:
		with Path(source).open("rb") as source_file, temporary.open("xb") as target_file:
			while chunk := source_file.read(COPY_CHUNK_SIZE):
				target_file.write(chunk)
			target_file.flush()
			os.fsync(target_file.fileno())
		os.replace(temporary, target)
	finally:
		temporary.unlink(missing_ok=True)
