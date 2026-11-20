# Translating Awqati

## Current languages and files

Awqati 8.2.1 supports English and Arabic. English is the source language. Arabic gettext catalogs are:

- `addon/locale/ar/LC_MESSAGES/nvda.po`: the main NVDA interface catalog.
- `addon/locale/ar/LC_MESSAGES/calendar_converter.po`: the separate calendar-converter catalog.
- `addon/doc/en/readme.md` and `addon/doc/ar/readme.md`: the complete user guides, with HTML copies alongside them.
- `docs/دليل_أوقاتي_العربي_المعتمد.md`: the approved Arabic guide source used by the documentation generator.

Some current text is selected directly by the Arabic/English formatters rather than gettext. The converter also selects Arabic or English explicitly. A new language therefore needs a coordinated development change as well as translated catalogs; placing a new `.po` file in the tree alone will not provide complete support.

## Extract and translate messages

Use the build dependencies described in [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md). `tools/build_translations.py` is the authoritative extractor. Its `extract_catalog()` function extracts the main domain; `extract_catalog("calendar_converter")` handles the independent converter domain, including conditional string branches. The main extraction also includes selected data labels and the translatable add-on metadata from `buildVars.py`.

To extract both templates without building or changing the approved add-on package, run this command from the repository root in PowerShell with a configured Python environment:

```powershell
python -B -c 'from pathlib import Path; from tools.build_translations import extract_catalog; from babel.messages.pofile import write_po; Path("build").mkdir(exist_ok=True); [(write_po(Path("build", name + ".pot").open("wb"), extract_catalog(domain), sort_output=True)) for name, domain in (("messages", "nvda"), ("calendar_converter", "calendar_converter"))]'
```

The templates are `build/messages.pot` and `build/calendar_converter.pot`. Edit `.po` files with a gettext editor, updating existing catalogs from the corresponding template. Preserve every message identifier, placeholder such as `{date}` or `%s`, formatting flag, markup element, URL, and technical identifier. Translate the surrounding text. Keep keyboard shortcuts and control names consistent with the guides; do not silently change shortcut assignments.

For another language, first open an [issue](https://github.com/alialomari-coder/Awqati/issues) to coordinate its locale code, terminology, and runtime support. Use the existing layout, `addon/locale/<language>/LC_MESSAGES/`, with both domains and a guide under `addon/doc/<language>/`. The 8.2.1 build validates and compiles Arabic explicitly; additional-language compilation and formatter support are future development work. This publication does not change them.

## Validate and contribute

Check catalog syntax, placeholders, missing translations, and fuzzy entries. In a separate development checkout, build a test package using the development guide and test it with a separate NVDA profile. Review spoken messages, punctuation, keyboard navigation, accessible names, dialogs, errors, converter results, and the complete guide. Compare the translated meaning with the English source. Report the NVDA version and checks performed in your pull request against `master`.

For the approved 8.2.1 release, do not regenerate catalogs or rebuild the published package. Its existing compiled files are release artifacts; translation contributions should target a future reviewed release.

## Future NVDA community translation integration

The [official submission guide](https://github.com/nvaccess/addon-datastore/blob/master/docs/submitters/submissionGuide.md) links to the [guide for authors](https://github.com/nvaccess/AddonTemplate/blob/master/docs/l10n/addonAuthors.md) and [guide for translators](https://github.com/nvaccess/AddonTemplate/blob/master/docs/l10n/addonTranslators.md). The current community workflow uses Crowdin for interface catalogs and XLIFF documentation.

Awqati's gettext catalogs and Markdown guides provide a basis for later integration, but this repository is not yet configured for that workflow. A later task must coordinate community-project access, configure a restricted repository secret, add the supported synchronization infrastructure, and account for both gettext domains and the bilingual formatter code. Documentation conversion and additional-language build/runtime support also need review. No Crowdin registration, token setup, workflow installation, or runtime change was performed for 8.2.1 publication.
