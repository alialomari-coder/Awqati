"""Own the Awqati Tools menu independently of optional services."""
import addonHandler
import gui
import wx

addonHandler.initTranslation()


class ClockToolsMenu:
    def __init__(self, open_tool, actions=None):
        self.open_tool = open_tool
        self.closed = False
        self.pending = None
        self.menu = wx.Menu()
        self.actions = actions or {}
        self.commands = {}
        if actions is not None:
            self.append(self.menu, "prayers", _("Today's prayer times"))
        self.tools = wx.Menu()
        self.items = {}
        for identity, label in (("alarms", _("Alarms")), ("timers", _("Timers")),
                ("stopwatch", _("Stopwatch")), ("world_clock", _("World clock"))):
            item = self.tools.Append(wx.ID_ANY, label)
            self.items[identity] = item
            self.tools.Bind(wx.EVT_MENU, lambda event, key=identity: self.queue(key), item)
        self.menu.AppendSubMenu(self.tools, _("Clock Tools"))
        if actions is not None:
            self.append(self.menu, "converter", _("Date converter"))
            self.append(self.menu, "daily", _("Daily information"))
            self.day_menu = wx.Menu()
            for key, label in (("events", _("Events")), ("births", _("Births")),
                    ("deaths", _("Deaths")), ("observances", _("Holidays and observances"))):
                self.append(self.day_menu, key, label)
            self.menu.AppendSubMenu(self.day_menu, _("On This Day"))
            self.weather_menu = wx.Menu()
            for key, label in (("current", _("Current weather")), ("today", _("Today's forecast")),
                    ("future", _("Coming days forecast"))):
                self.append(self.weather_menu, key, label)
            self.menu.AppendSubMenu(self.weather_menu, _("Weather"))
        self.parent = gui.mainFrame.sysTrayIcon.toolsMenu
        # A stale owner may survive a plugin reload. Close it before replacing it.
        previous = getattr(gui.mainFrame.sysTrayIcon, "_awqati_menu_owner", None)
        if previous is not None:
            previous.close()
        self.item = self.parent.AppendSubMenu(self.menu, _("Awqati"))
        gui.mainFrame.sysTrayIcon._awqati_menu_owner = self

    def append(self, menu, key, label):
        item = menu.Append(wx.ID_ANY, label)
        self.commands[key] = item
        menu.Bind(wx.EVT_MENU, lambda event, key=key: self.queue(key), item)

    def queue(self, identity):
        if self.closed:
            return
        if self.pending:
            self.pending.Stop()
        # Let the native tray/menu loop finish restoring foreground focus.
        self.pending = wx.CallLater(150, self.dispatch, identity)

    def dispatch(self, identity):
        self.pending = None
        if not self.closed:
            try:
                if identity in self.actions:
                    self.actions[identity]()
                else:
                    self.open_tool(identity)
            except Exception:
                import logHandler
                import ui
                logHandler.log.exception("Awqati menu command failed: %s", identity)
                ui.message(_("This Awqati service is unavailable. Other services remain available."))

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.pending:
            self.pending.Stop()
            self.pending = None
        self.parent.DestroyItem(self.item)
        if getattr(gui.mainFrame.sysTrayIcon, "_awqati_menu_owner", None) is self:
            gui.mainFrame.sysTrayIcon._awqati_menu_owner = None
