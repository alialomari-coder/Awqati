"""Create only a project-local NVDA portable runtime on a private desktop."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from run_on_this_day_nvda_probe import private_process, personal_hashes, nvda_pids


def main():
	package = ROOT / 'development_baseline/nvda_2026.1.exe'
	assert hashlib.sha256(package.read_bytes()).hexdigest() == '8ddb7dabce62640b465ed2b7bfa63d9ac21f9901ec816bbc1a1f3678bf92be28'
	target = ROOT / 'development_baseline/nvda-2026.1-portable'
	assert not target.exists(), 'Refusing to overwrite an existing portable runtime'
	profile = ROOT / 'development_baseline/nvda-2026.1-prepare-profile'
	profile.mkdir(exist_ok=True)
	initial, owners = personal_hashes(), nvda_pids()
	user = ctypes.WinDLL('user32', use_last_error=True)
	user.CreateDesktopW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
	user.CreateDesktopW.restype = wintypes.HANDLE
	user.CloseDesktop.argtypes = [wintypes.HANDLE]
	name = 'AwqatiTask3_Prepare2026_1'
	desktop = user.CreateDesktopW(name, None, None, 0, 0x1ff, None)
	if not desktop:
		raise ctypes.WinError(ctypes.get_last_error())
	try:
		code = private_process([str(package), '--minimal', '--no-sr-flag', '--create-portable-silent',
			'--portable-path', str(target), '--config-path', str(profile), '--log-file', str(profile / 'prepare.log')], 'winsta0\\' + name)
		result = dict(exitCode=code, portableExists=(target / 'nvda_noUIAccess.exe').is_file(),
			personalConfigurationUnchanged=initial == personal_hashes(), personalProcessPreserved=owners <= nvda_pids(),
			installerSha256=hashlib.sha256(package.read_bytes()).hexdigest())
		(ROOT / 'docs/historical_converter_task6/prepare_nvda2026_1.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
		print(result)
		assert code == 0 and result['portableExists'] and result['personalConfigurationUnchanged'] and result['personalProcessPreserved']
	finally:
		user.CloseDesktop(desktop)


if __name__ == '__main__':
	main()
