"""Inspect actual native message buttons inside the task-3 private NVDA.

Windows introspection reads the test process's own native modal only. Posted
native key messages test Enter/Escape on that private test desktop, not physical
keystrokes. WM_CLOSE is reserved for the owned-modal timeout cleanup.
"""
import ctypes
from ctypes import wintypes
import globalVars
from pathlib import Path
import sys
import wx

PROFILE=Path(globalVars.appArgs.configPath)
ROOT=Path((PROFILE/'source-root.txt').read_text(encoding='utf-8'))
sys.path.insert(0,str(ROOT/'tools'))
from calendar_converter_nvda_probe import GlobalPlugin as BaseProbe


class GlobalPlugin(BaseProbe):
	def inspect(self):
		d=self.dialog
		self.require(wx.Window.FindFocus() is d.source,'source focus before native messages')
		self.require(d.close_button.GetLabel()==d.texts.gettext('Close'),'main close label remains localized')
		self.require(self.obj(d.close_button).name==d.texts.gettext('Close'),'NVDA main close name localized')
		self.result['nativeMessages']=[]
		self.result['scope']='Actual Windows wx.MessageDialog/MSAA; native Enter/Escape key messages on owned buttons in a private desktop; no physical-key or human audio-listening claim.'
		d.show_result=d._message_result;d.show_error=d._message_error
		self.active_case=None
		for index,(kind,key) in enumerate((('result','Enter'),('result','Escape'),('error','Enter'),('error','Escape'))):
			d.entries['year'].ChangeValue('1448' if kind=='result' else '365')
			d.entries['year'].SetFocus()
			before=d.values()
			self.active_case=index;self.key_timed_out=False
			title=d.texts.gettext('Conversion result' if kind=='result' else 'Check the date')
			wx.CallLater(250,lambda title=title,key=key:self.guard(lambda:self.inspect_native(title,key)))
			d._convert()
			self.active_case=None
			self.require(not self.key_timed_out,kind+' native '+key+' dismisses message')
			self.require(d.values()==before,kind+' '+key+' preserves input fields')
			self.require(wx.Window.FindFocus() is d.entries['year'],kind+' '+key+' restores year focus')
			if kind=='error':
				self.require(d.entries['year'].GetStringSelection()=='365',key+' selects invalid year after error')
		d._close();self.dialog=None
		self.opener.SetFocus()
		wx.CallLater(300,lambda:self.guard(self.closed))

	def inspect_native(self,title,key):
		user=ctypes.WinDLL('user32',use_last_error=True)
		kernel=ctypes.WinDLL('kernel32',use_last_error=True)
		callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
		user.EnumThreadWindows.argtypes=[wintypes.DWORD,callback_type,wintypes.LPARAM]
		user.EnumChildWindows.argtypes=[wintypes.HWND,callback_type,wintypes.LPARAM]
		user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
		user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
		user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
		user.IsWindow.argtypes=[wintypes.HWND]
		def window_text(hwnd):
			buffer=ctypes.create_unicode_buffer(2048);user.GetWindowTextW(hwnd,buffer,len(buffer));return buffer.value
		windows=[]
		@callback_type
		def top(hwnd,data):
			if window_text(hwnd)==title:windows.append(hwnd)
			return True
		user.EnumThreadWindows(kernel.GetCurrentThreadId(),top,0)
		self.require(len(windows)==1,'one actual native '+title+' dialog')
		hwnd=windows[0]
		try:
			buttons=[];button_handles=[]
			from NVDAObjects.IAccessible import getNVDAObjectFromEvent
			@callback_type
			def child(child_hwnd,data):
				buffer=ctypes.create_unicode_buffer(128);user.GetClassNameW(child_hwnd,buffer,len(buffer))
				if buffer.value.lower()=='button':
					button_handles.append(child_hwnd)
					obj=getNVDAObjectFromEvent(child_hwnd,-4,0)
					buttons.append(dict(label=window_text(child_hwnd),nvda_name=obj.name if obj else None,
						nvda_role=obj.role.name if obj else None))
				return True
			user.EnumChildWindows(hwnd,child,0)
			self.result['nativeMessages'].append(dict(title=title,key=key,buttons=buttons))
			self.require(len(buttons)==1,'native message has exactly its existing OK button')
			expected=self.dialog.texts.gettext('OK')
			self.require(buttons[0]['label']==expected,'actual rendered button label '+expected)
			self.require(buttons[0]['nvda_name']==expected,'real NVDA button name '+expected)
			self.require(buttons[0]['nvda_role']=='BUTTON','native OK button role')
		except Exception:
			user.PostMessageW(hwnd,0x0010,0,0)
			raise
		case=self.active_case
		def timeout():
			if self.active_case==case and user.IsWindow(hwnd):
				self.key_timed_out=True
				user.PostMessageW(hwnd,0x0010,0,0)
		wx.CallLater(700,timeout)
		user.PostMessageW(button_handles[0],0x0100,0x0D if key=='Enter' else 0x1B,1)
