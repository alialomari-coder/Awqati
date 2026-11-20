# Archived 5.0 development history

Historical development notes; superseded by the user-facing 5.0.0 summary in changelog.md.

# 5.0.0-dev20 — تنقية الأوامر وتنظيم المساعدة

- إخفاء خمسة تسجيلات مكررة غير مخصصة: تشغيل ساعة الإيقاف وتسجيل الجولة وحالتها وآخر جولة، والتوقيت الزوالي. تبقى المعالجات القديمة، ويظل أي أمر ذي تخصيص محفوظ ظاهرًا وقابلًا للاستخدام والتعديل.
- الاحتفاظ بالأوامر المستقلة، ومنها عدد الجولات، وعدد المؤقتات العاملة، والتاريخ الميلادي، والتحكم المستقل بالتنبيهات، وإيقاف المنبه مباشرة.
- نقل أدوات الوقت إلى قسم الساعة وترتيبها: المنبهات، المؤقتات، ساعة الإيقاف، الساعة العالمية. تنظيم اختصاراتها وحذف قسم الأوامر غير المعينة ومعرفاته من الدليلين العربي والإنجليزي.
- بقاء اختصارات dev18 وdev19 وأجسام أوامرها والحسابات والبيانات والتنبيهات والنغمات دون تغيير. التقرير: `docs/command_cleanup_dev20_ar.md`. حزمة تطوير محلية دون نشر رسمي.

# 5.0.0-dev19 — المراجعة النهائية وتحديث المساعدة

- تحديث دليل المساعدة والوصف التعريفي بالعربية والإنجليزية، مع قائمة موحدة للاختصارات الافتراضية والأوامر غير المعينة.
- إصلاح الموقع المخصص مع طريقة «تلقائي حسب الدولة»: طلب اختيار طريقة حساب صريحة عند الحفظ وللإعدادات القديمة المتأثرة، مع المحافظة على البيانات عند الإلغاء.
- بقاء اختصارات dev18 ومعادلات الحساب وأصوات الأدوات دون تغيير.
- فحوص آلية وتكامل وترقية معزولة داخل NVDA؛ تبقى المراجعة اليدوية غير مكتملة. التفاصيل في `docs/final_5_review_ar.md`. لا نشر رسمي.

# 5.0.0-dev18 — اختصارات المؤقتات

- تنفيذ خارطة Y المعتمدة: إعلان فوري وضغطتان بعداد NVDA الأصلي، وتحكم وفتح وإسكات وإعادة تشغيل وتنقل.
- إسكات مؤقت جارٍ واحد في كل ضغطة دون اشتراط تحديده؛ تأكيد كل إعادة تشغيل؛ مزامنة تحديد القائمة والاحتفاظ به عند الإغلاق.
- بقاء أسماء الأوامر السابقة وتخصيصات المستخدم، والمؤقتات المتزامنة وبياناتها وأصواتها وإعداداتها.
- اعتمد المالك dev18 بعد التجربة العملية وأغلق المهمة؛ لا نشر رسمي.

# 5.0.0-dev17 — توحيد الضغطات والاختصارات

- المنبهات: NVDA+F8 يعلن القادم ثم العدد ثم يوقف الجاري دون غفوة؛ NVDA+Shift+F8 للغفوة. الضغطات الزائدة لا تعيد الإجراء.
- ساعة الإيقاف: تشغيل/إيقاف مؤقت/استئناف على NVDA+J، وجولة على NVDA+Shift+J، وتصفير مؤكد للساعة الموقوفة على NVDA+Ctrl+Shift+J. تنفيذ فوري بلا انتظار عدد الضغطات. NVDA+Windows+J للزمن ثم الحالة، وNVDA+Windows+Shift+J للجولة الجارية ثم الأخيرة. فتح النافذة يبقى NVDA+Ctrl+J.
- أزيل موزع انتظار ساعة الإيقاف من الحزمة. لم تتغير النغمات أو مددها أو الحفظ؛ يبقى النطق بعد النغمة في الوضع المختار مع حماية الردود المتقادمة.
- الساعة العالمية تستخدم مقاطعة NVDA الطبيعية دون إلغاء نطق إضافي؛ الضغطات الزائدة تعيد معلومات الثالثة.
- NVDA+Alt+P يفتح المواقيت محليًا؛ NVDA+Shift+P للتحقق الشبكي فقط مع بقاء الموافقة. حُميت رسائل الاستقرار المؤجلة والنتائج القديمة، بما فيها النافذة المحذوفة.
- أوصاف عربية وإنجليزية وخارطة محدثة من بيانات الأوامر. المؤقتات تبقى قابلة للتخصيص دون افتراضيات جديدة، وNVDA+F12 القائم محفوظ مع توثيق تعارضه الأصلي.
- بناء تطويري للمراجعة؛ لا نشر رسمي ولا أوامر طبقية. إغلاق المتابعة ينتظر قبول صاحب المشروع داخل NVDA.

## 5.0.0-dev16 — Immediate world-clock query

- Use NVDA's native repeat counter synchronously for NVDA+Ctrl+F12. Each of the first three presses cancels previous speech and immediately announces its corresponding city; no add-on timer or waiting for later presses.
- Remove the world-clock deferred dispatcher; preserve every other command, shortcut and NVDA setting. Update regression tests and both guides for the approved immediate behavior.

## 5.0.0-dev15 — 2026-11-03 — Published data channel and weekly updates

- Record owner acceptance of dev14 navigation and display names. Confirm the previous update manifest was absent (GitHub 404); replace that endpoint with the public official-repository data-only branch over GitHub's HTTPS contents API.
- Publish signed manifest and full data archive, IANA 2026f/CLDR49, using the existing preinstalled RSA trust anchor. Pin repository and branch, distinguish incompatible builds, and keep all downloaded files inside validated data staging.
- Add default-enabled Update data automatically checkbox. Use a persisted weekly deadline after startup, separate successful-check and actual-update dates, one worker, and bounded silent retries after one hour, six hours, one day, then one week. Keep manual checks independent of that schedule.
- Preserve city order and both-language display overrides; replace the world timezone provider on activation so real updated TZif rules immediately apply. Defer automatic success notification behind important alerts; no automatic failure/no-change messages.
- Verify public download, signature, activation, no-change and rollback with Python 3.12 and NVDA's actual Python 3.13 runtime, plus offline local-server/scheduler/failure regression tests. No official add-on release, main-branch push or layered commands.

## 5.0.0-dev14 — 2026-11-03 — World clock keyboard and display names

- Fix the repeated AttributeError in the owner's real NVDA log: wx.WXK_APPS does not exist in bundled wx. Use verified WXK_WINDOWS_MENU and forward ordinary arrows, Tab and Escape. Preserve native selection and menu behavior without delays.
- Cache rendered row text outside Windows accessibility callbacks; focus and selection handlers do not calculate time, rebuild the list, speak or save.
- Fix the independently reproduced context-menu UnboundLocalError: HitTest unpacking shadowed the gettext function with a local underscore.
- Add Edit name in the city context menu, with independent city/country fields, Save, Cancel and Restore original names. Validate trimmed 1–160 character names and reject control/format characters. Store per-language display overrides separately from reference records and preserve them through reloads, reordering and data updates.
- Add regression tests for keys, cached reads, persistence, DST invariance and the native deferred three-press query, plus real Windows/wx keyboard and editor checks in Arabic and English.
- No official release or data-channel publication. Owner live NVDA speech/braille and freeze-resolution acceptance remain required.

## 5.0.0-dev13 — 2026-11-03 — Offline World clock

- Add World clock as the fourth embedded time tool: bilingual alphabetical search, stable city identities, atomic persistence, reordering, confirmation before deletion, context menus and silent virtual-list refresh.
- Add NVDA+Ctrl+F12: native deferred single/double/triple press announces the first/second/third city without earlier announcements or changing selection.
- Bundle a geographically verified catalog and IANA 2026f rules. Correct GeoNames associations using independent OSM boundaries; retain documented exceptions and provenance. Use the PSF-licensed reference ZoneInfo implementation when NVDA lacks zoneinfo.
- Prepare signed, recoverable manual data updates on a background worker. The new data channel is not published; no live update success is claimed.
- Name the native timer list Timers list / قائمة المؤقتات through wx and Windows MSAA. Record owner acceptance of dev12; preserve the existing three tools, their sounds, shortcuts and engines.
- Live owner speech/braille acceptance remains pending. No layered commands or official release.

## 5.0.0-dev12 — Clock page time tools

- Embed the complete existing alarm, countdown and stopwatch interfaces below a native Time tools selector at the end of Clock settings.
- Preserve native controls and selections while switching; route existing opening commands to their embedded tools with unchanged gestures.
- Remove the separate Alarms and Timers settings section. Keep timing, sound, storage and preferences unchanged from dev11.
- Add regression and Arabic/English native wx checks. Owner acceptance of the new organization remains pending.

## 5.0.0-dev11 — 2026-11-02

- Raise default stopwatch/countdown sine-tone gain and pitch while preserving every approved rhythm, duration and gap. Keep personal alarm and prayer sounds unchanged.
- Add asynchronous countdown command confirmations followed by named speech, independent of expiry preferences.
- Add per-timer Play clock ticking, off by default and compatible with old files. Only the selected running timer ticks, using one cached persistent audio worker; higher-priority alerts silence it without stopping the countdown.
- Owner listening and live accessibility acceptance remain pending. No layered commands or official publication.

## 5.0.0-dev10 — 2026-11-02

- Add multiple independent countdown timers, quick and reusable definitions, pause/resume/restart/cancel/delete, atomic recovery and sleep-inclusive timing.
- Add a bilingual native manager and seven customizable commands without default gestures. Integrate bounded repetitions, independent WAV previews, quiet-hour policy and central alert priorities; preserve higher-priority interruptions as deferred timer-name speech.
- Keep task 2.2 open pending live NVDA keyboard/braille and owner behavior/audio approval. No layered commands or official publication.

## 5.0.0-dev9 — 2026-11-02

- Close stopwatch task 2.1 following final owner acceptance of dev8. Move only its opening default from NVDA+Alt+J to audited NVDA+Ctrl+J, freeing the original braille binding. Preserve all accepted stopwatch behavior and personal settings.

## 5.0.0-dev8 — 2026-11-02

- Correct current-lap queries, shorten stopwatch confirmations, sequence speech after existing tones with stale-message cancellation, and default only new preferences to tones and speech. Preserve approved sound files, native repeat timing and saved preferences. Final owner acceptance remains pending.

## 5.0.0-dev7 — 2026-11-01

- Close personal alarm task 1.1 following owner acceptance. Add independent stopwatch, laps, accessible dialog, atomic recovery, deferred native-repeat commands and cancellable confirmation previews. Live stopwatch acceptance remains pending.

## 5.0.0-dev6 — Personal alarm corrective follow-up (local development)

- Clarify Arabic validation, storage, interruption, stop and snooze messages; announce the saved and scheduled snooze duration through the shared duration formatter.
- Extend NVDA+F8 to immediate next/count/snooze/stop actions using NVDA native repeat counts. The owner explicitly accepted earlier actions taking effect before later presses. Preserve the independent commands and other gestures.
- Stop can cancel the most recently snoozed pending cycle. Keep the native weekday list without synthetic speech; document NVDA's selected-state filtering and live-test limits.
- Preserve the approved alarm audio and prior packages. No release publication.
