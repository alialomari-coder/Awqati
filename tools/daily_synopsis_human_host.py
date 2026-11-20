"""Accessible acceptance workspace, loaded only in a synthetic NVDA profile.

Does not patch Awqati, intercept speech/keys, or record clipboard contents.
"""
import importlib
import json
from pathlib import Path
import time
import traceback
import core
import globalPluginHandler
import globalVars
import ui
import versionInfo
import wx


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self):
        super().__init__()
        self.profile = Path(globalVars.appArgs.configPath)
        if not self.profile.name.startswith('human32-'):
            raise RuntimeError('Human acceptance profile required')
        self.frame = None
        self.announced = False
        self.started = time.monotonic()
        wx.CallLater(2000, self.begin)

    def begin(self):
        try:
            import systemUtils
            if not systemUtils._getDesktopName().startswith('AwqatiHuman32_'):
                raise RuntimeError('Private acceptance desktop required')
            plugin = next(p for p in globalPluginHandler.runningPlugins
                if p.__module__.endswith('awqati.nvda_adapter.plugin'))
            if plugin._runtime is None:
                raise RuntimeError('Awqati is not ready')
            options = json.loads((self.profile/'session.json').read_text('utf-8'))
            self.frame = wx.Frame(None, title='أوقاتي: مساحة القبول البشري المعزولة', size=(760,540))
            panel = wx.Panel(self.frame)
            sizer = wx.BoxSizer(wx.VERTICAL)
            text = ('هذه جلسة اختبار مستقلة على NVDA 2026.1. الموقع: الرياض. '
                + ('الواجهة عربية. ' if options['language']=='ar' else 'الواجهة إنجليزية. ')
                + ('إدراج التراث مفعّل. ' if options['heritage'] else 'إدراج التراث معطّل. ')
                + 'للعودة فورًا في أي وقت: Control مع Alt مع F10. العودة تلقائية بعد عشر دقائق. '
                'اختبر NVDA مع Control مع H مرة للنبذة، ومرتين للتراث، وثلاث مرات للنافذة. '
                'داخل النافذة جرّب التحديد والنسخ والتنقل، ثم Escape. '
                'بعد الإغلاق يعود التركيز إلى مساحة اللصق هنا؛ اضغط Control مع V لمراجعة ما نسخته. '
                'يمكنك كذلك استعمال NVDA مع F12 ثلاث مرات لسماع النص المدمج. '
                'لا تكتب بيانات شخصية؛ حافظة Windows مشتركة مع جلستك المعتادة، وسيستبدل النسخ محتواها.')
            label = wx.StaticText(panel,label='تعليمات الاختبار')
            instructions = wx.TextCtrl(panel,value=text,style=wx.TE_MULTILINE|wx.TE_READONLY,name='تعليمات الاختبار')
            paste_label = wx.StaticText(panel,label='مساحة لصق النص المنسوخ ومراجعته')
            self.paste = wx.TextCtrl(panel,style=wx.TE_MULTILINE,name='مساحة لصق النص المنسوخ ومراجعته')
            back = wx.Button(panel,label='إنهاء الاختبار والعودة إلى NVDA المعتاد')
            for item,weight in ((label,0),(instructions,1),(paste_label,0),(self.paste,1),(back,0)):
                sizer.Add(item,weight,wx.ALL|wx.EXPAND,8)
            panel.SetSizer(sizer)
            self.frame.Bind(wx.EVT_CLOSE,lambda e:self.request_return())
            back.Bind(wx.EVT_BUTTON,lambda e:self.request_return())
            self.frame.Show()
            self.paste.SetFocus()
            self.timer = wx.Timer(self.frame)
            self.frame.Bind(wx.EVT_TIMER,self.tick,self.timer)
            self.timer.Start(200)
            (self.profile/'host-ready.json').write_text(json.dumps(dict(
                ready=True,nvdaVersion=versionInfo.version,awqatiModule=plugin.__module__,
                language=options['language'],heritage=options['heritage'],
                humanAcceptance=None,sourceOnly=True)), 'utf-8')
        except Exception:
            (self.profile/'host-error.txt').write_text(traceback.format_exc(),'utf-8')
            core.triggerNVDAExit()

    def request_return(self):
        (self.profile/'return.request').touch()

    def tick(self,event):
        if (self.profile/'stop.request').exists():
            self.timer.Stop()
            core.triggerNVDAExit()
            return
        # Announce after the user actually switches, never steal the old desktop.
        import ctypes
        from ctypes import wintypes
        user=ctypes.WinDLL('user32')
        user.OpenInputDesktop.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        user.OpenInputDesktop.restype=wintypes.HANDLE
        user.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
        user.CloseDesktop.argtypes=[wintypes.HANDLE]
        handle=user.OpenInputDesktop(0,False,1)
        if not handle:return
        try:
            name=ctypes.create_unicode_buffer(256);needed=wintypes.DWORD()
            if not user.GetUserObjectInformationW(handle,2,name,ctypes.sizeof(name),ctypes.byref(needed)):return
            if name.value != json.loads((self.profile/'session.json').read_text('utf-8'))['desktop']:return
        finally:user.CloseDesktop(handle)
        if not self.announced:
            self.announced=True
            self.frame.Raise()
            self.paste.SetFocus()
            ui.message('بدأت جلسة أوقاتي المعزولة. العودة فورًا: Control Alt F10. التركيز في مساحة اللصق. استخدم اختصارات النبذة المعتادة.')

    def terminate(self):
        if hasattr(self,'timer'):self.timer.Stop()
        if self.frame and not self.frame.IsBeingDeleted():self.frame.Destroy()
