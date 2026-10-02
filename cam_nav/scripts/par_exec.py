def onPulse(par):
    ext = parent().ext.CamNavExt
    if par.name == 'Reset':
        ext.Reset()
    elif par.name == 'Sethome':
        ext.SetHome()
    return
