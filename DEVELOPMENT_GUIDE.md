# Developing Awqati

The current stable version is **8.2.1**, on `master`. It requires NVDA 2026.1 and declares testing through NVDA 2026.3.1. English and Arabic are supported. Read [CONTRIBUTING.md](CONTRIBUTING.md) and [TRANSLATING.md](TRANSLATING.md) before submitting a change.

## Repository layout

- `addon/globalPlugins/awqati/`: domain logic, application services, infrastructure, NVDA adapter, bundled data, and resources.
- `addon/locale/ar/LC_MESSAGES/`: main and converter gettext catalogs.
- `addon/doc/ar/` and `addon/doc/en/`: complete user guides and HTML copies.
- `docs/دليل_أوقاتي_العربي_المعتمد.md`: approved Arabic documentation source.
- `tests/`: automated tests, support code, and synthetic or public-data fixtures.
- `tools/`: build tools, data preparation tools, and relevant test runners.
- `data_sources/`: source data and approved audio needed for reproducibility.
- `buildVars.py`, `manifest.ini.tpl`, `manifest-translated.ini.tpl`, and `sconstruct`: release metadata and package construction.

## Set up a development environment

Use Python 3.13 for the development checks, with NVDA available separately for integration testing. These commands install the pinned build dependencies in a project-local folder:

```powershell
python -m pip install --requirement requirements-build.txt --target .build-deps
```

Do this in a development checkout. Do not commit installed dependencies, virtual environments, local NVDA profiles, generated packages, logs, credentials, or personal backups.

## Build and check future changes

The published 8.2.1 package is owner-approved and must not be rebuilt or replaced as part of publication. The following commands are for a separate development checkout and future reviewed changes. Building creates or overwrites the package named by `buildVars.py` in `dist/`.

To regenerate the guides after an approved documentation edit:

```powershell
python -B tools/build_release_docs.py
```

To build a development package:

```powershell
python -B tools/run_scons.py
```

The custom SCons entry point copies the source and notices, generates the manifest, validates both Arabic gettext domains, compiles catalogs, and writes the `.nvda-addon` ZIP. Its default action always builds; it does not provide the AddonTemplate `scons pot` target. For extraction without packaging, use [TRANSLATING.md](TRANSLATING.md).

For future code changes, run the relevant tests first. The complete existing check runner is:

```powershell
python -B tools/run_checks.py
```

That runner cleans generated outputs, rebuilds the package, and discovers the test suite. Use it only in a development checkout. Some historical integration and acceptance tools require an isolated NVDA installation, earlier packages, or retained local evidence. Those artifacts are intentionally not part of the public source distribution. Their absence is not an instruction to reconstruct the owner's profiles or publish local receipts. Test fixtures and scientific reference inputs needed by the ordinary source tests are retained.

## Design requirements

Keep domain and application code independent of NVDA and wxPython. Put operating-system, network, and NVDA integration at the appropriate boundaries. Avoid slow work on NVDA's main thread. Preserve stored settings, accessible names, keyboard operation, focus order and restoration, translated messages, and the distinction between scientific astronomy and the traditional Arabian calendar.

Published binaries must be tied to a reviewed source commit and release tag. Keep the previous release and Git history. Report actual checks and their limits; automated interface probes do not establish human listening acceptance.

## Historical record

The [change history](changelog.md) preserves earlier development and release milestones. Earlier committed versions of this guide remain in Git history. Local administrative reports, build receipts, private profiles, and cloud synchronization tools are not required to build the add-on and are excluded from the publication snapshot.
