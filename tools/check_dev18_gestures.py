"""Official-source conflict scan and real Windows layout/native naming probes.

No keys are injected and no user configuration or input language is changed.
"""
import ast
import ctypes
from ctypes import wintypes
from enum import IntFlag
import hashlib
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace as NS

ROOT=Path(__file__).resolve().parents[1]

def norm(value):
    if not value.lower().startswith('kb') or ':' not in value:return None
    return frozenset(s.replace('ctrl','control') for s in value.lower().split(':',1)[1].split('+'))

def run():
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.LoadKeyboardLayoutW.argtypes=[wintypes.LPCWSTR,wintypes.UINT];user32.LoadKeyboardLayoutW.restype=wintypes.HKL
    user32.GetKeyboardLayout.argtypes=[wintypes.DWORD];user32.GetKeyboardLayout.restype=wintypes.HKL
    user32.MapVirtualKeyExW.argtypes=[wintypes.UINT,wintypes.UINT,wintypes.HKL];user32.MapVirtualKeyExW.restype=wintypes.UINT
    user32.ToUnicodeEx.argtypes=[wintypes.UINT,wintypes.UINT,ctypes.POINTER(ctypes.c_ubyte),wintypes.LPWSTR,ctypes.c_int,wintypes.UINT,wintypes.HKL]
    before=user32.GetKeyboardLayout(0)
    layouts={}
    for klid in ('00000409','00000401','00010401','00020401'):
        hkl=user32.LoadKeyboardLayoutW(klid,0x80)
        if not hkl:raise ctypes.WinError(ctypes.get_last_error())
        chars=[]
        for shifted in (False,True):
            state=(ctypes.c_ubyte*256)();state[16]=128 if shifted else 0
            buf=ctypes.create_unicode_buffer(8)
            n=user32.ToUnicodeEx(0xDC,0x2B,state,buf,8,4,hkl)
            chars.append(buf.value if n>0 else None)
        layouts[klid]={'handle':hkl,'plain':chars[0],'shift':chars[1]}
    source=(ROOT/'addon/globalPlugins/awqati/nvda_adapter/plugin.py').read_text('utf8')
    tree=ast.parse(source)
    gestures=[n.value.value for n in ast.walk(tree) if isinstance(n,ast.keyword) and n.arg=='gesture']
    targets={norm(g) for g in gestures}
    if len(targets)!=len(gestures):raise AssertionError('Duplicate default gesture')
    # Preserve the historical candidate scan in addition to every current default.
    candidates=targets|{norm('kb:NVDA+shift+\\'),norm('kb:NVDA+shift+ذ'),norm('kb:NVDA+|'),norm('kb:NVDA+control+alt+f12')}
    refs=json.loads((ROOT/'docs/stopwatch_open_gesture_audit.json').read_text('utf8'))['nvda']
    output={'date':'2026-11-03','defaults':gestures,'duplicateDefaults':False,'versions':[],
        'scope':'All official source Python literals and INI keys; native naming functions with real Windows layout APIs and controlled NVDA configuration. No live key interception, user or external add-on maps.',
        'layouts':{k:{n:v[n] for n in ('plain','shift')} for k,v in layouts.items()}}
    class NVDAKey(IntFlag):NUMPAD_INSERT=1;EXTENDED_INSERT=2;CAPS_LOCK=4
    for ref in refs:
        p=ROOT/'development_baseline/stopwatch-closure'/('release-'+ref['version']+'.tar.gz')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=ref['archiveSha256']:raise AssertionError('Source checksum')
        with tarfile.open(p) as tar:
            sources={m.name.split('/source/',1)[1]:tar.extractfile(m).read().decode('utf-8-sig') for m in tar.getmembers()
                if m.isfile() and '/source/' in m.name and m.name.endswith(('.py','.ini'))}
        findings=[]
        for name,text in sources.items():
            if name.endswith('.py'):
                values=[(n.lineno,n.value) for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
            else:
                values=[(i,v.strip().strip('"')) for i,line in enumerate(text.splitlines(),1) if '=' in line and not line.lstrip().startswith(('#',';')) for v in line.split('=',1)[0].split(',')]
            findings.extend({'file':name,'line':i,'gesture':v} for i,v in values if norm(v) in candidates)
        # The established F12 overlap is retained by the owner's instruction.
        unexpected=[f for f in findings if norm(f['gesture'])!=norm('kb:NVDA+f12')]
        if unexpected:raise AssertionError(unexpected)
        vk={};exec(compile(sources['vkCodes.py'],'official vkCodes','exec'),vk)
        kt=ast.parse(sources['keyboardHandler.py'])
        klass=next(n for n in kt.body if isinstance(n,ast.ClassDef) and n.name=='KeyboardInputGesture')
        names={'getVkName','_get_mainKeyName','_get_modifierNames','_get_identifiers'}
        methods=[n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name in names]
        is_nvda=next(n for n in kt.body if isinstance(n,ast.FunctionDef) and n.name=='isNVDAModifierKey')
        active=[None]
        ns={'vkCodes':NS(**vk),'winUser':NS(MAPVK_VK_TO_CHAR=2,VK_INSERT=45,VK_CAPITAL=20),
            'user32':NS(MapVirtualKeyEx=user32.MapVirtualKeyExW),'getInputHkl':lambda:active[0],
            'config':NS(conf={'keyboard':{'NVDAModifierKeys':7}}),'NVDAKey':NVDAKey}
        probe_cls=ast.ClassDef(name='Probe',bases=[],keywords=[],body=methods,decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[is_nvda,probe_cls],type_ignores=[])),'official naming','exec'),ns)
        probes=[]
        for klid,layout in layouts.items():
            active[0]=layout['handle']
            for mode in ('desktop','laptop'):
                for nvda_vk,extended in ((45,True),(45,False),(20,False)):
                    for modifiers in ((),(16,),(18,),(17,),(17,16),('windows',),('windows',16)):
                        for key,vkcode,scan in (('j',74,0x24),('y',89,0x15),('backslash',0xDC,0x2B)):
                            obj=ns['Probe']();obj.vkCode=vkcode;obj.scanCode=scan;obj.isExtended=False;obj.isNVDAModifierKey=False;obj.layout=mode
                            obj.generalizedModifiers={(nvda_vk,extended)}|{(m,False) for m in modifiers}
                            obj._keyNamesInDisplayOrder=tuple(obj._get_modifierNames())+(obj._get_mainKeyName(),)
                            identifiers=obj._get_identifiers()
                            expected={'nvda'}|{str(m) if isinstance(m,str) else {16:'shift',17:'control',18:'alt'}[m] for m in modifiers}|{(key if key in ('j','y') else chr(user32.MapVirtualKeyExW(vkcode,2,active[0])).lower())}
                            if norm(identifiers[1])!=frozenset(expected):raise AssertionError(identifiers)
                            probes.append({'layout':klid,'mode':mode,'nvdaKey':[nvda_vk,extended],'key':key,'identifiers':identifiers})
        output['versions'].append({'version':ref['version'],'commit':ref['commit'],'archiveSha256':ref['archiveSha256'],
            'sourceFiles':len(sources),'conflicts':findings,'unexpectedConflicts':unexpected,'namingProbes':probes})
    if before!=user32.GetKeyboardLayout(0):raise AssertionError('Input layout changed')
    output['activeInputLayoutUnchanged']=True
    output['probeCount']=sum(len(v['namingProbes']) for v in output['versions'])
    path=ROOT/'docs/countdown_dev18_gestures.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f"{len(gestures)} unique defaults; {output['probeCount']} naming probes passed; only retained F12 conflicts")

if __name__=='__main__':run()
