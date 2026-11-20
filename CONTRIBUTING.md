# Contributing to Awqati

Thank you for helping improve Awqati, an accessible NVDA add-on. Bug reports, feature ideas, documentation improvements, translations, and code contributions are welcome.

## Report a problem or suggest an improvement

Search [existing issues](https://github.com/alialomari-coder/Awqati/issues) before opening a new one. For a bug, include the Awqati version, NVDA version, Windows version, interface language, steps to reproduce, expected result, and actual result. If useful, attach the relevant part of the NVDA log or Awqati's diagnostic information after reviewing it for personal information. Never include passwords, access tokens, recovery codes, or your full NVDA configuration.

For a suggestion, explain the problem it would solve and how someone using only a keyboard and a screen reader would use the proposed feature. Discuss substantial changes in an issue before implementing them.

## Submit a pull request

1. Fork the repository and create a branch for one focused change.
2. Read [the development guide](DEVELOPMENT_GUIDE.md), [the user guide](addon/doc/en/readme.md), and any relevant tests.
3. Make the change without unrelated formatting, generated packages, local logs, or personal settings. Add or adjust meaningful tests when behavior changes.
4. Check the affected behavior and describe the checks you actually performed. Clearly distinguish automated checks from testing inside NVDA.
5. Open a pull request against `master`. Explain the problem, resulting behavior, relevant issue, and validation. Update documentation and translations when applicable.

## Compatibility and accessibility

The stable 8.2.1 release requires NVDA 2026.1 and declares testing through NVDA 2026.3.1. Do not change compatibility declarations without evidence from testing. Preserve existing settings and shortcuts unless a change has been discussed.

Every function must work from the keyboard. Controls need meaningful accessible names, logical focus order, readable text errors, and predictable focus restoration. Test Arabic and English when changing shared interface behavior. Keep network requests and slow work away from NVDA's main thread, and keep NVDA and wxPython dependencies out of the domain and application layers.

See [TRANSLATING.md](TRANSLATING.md) for localization. Contributions must be compatible with the project's [GPL v2 or later license](COPYING.txt); preserve third-party notices and attribution.
