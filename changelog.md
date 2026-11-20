# 8.2.1

## تحسينات

- تقسيم التقرير العربي المفصل للحالة الحالية إلى جمل أقصر مع حفظ المعلومات وترتيبها ووحداتها.
- تحسين صياغة فترة عدم توقع الأمطار، بما يشمل الامتداد إلى صباح الغد أو مسائه.
- توضيح أن أعلى احتمال لهطول الأمطار يخص إحدى ساعات اليوم المتاحة، ونطق النسبة الصفرية «صفر بالمئة».

# 8.0.2

## Improvements

- Updated Arabic and English overviews; moved complete weather help into settings after Calendar.
- Refined Arabic next-day time ordering and today’s forecast opening. Condensed all-zero hourly probabilities in speech only, preserving missing and positive values and full text details.

## Bug fixes

- Unified Open weather information in a text window; opening reviews the last successful report without fetching or changing open text.
- Failed or cancelled requests no longer replace the saved successful report. Opening the window before a successful request announces that no previous weather information is available, without fetching data.

Existing gestures, weather transport and calculations are unchanged.

## 8.0.1

### تحسينات

تحسين تقارير الطقس والتعريب ومستويات التفاصيل والتوقعات ونسخ التقرير؛ NVDA+Alt+W لإعدادات الطقس.

- استخدام أسماء المدن العربية والإنجليزية من آلية أوقاتي القائمة، مع إبقاء أسماء المواقع المخصصة كما كتبها المستخدم.
- توضيح الفرق بين التقرير الحالي المختصر والمفصل، واحترام اختيارات المعلومات والوحدات، مع وصف النهار والليل بحسب البيانات المتاحة.
- بيان فترة قياس الهطول الحالي، وتوزيع العينات الساعية على أفق التوقعات مع تضمين آخر عينة متاحة وتوضيح الانتقال إلى الغد.
- ربط ملخص الطقس في معلومات اليوم بمستوى التفاصيل والخيارات، باستخدام مخبأ صالح دون انتظار الشبكة.
- تنظيم التقارير النصية وإضافة زر «نسخ التقرير»، مع إبقاء إسناد المصادر في النص المكتوب والدليلين دون تكراره في النطق المباشر.

## 8.0.0 — خدمة الطقس، 20 نوفمبر 2026

أول حزمة كاملة بخدمة Open-Meteo الاختيارية، تشمل جميع وظائف 7.1.0. تقارير الحالي واليوم والأيام القادمة، ضغطات NVDA+W المحسومة قبل النطق، معلومات ووحدات مخصصة، نافذة قابلة للنسخ، وملخص نبذة يومية اختياري. الطقس معطل افتراضيًا ويتطلب الإنترنت عند تمكينه؛ الإحداثيات والمنطقة الزمنية وعنوان IP تصل إلى المزود. المخطط 2 يرحّل إعدادات 7.1.0 ويحفظ نسخة المخطط 1 قبل أول حفظ. الدليلان والاختصارات والإسناد والخصوصية مطابقة للحزمة. نجحت فحوص الحزمة المثبتة والتحديث المعزول على NVDA 2026.1 و2026.3.1 باللغتين. لا نشر في المتجر ولا تثبيت شخصي؛ تجربة الاستماع ولوحة المفاتيح الفعلية للمالك. التفاصيل: AWQATI_8_0_0_RELEASE_REPORT.md.

## مصدر التطوير بعد 7.1.0 — خدمة الطقس، 20 نوفمبر 2026

- إضافة الطقس الحالي وتوقعات اليوم والساعات والأيام القادمة من Open-Meteo، وجودة الهواء الأمريكي اختيارية مستقلة.
- NVDA+W يحدد التقرير بضغطة أو ضغطتين أو ثلاث قبل النطق، مع قسم إعدادات بأربع مجموعات وتقارير ثنائية اللغة ووحدات مخصصة ونافذة قابلة للنسخ.
- تحديثات صامتة ومخبأ ودمج طلبات وتراجع عند فشل المصدر، وإبطال النتائج القديمة عند تغيير الموقع أو التعطيل؛ ملخص النبذة من مخبأ صالح فقط.
- مخطط إعدادات 2، ترحيل صريح يحفظ الخيارات السابقة ونسخة احتياطية قبل أول كتابة ذرية. أدلة الخصوصية والإسناد والرجوع إلى 7.1.0 محدثة.
- هذا تغيير في المصدر، وليس إصدارًا منشورًا؛ الحزمة 7.1.0 والحسابات والاختصارات القديمة محفوظة. تقرير النتائج: docs/WEATHER_TASK2_REPORT.md.

## استكمال الإغلاق النهائي للإصدار 7.1.0 — 20 نوفمبر 2026

اكتملت مراجعة التغييرات التسعة، وأُغلقت مهام إثراء النبذة الفلكية بعد اعتماد المالك. تطابق الدليلان مع الحزمة، ونجح 22 فحصًا للحزمة والمساعدة والبنية وفحص صياغة 138 وحدة Python. نتيجة 1486 اختبارًا السابقة محفوظة بوصفها نتيجة تاريخية، ولم تُعد الاختبارات الفلكية في متابعة الإغلاق. بقيت الوظائف المعتمدة محفوظة.

## السجل السابق (تاريخي)

## الإغلاق النهائي للإصدار 7.1.0 — 19 نوفمبر 2026

اعتمد مالك المشروع «أوقاتي 7.1.0» اعتمادًا نهائيًا في طلب الإغلاق بتاريخ 19 نوفمبر 2026، بعد تثبيته وتجربة النبذة الفلكية ونطقها واختصاراتها ونافذة المعلومات. هذه إفادة المالك عن تجربته الشخصية. اكتملت المهام التسع وأُغلقت دون أعمال معلقة في مشروع إثراء النبذة الفلكية.

الحزمة النهائية الوحيدة في مجلد التوزيع: `dist/awqati-7.1.0.nvda-addon`، بحجم 14,556,042 بايت. بصمة SHA-256 النهائية: `9684debf537389370652fe132419a6aa492451ab473ef66cfdc38357bc446e67`. أُعيد بناء الإصدار بنفس رقمه لتضمين شرح الدليلين المحدّث؛ تطابقت شفرة المنتج وبياناته ورسائل ترجمته مع الحزمة المعتمدة. تغيّرت ملفات المساعدة الأربعة وترويسة توليد كتالوج الترجمة فقط.

نجحت بوابة البناء بعد التنظيف و1486 اختبارًا، دون إخفاق أو خطأ أو تجاوز. الأدلة النهائية في `docs/release_7_1_0/closure/`، والتفاصيل في `RELEASE_7_1_0_CLOSURE.md`. لا بدء لخدمة الطقس ولا تغيير للوظائف المعتمدة. أوصاف انتظار القبول وحفظ الحزم السابقة في السجل التالي تاريخية، وقد حل هذا الإغلاق محلها.

## أوقاتي 7.1.0 — حزمة كاملة للاختبار والاعتماد الشخصي — 19 نوفمبر 2026


- دمج النبذة الفلكية المعتمدة بفقراتها الخمس، مع العبور الزوالي للشمس وارتفاعها، وتغير مدة النهار، ومسافة الأرض عن الشمس، وأحداث القمر وعبوره وقمته المستقلة ومسافته ومواعيد أطواره القادمة.
- الحفاظ على القسم التراثي مستقلًا وعلى الإعدادات والاختصارات والوظائف السابقة، دون تغيير الإعدادات الافتراضية.
- إصلاح اسم مربع نافذة النص لدى قارئ الشاشة، واستعادة التركيز إلى عنصر الفتح عند الإغلاق.

نجح 1486 اختبارًا و20 تشغيل NVDA معزولًا على 2026.1 و2026.3.1 للتثبيت الجديد والتحديث، باللغتين. التقرير AWQATI_7_1_0_RELEASE_REPORT.md. لا نشر في المتجر؛ يبقى الاعتماد الشخصي لدى المالك. حزمة 7.0.0 محفوظة ببصمتها الأصلية.

## إغلاق المتابعة التحريرية للمهمة 3.1 — 19 نوفمبر 2026

اعتمد المالك النص العربي النهائي صراحةً، وثُبت في المنسق مع إنجليزية مكافئة
في المعنى وترتيب المعلومات. حُفظ المرجع في
`docs/daily_synopsis_task31/final_editorial/approved_ar.txt`؛ الناتج مطابق له
بعد توحيد الأسطر والمسافات فقط. لم تتغير أي حسابات أو خدمات أو نصوص تراثية.
نجح 46 اختبارًا موجهًا، وتحققت بصمات 1636 ملفًا سابقًا خارج ملفي التنسيق.
التقرير الحالي والنموذجان: `DAILY_SYNOPSIS_TASK31_FINAL_EDITORIAL_REPORT.md`.
هذه هي المرجعية التحريرية الأحدث بدل النماذج السابقة. اكتملت 3.1 من جانب
المصدر والتحقق؛ الحزمة المستقرة 7.0.0 محفوظة دون بناء أو استبدال، ولم تبدأ 3.2.
اعتماد النص لا يعني نشر إصدار جديد أو إجراء اختبار استماع بشري.

## متابعة تصحيحية للمهمة 3.1 — 19 نوفمبر 2026

صُحح مصنّف طور القمر نفسه: ألغيت قطاعات الأسماء الرئيسية ذات العرض 45 درجة،
وأصبحت الفترات بين الزوايا الأساسية هلالًا أو أحدب متزايدًا أو متناقصًا.
نموذج 19 نوفمبر أصبح «الأحدب المتزايد» مع بقاء الإضاءة 68.6 بالمئة والعمر
التقريبي عشرة أيام؛ لم تتغير القيم العددية أو خدمة مواعيد الأطوار الأربعة.
جُمعت مقارنة النهار منذ الانقلاب مع طول النهار، وهُذبت الجمل والترقيم
والتكرار بالعربية والإنجليزية، مع إبقاء الساعة المدنية صباحًا أو مساءً.
نجح 44 اختبارًا موجّهًا؛ تحققت بصمات 1634 ملفًا وبقي التراث في النموذجين
مطابقًا حرفيًا. التقرير الحالي والنموذجان: `DAILY_SYNOPSIS_TASK31_CORRECTION_REPORT.md`.
الأدلة: `docs/daily_synopsis_task31/correction/`. هذه المتابعة تعلو في المرجعية
على وصف التصنيف والنموذج الأول السابق. الحزمة المستقرة محفوظة؛ 3.1 تنتظر
المراجعة والاعتماد، ولم تبدأ 3.2. لم يُجر اختبار نطق تفاعلي لهذه المراجعة.

## تطوير الفلك — المهمة 3.1 — 19 نوفمبر 2026

اكتمل دمج القدرات السبع في النبذة العلمية بالعربية والإنجليزية في مصدر التطوير:
عبور الشمس وارتفاعها عنده، تغير النهار منذ الانقلاب، أقصى النهار والليل
في أيامهما الفعلية المستقلة، المسافتان، شروق القمر وغروبه بالترتيب،
العبور القمري والقمة الفعلية منفصلين، والأطوار الأربعة من مصدر موحد.
لا توجد مستويات تفصيل مطبقة حاليًا؛ استُخدم النص القائم للنطق والنافذة
دون إضافة إعداد أو اختصار. التراث مستقل ومحفوظ حرفيًا في موضعه السابق.
نجح 168 اختبارًا موجّهًا، منها 18 اختبار تكامل جديدًا، وتحققت بصمات 1630
ملفًا سابقًا خارج ستة ملفات ربط معدلة عمدًا. لم تعد المراجع الفلكية السابقة.
النموذجان الكاملان والأدلة: `DAILY_SYNOPSIS_TASK31_REPORT.md`
و`docs/daily_synopsis_task31/`. توجد مذكرة ΔT في العرض حيث يلزم.
الحزمة المستقرة 7.0.0 لم تُبنَ أو تُستبدل؛ لم تبدأ 3.2. النتيجة للمراجعة
والاعتماد قبل أي إصدار. ما يلي من إدخالات سابقة سجل لحالة كل مهمة وقت تنفيذها.

## تطوير الفلك — اكتمال المهمة 2.4 — 19 نوفمبر 2026

أُضيفت مواعيد الأطوار الأربعة بخوارزمية Meeus المشتركة وخدمة اختيارية، مع
ترتيب UTC والقادم لكل طور وصياغة عربية وإنجليزية منفصلة. لم تُدمج في النبذة.
نجح 32 اختبارًا و96 مقارنة JPL على TT؛ أقصى فرق 14.871159 ثانية ضمن 90 ثانية.
حُفظ فشل الهامش الأصلي لمقارنة USNO في 2099 وفسر اختلاف نموذج الزمن دون إخفائه.
المسار القديم للمحاق والبدر بقي مطابقًا في 4922 حالة؛ المسار الجديد يغير
التحويل إلى UTC المعروف فقط، بأقصى فرق 6.482982 ثانية، دون استبدال المعروض.
قبل 1972 ومن 2027 الزمن النموذجي موسوم `modeledUT`، وليس UTC محققًا.
التفاصيل: `LUNAR_PHASES_TASK24_REPORT.md` والأدلة `docs/lunar_phases_task24/`.
الحزمة المستقرة 7.0.0 محفوظة. انتهت 2.4 فقط؛ المرحلة الثالثة لم تبدأ وتنتظر الاعتماد.

## تطوير الفلك — اكتمال المهمة 2.3 — 19 نوفمبر 2026

أُضيفت المسافة الهندسية الحالية بين مركزي الأرض والقمر دون تقريب، من
مزود الوقت وبلا موقع، مع تنسيق عربي وإنجليزي منفصل إلى أقرب ألف كم.
نجح 22 اختبارًا موجّهًا و41 مقارنة JPL بلا زمن ضوء؛ أقصى فرق 7.004829 كم
ضمن سماحية 20 كم. حُفظت الحسابات السابقة والنبذة والصلاة والإعدادات
والحزم. التقرير والأدلة: `LUNAR_DISTANCE_TASK23_REPORT.md`
و`docs/lunar_distance_task23/`. انتهت 2.3 فقط ولم تبدأ 2.4.
الإصدار المستقر يبقى 7.0.0؛ هذا تطوير مصدر اختياري غير مدمج في النبذة.

## تطوير الطبقة الفلكية — المهمة 1.3، 19 نوفمبر 2026

أضيف استعلام اختياري للمسافة الهندسية الحالية بين مركزي الأرض والشمس،
بالكيلومتر دون تقريب ومن مزود الوقت المعتمد، مع تنسيق رقمي منفصل بملايين
الكيلومترات للمهمة 3.1. تحققت 50 مقارنة مع JPL ضمن 25000 كيلومتر؛ أكبر فرق
11003.401456 كيلومتر. نجح 58 اختبارًا موجّهًا؛ لا تغيير للنبذة أو الصلاة أو
الإعدادات أو نتائج المهمتين 1.1 و1.2، ولا حزمة أو إصدار أو مرحلة ثانية جديدة.

# 7.0.0 — 2026-11-13

محوّل تاريخ بسيط ومتقدم، ونتيجة مشتركة مع النسخ والعكس، ودعم الغريغوري واليولياني والهجري بأم القرى والحساب التاريخي IIc. الوصول من صفحة «التقويم»، أو أمر «فتح محوّل التاريخ» بلا اختصار افتراضي؛ ضغطة للبسيط وضغطتان للمتقدم بعد التعيين. المحافظة على الإعدادات والاختصارات السابقة. اعتمد المالك الإصدار مستقرًا ونهائيًا في 13 نوفمبر 2026 بعد نجاح قبوله الشخصي واكتمال المهام الست ونجاح 1336 اختبارًا آليًا واختبارات NVDA 2026.1 و2026.3.1 باللغتين. لا مشكلات مفتوحة تمنع الاعتماد، مع الاحتفاظ بالقيود الاختبارية الموثقة. لم يُنفذ نشر أو Git push.

# الإصدار 6.0.0

اعتماد نهائي — 11 نوفمبر 2026: اعتمد صاحب المشروع 6.0.0 إصدارًا مستقرًا ونهائيًا بعد اكتمال تجربة الاستخدام ونجاح الحالات الـ1258 عبر الجولة السابقة واستكمال الحالات الثلاث على Python 3.13.15، دون تجاوزات باقية. أُغلقت أعمال تطوير الإصدار مع إبقاء الحزمة المعتمدة وبصمتها دون تغيير؛ النشر مؤجل لقرار لاحق. تفاصيل الاعتماد وأدلة الاختبارات في STATUS.md وAWQATI_6_0_0_REMAINING_TESTS.md.

يضيف هذا الإصدار خدمة «حدث في مثل هذا اليوم»، مع الاحتفاظ بجميع وظائف الإصدار الخامس وأدوات الساعة.

- جلب أحداث اليوم والمواليد والوفيات والأعياد والمناسبات من ويكيبيديا بالعربية والإنجليزية.
- السرد المباشر وصفحات HTML قابلة للتصفح باستخدام NVDA، مع روابط المقالات الأصلية وملخص أعداد البنود.
- تخزين يومي للمعلومات. الاختصار NVDA+Windows+F12 بضغطاته الأربع.

## Version 6.0.0

Final approval — 11 November 2026: the owner accepted 6.0.0 as the final stable release after usage acceptance and completion of all 1,258 tests across the previous run and the three remaining tests on Python 3.13.15, with no outstanding skips. Development is closed; the approved package and its SHA-256 remain unchanged. Publication awaits a separate owner decision.

Adds On This Day while retaining every version 5 feature and time management tool.

- Wikipedia events, births, deaths, holidays and observances in Arabic and English.
- Direct narration and HTML pages accessible with NVDA, with original article links and section counts.
- Daily caching. Use NVDA+Windows+F12 with one to four presses.

# الإصدار 5.0.0

يقدم هذا الإصدار أربع أدوات جديدة لإدارة الوقت، مع تحسينات في الأداء والاستقرار وسهولة الاستخدام.

- **المنبهات:** إنشاء منبهات شخصية متعددة، مع إمكانية تحديد أيام التكرار وأصوات التنبيه، وتأجيل الرنين أو إيقافه.
- **المؤقتات:** تشغيل عدة مؤقتات تنازلية في الوقت نفسه، مع إمكانية إيقافها مؤقتًا واستئنافها وإعادة تشغيلها، وتخصيص أصواتها وتفعيل تكتكة الساعة.
- **ساعة الإيقاف:** قياس الوقت وتسجيل الجولات ومراجعة نتائجها ونسخها.
- **الساعة العالمية:** معرفة الوقت في مدن العالم، وإضافة المدن المفضلة وترتيبها وتخصيص أسمائها، مع مراعاة اختلاف المناطق الزمنية والتوقيت الصيفي.
- **اختصارات لوحة المفاتيح:** إضافة اختصارات مخصصة لأدوات الوقت الجديدة، وتحسين سرعة الاستجابة وتنظيم الأوامر.
- **تحسينات عامة:** تعزيز استقرار الإضافة، وتحسين بعض الواجهات، وتحديث دليلي المساعدة بالعربية والإنجليزية.

## Version 5.0.0

This version introduces four new time management tools, along with improvements to performance, stability and ease of use.

- **Alarms:** Create multiple personal alarms, choose repeat days and alarm sounds, and snooze or stop ringing.
- **Timers:** Run multiple countdown timers at the same time, with options to pause, resume and restart them, customize their sounds and enable clock ticking.
- **Stopwatch:** Measure time, record laps, and review and copy the results.
- **World clock:** Check the time in cities around the world, add and reorder favorite cities, and customize their names, accounting for time zone differences and daylight saving time.
- **Keyboard shortcuts:** Add dedicated shortcuts for the new time tools, improve responsiveness and organize commands.
- **General improvements:** Enhance add-on stability, improve some interfaces, and update the Arabic and English help guides.

سجل التطوير التفصيلي محفوظ في [أرشيف التطوير / Development archive](docs/development_changelog_pre5.md).

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


## 5.0.0-dev22 — 2026-11-11

- Add On This Day with four presses of NVDA+Windows+F12, interruptible direct speech and optional accessible local web pages. Reuse the daily Arabic/English Wikipedia cache and validate all output links.

## تطوير غير منشور — المهمة الفلكية 1.2، 19 نوفمبر 2026

- إضافة API حسابي للتغير الموقّع منذ الانقلاب السابق، وحدود النهار السنوية حسب الموقع والسنة المحلية، والمدد الليلية المقابلة وتواريخ حدودها المستقلة.
- فصل تساوي نتائج المحرك الدقيقة عن التساوي بعد تقريب الدقائق؛ أهلية الإعلان لأول يوم دقيق فقط، وعدم استخدام مدد قطبية افتراضية.
- توثيق التعريف وحدود الدقة والفروق المرجعية في ASTRONOMY_ENHANCEMENT_STUDY.md وdocs/data_sources.md، دون تغيير النبذة أو حزمة الإصدار المستقر.

## 19 نوفمبر 2026 — المهمة الفلكية 2.1

- حساب محلي اختياري لشروق القمر وغروبه بموقع المستخدم وتاريخه المدني، مع اختلاف المنظر والانكسار وحجم القرص، وكل أحداث اليوم وحالات الغياب أو الخطأ المستقلة.
- صياغة عربية وإنجليزية مستقلة جاهزة للمهمة 3.1، دون دمجها بالنبذة الحالية أو تغيير الإعدادات أو الصلاة أو الحزمة 7.0.0.
- نجاح 51 اختبارًا و33 حالة USNO تضم 47 حدثًا؛ أقصى فرق 29.445190 ثانية، وتطابق الغياب والتعدد. أدلة وبصمات التسليم في docs/lunar_horizon_task21، والتقرير LUNAR_HORIZON_TASK21_REPORT.md.
- توقفت الأعمال عند 2.1؛ لم تبدأ 2.2.

### تصحيح صياغة المهمة 2.1 — 19 نوفمبر 2026

- تسمية القمر صراحة في أول ذكر بالعربية والإنجليزية، وتصحيح أمثلة التقرير والوثائق.
- عرض أحداث شروق القمر وغروبه بحسب ترتيبها الزمني الفعلي، بما فيها الأحداث المتعددة ورجوع الساعة، دون تغيير الحسابات.
- توثيق القاعدة لدمج المهمة 3.1، وفحص نصي منفصل بأوقات جاهزة فقط؛ لم تعد الاختبارات الفلكية ولم تبدأ 2.2. أدلة المزامنة في docs/lunar_horizon_task21/text_revision/.


## 19 نوفمبر 2026 — المهمة الفلكية 2.2

- إضافة `lunar_transit_day` و`AstronomyService.read_lunar_transit` لحساب
  كل العبور الزوالي العلوي وارتفاع مركز القمر عنده، وأعلى ارتفاع هندسي
  فعلي مستقل، بالاعتماد على الحساب المحلي المشترك للمهمة 2.1.
- تمييز حدود اليوم والقيمة الحدية غير المتحققة عند نهايته، الغياب والتعدد،
  الحالات القطبية والتوقيت الصيفي واليوم المكرر والمحذوف وبقاء المركز تحت الأفق.
- توثيق الصياغتين العربية والإنجليزية للمهمة 3.1 دون تعديل النبذة المعروضة.
- نجاح 59 اختبارًا مركزًا و14 حالة Horizons، تتضمن 11 عبورًا و14 قيمة قصوى؛
  أقصى فرق 11.992175 ثانية و0.001228038 درجة. لم تعد المراجع السابقة.
- المحافظة على الصلاة والإعدادات والنبذة والحزمة المستقرة؛ انتهت 2.2 وحدها
  دون بدء 2.3. التفاصيل وأدلة التسليم في `LUNAR_TRANSIT_TASK22_REPORT.md`
  و`docs/lunar_transit_task22/`.


## تطوير غير منشور — التحقق الفلكي 3.2 — 19 نوفمبر 2026

- إصلاح اسم مربع نافذة النص الذي كان مفقودًا في MSAA رغم تعريفه في wx، بإضافة تسمية أصلية مرتبطة.
- استعادة التركيز إلى عنصر الفتح بعد إغلاق نافذة النص، إذا بقي متاحًا.
- تحقق ثنائي اللغة على NVDA 2026.1 و2026.3.1 معزولًا، مع حماية النص والحسابات والحزمة المستقرة. التقرير DAILY_SYNOPSIS_TASK32_FINAL_VERIFICATION_REPORT.md؛ لا إصدار جديد، والقبول السمعي البشري لم يُجرَ.
