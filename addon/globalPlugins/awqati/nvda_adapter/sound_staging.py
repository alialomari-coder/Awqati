"""Transactional staging for sound files selected from the settings UI."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import threading
from typing import Iterable, Mapping
from uuid import uuid4

from ..domain import SoundReference
from ..infrastructure.audio_files import SOUND_CATEGORIES, SoundFileService, validate_wav


_COPY_CHUNK_SIZE = 1024 * 1024


class SoundPreparationCancelled(RuntimeError):
	"""The settings session closed while a sound was being prepared."""


class SoundCommit:
	"""Reversible moves performed immediately before settings persistence."""

	def __init__(self) -> None:
		self.moves: list[tuple[Path, Path]] = []
		self.created_directories: list[Path] = []


def collect_sound_reference_values(value: object) -> set[str]:
	"""Collect sound references from the language-neutral settings graph."""
	result: set[str] = set()

	def visit(item: object) -> None:
		if isinstance(item, SoundReference):
			result.add(item.value)
		elif is_dataclass(item) and not isinstance(item, type):
			for field in fields(item):
				visit(getattr(item, field.name))
		elif isinstance(item, Mapping):
			for child in item.values():
				visit(child)
		elif isinstance(item, (list, tuple, set, frozenset)):
			for child in item:
				visit(child)

	visit(value)
	return result


class SoundStagingSession:
	"""Own temporary files until the surrounding settings draft is committed."""

	def __init__(self, root: Path, file_service: SoundFileService | None = None) -> None:
		self.root = Path(root)
		self.files = file_service or SoundFileService(self.root, Path())
		self._lock = threading.RLock()
		self._io_lock = threading.Lock()
		self._closed = threading.Event()
		self._pending = 0
		self._staged: dict[str, Path] = {}
		self._staging_dir = self._new_staging_dir()

	def _new_staging_dir(self) -> Path:
		return self.root / ".settings-staging" / uuid4().hex

	@property
	def has_pending_work(self) -> bool:
		with self._lock:
			return self._pending > 0

	def begin_preparation(self) -> bool:
		with self._lock:
			if self._closed.is_set():
				return False
			self._pending += 1
			return True

	def finish_preparation(self) -> None:
		with self._lock:
			self._pending = max(0, self._pending - 1)

	def prepare(self, source: Path, category: str) -> SoundReference:
		"""Validate and stream a WAV into staging, or reference a safe in-place file."""
		if category not in SOUND_CATEGORIES:
			raise ValueError("unsupported sound category")
		validate_wav(source)
		if self._closed.is_set():
			raise SoundPreparationCancelled()
		with self._io_lock:
			if self._closed.is_set():
				raise SoundPreparationCancelled()
			if self.files.is_inside_category(source, category):
				return self.files.reference_for_existing(source)
			with self._lock:
				staging_dir = self._staging_dir / category
			staging_dir.mkdir(parents=True, exist_ok=True)
			temporary = staging_dir / f"{uuid4().hex}.wav"
			digest = hashlib.sha256()
			try:
				with Path(source).open("rb") as source_file, temporary.open("xb") as staged_file:
					while True:
						if self._closed.is_set():
							raise SoundPreparationCancelled()
						chunk = source_file.read(_COPY_CHUNK_SIZE)
						if not chunk:
							break
						digest.update(chunk)
						staged_file.write(chunk)
				managed_name = f"awqati-managed-{digest.hexdigest()[:16]}-{Path(source).stem}.wav"
				reference = SoundReference(PurePosixPath("sounds", category, managed_name).as_posix())
				final_staged = staging_dir / managed_name
				if final_staged.exists():
					temporary.unlink()
				else:
					os.replace(temporary, final_staged)
				validate_wav(final_staged)
				with self._lock:
					if self._closed.is_set():
						raise SoundPreparationCancelled()
					previous = self._staged.get(reference.value)
					self._staged[reference.value] = final_staged
				if previous is not None and previous != final_staged:
					previous.unlink(missing_ok=True)
				return reference
			finally:
				temporary.unlink(missing_ok=True)
				if self._closed.is_set():
					self._remove_tree(self._staging_dir)

	def resolve(self, reference: SoundReference) -> Path:
		with self._lock:
			staged = self._staged.get(reference.value)
		if staged is not None and staged.is_file():
			return staged
		from ..infrastructure.audio_files import safe_reference_path
		return safe_reference_path(self.root, reference.value)

	def begin_commit(self, used_references: Iterable[str]) -> SoundCommit:
		"""Move used staged files into place, retaining enough state to roll back."""
		if self.has_pending_work:
			raise RuntimeError("sound preparation is still running")
		commit = SoundCommit()
		used = set(used_references)
		with self._io_lock:
			try:
				for reference, staged in tuple(self._staged.items()):
					if reference not in used or not staged.is_file():
						continue
					target = self.root.joinpath(*PurePosixPath(reference).parts)
					if target.is_file():
						continue
					missing: list[Path] = []
					parent = target.parent
					while parent != self.root and not parent.exists():
						missing.append(parent)
						parent = parent.parent
					target.parent.mkdir(parents=True, exist_ok=True)
					commit.created_directories.extend(reversed(missing))
					os.replace(staged, target)
					commit.moves.append((staged, target))
				return commit
			except Exception:
				self._rollback_locked(commit)
				raise

	def rollback(self, commit: SoundCommit) -> None:
		with self._io_lock:
			self._rollback_locked(commit)

	def _rollback_locked(self, commit: SoundCommit) -> None:
		for staged, target in reversed(commit.moves):
			if target.is_file():
				staged.parent.mkdir(parents=True, exist_ok=True)
				os.replace(target, staged)
		for directory in reversed(commit.created_directories):
			try:
				directory.rmdir()
			except OSError:
				pass

	def complete(self, commit: SoundCommit, used_references: Iterable[str] | None = None) -> None:
		"""Accept a commit and clean unused managed copies off the UI thread."""
		del commit
		old_staging = self._rotate_staging()
		self._cleanup_later(old_staging, None if used_references is None else set(used_references))

	def discard(self) -> None:
		"""Cancel the session without making the UI wait for file deletion."""
		self._closed.set()
		old_staging = self._rotate_staging()
		self._cleanup_later(old_staging)

	def _rotate_staging(self) -> Path:
		with self._lock:
			old_staging = self._staging_dir
			self._staging_dir = self._new_staging_dir()
			self._staged = {}
			return old_staging

	def _cleanup_later(self, path: Path, used_references: set[str] | None = None) -> None:
		threading.Thread(
			target=self._cleanup_worker,
			args=(path, used_references),
			name="AwqatiSoundCleanup",
			daemon=True,
		).start()

	def _cleanup_worker(self, path: Path, used_references: set[str] | None) -> None:
		with self._io_lock:
			self._remove_tree(path)
			if used_references is not None:
				self.files.cleanup_unreferenced_managed(used_references)

	def _remove_tree(self, path: Path) -> None:
		shutil.rmtree(path, ignore_errors=True)
		try:
			path.parent.rmdir()
		except OSError:
			pass
