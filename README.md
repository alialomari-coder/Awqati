# Awqati

Awqati is an accessible add-on for the NVDA screen reader. It provides offline prayer times, Zawali and Ghurubi clocks, five calendars, Qibla direction, daily astronomical and Arabian-calendar information, and configurable alerts for prayer times, the clock, adhkar, and the daily Wird.

The supported user-interface and documentation languages for version 4.0.0 are Arabic and English. The interface is designed for full keyboard use with NVDA, including right-to-left Arabic and left-to-right English layouts.

## Requirements

- NVDA 2026.1.0 or later.
- Latest stable version tested: NVDA 2026.2.0.
- Windows supported by the corresponding NVDA release.

Core calculations and bundled data work without an Internet connection. Online prayer-time verification and data-update checks are optional and run only after an explicit user action.

## Documentation

- Arabic user guide: `addon/doc/ar/readme.md`
- English user guide: `addon/doc/en/readme.md`
- Data sources and attribution: `DATA_SOURCES.md`
- Developer guide: `DEVELOPMENT_GUIDE.md`

## Building and testing

Use Python 3.10 or later. Install the pinned build-only dependencies into `.build-deps`, then run the unified project gate:

```powershell
python -m pip install --requirement requirements-build.txt --target .build-deps
python tools/build_release_docs.py
python tools/run_checks.py
```

The package is written to `dist/`. Build dependencies and generated `build/` and `dist/` files are not bundled as source.

## Project links

- Source and project home: https://github.com/alialomari-coder/Awqati
- Manual data-update repository: https://github.com/alialomari-coder/awqati-data

The data repository is used only for optional manual data updates; it is not the add-on's source repository or homepage.

## License

Awqati is licensed under GNU GPL-2.0-or-later. See `COPYING.txt` for the complete GNU GPL version 2 text and `DATA_SOURCES.md` for third-party data notices.
