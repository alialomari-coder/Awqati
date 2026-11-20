"""Native keyboard-accessible world-clock views; painting never speaks or moves focus."""
import addonHandler
import ui
import wx
from .countdown_dialog import direction
from .native_accessibility import set_list_name

addonHandler.initTranslation()


class SelectedCityList(wx.ListCtrl):
    def __init__(self,parent,control):
        super().__init__(parent,style=wx.LC_REPORT|wx.LC_SINGLE_SEL|wx.LC_VIRTUAL,size=(750,270),name=_('Selected cities'))
        self.control=control
        self.texts=()
        self.InsertColumn(0,_('City time and local time difference'),width=1000)
        set_list_name(self,_('Selected cities'))

    def OnGetItemText(self,item,column):
        # Windows/NVDA may request this synchronously while handling focus.
        # Never calculate times, access files, select items or speak here.
        return self.texts[item] if 0<=item<len(self.texts) else ''

    def update_texts(self):
        texts=[]
        for city in self.control.service.rows:
            try:texts.append(self.control.text(city))
            except (OSError,ValueError,KeyError):
                texts.append(self.control.city_name(city)+', '+_('The city time is unavailable. Existing data were preserved.'))
        self.texts=tuple(texts)
        self.Refresh(False)


class EditCityNameDialog(wx.Dialog):
    def __init__(self,parent,control,city):
        super().__init__(parent,title=_('Edit name'))
        direction(self);self.control=control;self.city=city;self.language=control.language()
        box=wx.BoxSizer(wx.VERTICAL)
        city_name,country_name=control.service.names(city,self.language)
        box.Add(wx.StaticText(self,label=_('City name:')),flag=wx.ALL,border=5)
        self.city_name=wx.TextCtrl(self,value=city_name,name=_('City name:'))
        box.Add(self.city_name,flag=wx.ALL|wx.EXPAND,border=5)
        box.Add(wx.StaticText(self,label=_('Country name:')),flag=wx.ALL,border=5)
        self.country_name=wx.TextCtrl(self,value=country_name,name=_('Country name:'))
        box.Add(self.country_name,flag=wx.ALL|wx.EXPAND,border=5)
        save=wx.Button(self,wx.ID_SAVE,label=_('Save'))
        cancel=wx.Button(self,wx.ID_CANCEL,label=_('Cancel'))
        restore=wx.Button(self,label=_('Restore original names'))
        save.Bind(wx.EVT_BUTTON,self.save);restore.Bind(wx.EVT_BUTTON,self.restore)
        for button in (save,cancel,restore):box.Add(button,flag=wx.ALL,border=5)
        save.SetDefault();self.SetSizerAndFit(box);self.city_name.SetFocus();self.city_name.SelectAll()

    def restore(self,event):
        city=self.control.service.catalog.cities.get(self.city.city_id,self.city)
        names=(city.name_ar,city.country_ar) if self.language=='ar' else (city.name_en,city.country_en)
        self.city_name.SetValue(names[0]);self.country_name.SetValue(names[1]);self.city_name.SetFocus()

    def save(self,event):
        try:self.control.service.edit_names(self.city.city_id,self.language,self.city_name.GetValue(),self.country_name.GetValue())
        except ValueError:
            wx.MessageBox(_('Enter a city name and a country name, each from 1 to 160 characters, without control characters.'),_('Edit name'),wx.OK|wx.ICON_ERROR,self)
            return
        except OSError:self.control.save_error();return
        self.control.refresh(self.city.city_id)
        self.EndModal(wx.ID_OK)


class AddCityDialog(wx.Dialog):
    def __init__(self,parent,control):
        super().__init__(parent,title=_('Add city'))
        direction(self);self.control=control;self.pending=None
        box=wx.BoxSizer(wx.VERTICAL)
        box.Add(wx.StaticText(self,label=_('Search for a city:')),flag=wx.ALL,border=5)
        self.query=wx.TextCtrl(self,name=_('Search for a city'))
        box.Add(self.query,flag=wx.ALL|wx.EXPAND,border=5)
        self.available=wx.ListBox(self,size=(600,300),name=_('Available cities'))
        set_list_name(self.available,_('Available cities'))
        box.Add(self.available,proportion=1,flag=wx.ALL|wx.EXPAND,border=5)
        add=wx.Button(self,label=_('Add'));close=wx.Button(self,wx.ID_CANCEL,label=_('Close'))
        add.Bind(wx.EVT_BUTTON,self.add)
        box.Add(add,flag=wx.ALL,border=5);box.Add(close,flag=wx.ALL,border=5)
        self.query.Bind(wx.EVT_TEXT,self.changed)
        self.Bind(wx.EVT_WINDOW_DESTROY,self.destroyed)
        self.SetSizerAndFit(box);self.filter();self.query.SetFocus()

    def changed(self,event):
        if self.pending:self.pending.Stop()
        self.pending=wx.CallLater(120,self.filter)
        event.Skip()

    def filter(self):
        self.pending=None
        self.rows=self.control.service.catalog.search(self.query.GetValue(),self.control.language())
        self.available.Set([c.label(self.control.language()) for c in self.rows])
        if self.rows:self.available.SetSelection(0)

    def add(self,event):
        index=self.available.GetSelection()
        if index!=wx.NOT_FOUND:self.control.add(self.rows[index])

    def destroyed(self,event):
        if event.GetEventObject() is self and self.pending:self.pending.Stop()
        event.Skip()


class WorldClockPanel(wx.Panel):
    def __init__(self,parent,control):
        super().__init__(parent);direction(self);self.control=control;control.dialog=self
        box=wx.BoxSizer(wx.VERTICAL)
        self.list=SelectedCityList(self,control)
        box.Add(self.list,flag=wx.ALL|wx.EXPAND,border=5)
        add=wx.Button(self,label=_('Add city'));update=wx.Button(self,label=_('Update data'))
        add.Bind(wx.EVT_BUTTON,self.add);update.Bind(wx.EVT_BUTTON,lambda e:control.update())
        box.Add(add,flag=wx.ALL,border=5);box.Add(update,flag=wx.ALL,border=5)
        self.automatic=wx.CheckBox(self,label=_('Update data automatically'),name=_('Update data automatically'))
        self.automatic.SetValue(control.policy.enabled)
        def automatic_changed(event):
            if not control.set_automatic(self.automatic.GetValue()):self.automatic.SetValue(control.policy.enabled)
        self.automatic.Bind(wx.EVT_CHECKBOX,automatic_changed)
        box.Add(self.automatic,flag=wx.ALL,border=5)
        self.SetSizer(box)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED,self.selected)
        self.list.Bind(wx.EVT_CHAR_HOOK,self.key)
        self.list.Bind(wx.EVT_CONTEXT_MENU,self.context)
        self.Bind(wx.EVT_WINDOW_DESTROY,self.destroyed)
        self.timer=wx.Timer(self);self.Bind(wx.EVT_TIMER,lambda e:self.list.update_texts(),self.timer);self.timer.Start(1000)
        self.refresh()

    def refresh(self):
        rows=self.control.service.rows
        self.list.update_texts()
        self.list.SetItemCount(len(rows))
        index=next((i for i,c in enumerate(rows) if c.city_id==self.control.selected_id),0 if rows else -1)
        if index>=0:
            self.list.Select(index);self.list.Focus(index)
            self.control.selected_id=rows[index].city_id
        self.list.Refresh(False)

    def index(self):return self.list.GetFirstSelected()

    def selected(self,event):
        if 0<=event.GetIndex()<len(self.control.service.rows):
            self.control.selected_id=self.control.service.rows[event.GetIndex()].city_id
        event.Skip()

    def add(self,event):
        with AddCityDialog(self,self.control) as dialog:dialog.ShowModal()
        self.list.SetFocus()

    def move(self,step):
        index=self.index()
        if index<0:return
        try:target=self.control.service.move(index,step)
        except (OSError,ValueError):self.control.save_error();return
        if target==index:return
        city=self.control.service.rows[target]
        self.control.refresh(city.city_id)
        ui.message(_('{city}, position {position}.').format(city=self.control.city_name(city),position=target+1))
        self.list.SetFocus()

    def delete(self):
        index=self.index()
        if index<0:return
        city=self.control.service.rows[index]
        if wx.MessageBox(_('Delete {city} from the world clock?').format(city=self.control.city_name(city)),
                _('World clock'),wx.YES_NO|wx.CANCEL|wx.NO_DEFAULT|wx.ICON_QUESTION,self)!=wx.YES:
            self.list.SetFocus();return
        try:self.control.service.delete(index)
        except (OSError,ValueError):self.control.save_error();self.list.SetFocus();return
        rows=self.control.service.rows
        self.control.selected_id=rows[min(index,len(rows)-1)].city_id if rows else None
        self.refresh();self.list.SetFocus()

    def key(self,event):
        code=event.GetKeyCode()
        if event.ControlDown() and code in (wx.WXK_UP,wx.WXK_DOWN):self.move(-1 if code==wx.WXK_UP else 1)
        elif code==wx.WXK_DELETE:self.delete()
        elif code==wx.WXK_WINDOWS_MENU or (code==wx.WXK_F10 and event.ShiftDown()):self.context()
        else:event.Skip()

    def edit_name(self):
        index=self.index()
        if index<0:return
        with EditCityNameDialog(self,self.control,self.control.service.rows[index]) as dialog:dialog.ShowModal()
        self.list.SetFocus()

    def context(self,event=None):
        if event is not None and event.GetPosition()!=wx.Point(-1,-1):
            index=self.list.HitTest(self.list.ScreenToClient(event.GetPosition()))[0]
            if index>=0:self.list.Select(index);self.list.Focus(index)
        index=self.index();count=len(self.control.service.rows)
        menu=wx.Menu()
        for label,enabled,action in ((_('Move up'),index>0,lambda:self.move(-1)),
                (_('Move down'),0<=index<count-1,lambda:self.move(1)),
                (_('Delete city'),index>=0,self.delete),
                (_('Edit name'),index>=0,self.edit_name)):
            item=menu.Append(wx.ID_ANY,label);item.Enable(enabled)
            menu.Bind(wx.EVT_MENU,lambda e,action=action:action(),item)
        try:self.list.PopupMenu(menu)
        finally:menu.Destroy();self.list.SetFocus()

    def destroyed(self,event):
        if event.GetEventObject() is self:
            self.timer.Stop()
            if self.control.dialog is self:self.control.dialog=None
        event.Skip()
