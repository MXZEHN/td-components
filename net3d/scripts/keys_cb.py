# Keyboard In DAT callbacks: every key goes to the UI layer's key display.
# Builds differ in the trailing arguments (cmd keys), hence *args.
def onKey(dat, key, character, alt, lAlt, rAlt, ctrl, lCtrl, rCtrl, shift, lShift, rShift, state, time, *args):
    cmd = bool(args[0]) if args else False
    parent().ext.UILayerExt.OnKey(key, character, ctrl=ctrl, shift=shift, alt=alt, cmd=cmd, state=state)
    return
