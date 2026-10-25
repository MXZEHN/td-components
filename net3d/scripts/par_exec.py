REBUILD = ('Target', 'Recurse', 'Scale', 'Layerspacing', 'Labelres', 'Previews')


def onPulse(par):
    ext = parent().ext.NetGraphExt
    if par.name == 'Rebuild':
        ext.Rebuild()
    elif par.name == 'Frameall':
        ext.Frame()
    return


def onValueChange(par, prev):
    if par.name in REBUILD:
        parent().ext.NetGraphExt.Rebuild()
    return
