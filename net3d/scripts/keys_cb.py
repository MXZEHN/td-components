# Keyboard In DAT callbacks: every key goes to the UI layer's key display.
# 2025 builds pass one keyInfo namedtuple, older builds pass the fields.
def onKey(dat, *args):
    if len(args) == 1:
        k = args[0]
        parent().ext.UILayerExt.OnKey(k.key, k.character, ctrl=k.ctrl, shift=k.shift, alt=k.alt,
                                      cmd=getattr(k, 'cmd', False), state=k.state)
        return
    key, character, alt, lAlt, rAlt, ctrl, lCtrl, rCtrl, shift, lShift, rShift, state, time = args[:13]
    cmd = bool(args[13]) if len(args) > 13 else False
    parent().ext.UILayerExt.OnKey(key, character, ctrl=ctrl, shift=shift, alt=alt, cmd=cmd, state=state)
    return

def onShortcut(dat, shortcutName, time):
    return
