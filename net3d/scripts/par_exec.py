# Parameters that change the layout or the cards
UPDATE = ('Recurse', 'Scale', 'Layerspacing', 'Labelres', 'Viewerres', 'Previews', 'References')


def onPulse(par):
    ext = parent().ext.NetGraphExt
    if par.name == 'Rebuild':
        ext.Rebuild()
    elif par.name == 'Frameall':
        ext.Frame()
    return


def onValueChange(par, prev):
    ext = parent().ext.NetGraphExt
    if par.name == 'Target':
        ext.Rebuild()
    elif par.name in UPDATE:
        ext.Update(force=True)
    return
