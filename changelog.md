# Awqati changes

## 4.0.0 — owner-acceptance candidate

- Completely rebuilt the add-on formerly known as Prayer Times and renamed it Awqati to reflect its wider scope.
- Added a global location database, custom and explicitly detected locations, bundled IANA time-zone data, and offline core operation.
- Rebuilt prayer calculations, Iqama and current/waiting states; Zawali and Ghurubi clocks; five calendars; Qibla; astronomy; and the traditional Arabian calendar.
- Rebuilt alerts, adhkar, the daily Wird, quiet hours, scheduling, sound and speech, fallback, and overlap handling.
- Added optional manual online prayer verification, manual data updates, and privacy-preserving diagnostics, with no automatic connection.
- Completed Arabic and English interfaces, documentation, right-to-left and left-to-right layouts, and keyboard accessibility.
- The 0.5.x entries below are internal development history; the user guides list published-version history.

## 0.5.4.2 — Qibla button in settings

- Added an accessible Arabic and English button after the assigned-location controls.
- Reused the existing Qibla command path, formatting, missing-location policy, and shortcut unchanged.
- Preserved native keyboard focus order in Arabic RTL and English LTR settings.

## 0.5.3.6 — keyboard-responsive shortcut privacy prompt

- Opened the first-session privacy confirmation non-modally after the global gesture handler returns.
- Preserved its text, session-only approval, focus restoration, and the existing settings-button behavior.
- Added regression coverage preventing a blocking modal dialog from returning to the shortcut path.

## 0.5.3.2 — manual data updates and diagnostics

- Added the public HTTPS data channel for the five approved versioned data packages.
- Added atomic package validation, SHA-256 verification, rollback, timeout, and cancellation handling.
- Added optional AlAdhan prayer-time verification and privacy-preserving diagnostic information.
- Added accessible Arabic and English settings actions and NVDA commands for explicit checks only.
## 0.5.2.3 — numeric spoken clock correction

- Replaced colon-separated numeric clock speech with numeric values and explicit minute and second units.
- Applied the correction to Arabic and English Zawali and Ghurubi output while preserving word formatting and zero-minute settings.
- Added a regression matrix for both hour systems, seconds, zero minutes, styles, languages, and clock types.

## 0.5.2.2 — Arabic and English localization

- Completed Arabic and English product documentation and language-direction coverage.
- Removed Arabic logical defaults from Domain while preserving user-authored Wird text.
- Centralized reviewed prayer names, astronomical terms, devotional transliterations, feature names, and reminders.
- Added task 5.2 translation, glossary, documentation, fallback, and architecture regression checks.

## 0.5.1.4 — prayer-state duration formatting

- Formatted prayer-state durations of 60 minutes or more as localized hours and minutes.
- Preserved minute-only output below one hour and omitted zero-minute remainders.
- Added Arabic singular, dual and plural forms plus natural English counterparts.

## 0.5.1.3 — corrective follow-up after task 5.1

- Localized F11, daily prayer times and alert status completely through gettext.
- Replaced the private multi-press delay with NVDA's native repeat count.
- Adopted the final 21-command map, including Ctrl+H and Shift+P.
- Corrected 12-hour Zawali periods, daily-information contexts and local season-day numbering.
- Adopted the owner-edited Arabian calendar data as version 2026.09.16-r2.

## Development scaffold

- Created the initial NVDA add-on package structure.
- Added repeatable SCons packaging and foundational tests.
- Added execution-management documentation for task 0.1.
