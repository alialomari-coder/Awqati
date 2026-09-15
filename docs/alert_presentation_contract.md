# عقد عرض التنبيهات والصوت — المهمة 4.4

أغلقت المهمة 4.4 في 16 سبتمبر 2026. يصف هذا الملف الحد الفعلي بين Scheduler والعرض، ولا ينفذ ربط دورة حياة `GlobalPlugin` المؤجل إلى 5.1.

## الملكية والتسلسل

- `AlertScheduler` وحده يملك `waiting` و`current` ويمنح lease بواسطة `claim_for_presentation`.
- `AlertPresenter` لا يملك طابور أحداث ثانياً. يحتفظ فقط بالحدث الجاري والمرحلة الحالية لحماية callbacks المتأخرة أو المكررة.
- يسجل `mark_presented` مرة واحدة عند callback بدء output الفعلي. ثم يستدعي `complete(..., presented=False)` عند النهاية لأن التسجيل سبق أن تم.
- بعد اكتمال الحدث يطلب Presenter الحدث التالي من Scheduler؛ لذلك يعيد Scheduler فحص الصلاحية ويمكنه إسقاط حدث انتهت grace الخاصة به أثناء صوت طويل.
- `SOUND_AND_SPEECH` يعني WAV حتى completion الموثوق، ثم speech. لا يبدأ المساران معاً.
- فشل الصوت أو غيابه أو تلفه يحول الحدث إلى نطق مرة واحدة. `SILENT` لا يتحول إلى نطق.

## AudioService

- يحل الملف بالترتيب: custom صالح، ثم default صالح لنوع الحدث، ثم لا صوت.
- default المضمّن الوحيد هو `globalPlugins/awqati/sounds/clock/clock.wav` لنوع الساعة.
- يقرأ WAV على worker في دفعات، ويستخدم `nvwave.WavePlayer.feed` ثم `idle` لمعرفة اكتمال التشغيل الحقيقي. لا يقرأ الملف كاملاً ولا ينتظر خيط NVDA ولا يقدر المدة ولا يفرض حداً زمنياً.
- يرفض بدء WAV ثانٍ أثناء التشغيل. تبلغ callbacks حالات البدء، الاكتمال، الإلغاء، والفشل قبل أو بعد البدء.
- تستخدم معاينة الإعدادات الخدمة نفسها؛ أزيل المسار المستقل `wx.adv.Sound`.

## SpeechService

- يعزل NVDA speech API داخل Adapter ويستخدم `CallbackCommand` لمعرفة التقدم والاكتمال.
- يأتي callback البدء بعد أول جزء منطوق، لا قبل أول نص. هذا ضروري أيضاً لتفادي index-only prefix الذي ثبت أنه يعلق OneCore 2026.2.
- يأتي callback الاكتمال في نهاية speech sequence، وتغلق `speechCanceled` العملية عند الإلغاء. لا توجد sleeps أو تقديرات بعدد الأحرف.
- ترفض الخدمة رسالة ثانية ما دامت الرسالة الأولى جارية.

## ملفات WAV

- الجذر: `<NVDA config path>/awqati/sounds`.
- الفروع النهائية: `alerts` و`clock` و`adhkar`.
- تقبل قراءة مرجع `sounds/adhan/...` القديم فقط للتوافق؛ لا تنشأ مراجع جديدة بهذه الفئة ولم يرتفع schemaVersion.
- `validate_wav` يتحقق من الامتداد وRIFF/WAVE وحدود chunks ووجود `fmt` و`data` غير فارغين ومعلمات PCM المدعومة، من دون تحميل payload كاملاً.
- الملف الخارجي ينسخ إلى staging بدفعات ثم ينتقل ذرياً عند Apply/OK. المرجع نسبي وآمن ولا يسمح بمسار مطلق أو `..`.
- النسخ التي تنشئها الإضافة فقط تحمل بادئة `awqati-managed-<hash>-`. التنظيف لا يمس ملفات المستخدم اليدوية ولا المصدر الخارجي ولا default المضمّن.
- Cancel يلغي staging، وفشل الحفظ يعيد rollback، وإزالة custom تجعل الحل يعود إلى default إن وجد وإلا إلى fallback النطق عند العرض.

## أدلة القبول

- الاختبارات الآلية: ملفات `test_task44_audio_files.py` و`test_task44_adapters.py` و`test_task44_presenter.py` و`test_task44_fallback_matrix.py`، إضافة إلى انحدار 4.1–4.3 والواجهة والإعدادات والترجمة والمعمارية.
- الاختبار الفعلي: `alert_presentation_task44_acceptance.json` يسجل نتائج NVDA 2026.2 للخدمات، WAV ذي 12 ثانية، التسلسل الزمني، fallback، وواجهة العربية والإنجليزية.
- التنفيذ لا يربط Scheduler تلقائياً بدورة حياة NVDA؛ هذا هو نطاق المهمة 5.1 التالية.
