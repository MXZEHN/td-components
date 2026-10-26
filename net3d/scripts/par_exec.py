# Parameters that change the layout or the cards
UPDATE = ('Recurse', 'Scale', 'Layerspacing', 'Labelres', 'Viewerres', 'Previews', 'References', 'Tilesource', 'Annotations')


def onPulse(par):
    ext = parent().ext.NetGraphExt
    if par.name == 'Rebuild':
        ext.Rebuild()
    elif par.name == 'Frameall':
        ext.Frame()
    elif par.name == 'Capturetiles':
        debug('net3d: captured {} tile faces'.format(ext.CaptureTiles()))
    elif par.name == 'Retype':
        ext.RetypeAnnotations()
    elif par.name == 'Examine':
        # floating panel viewer: tumble, pan and zoom with the mouse
        v = parent().op('examine')
        if v is not None:
            v.openViewer()
    elif par.name == 'Examinehome':
        cam = parent().op('examine_cam/cameraViewport')
        if cam is not None:
            cam.ext.CameraExt.Home()
    return


def onValueChange(par, prev):
    ext = parent().ext.NetGraphExt
    if par.name == 'Target':
        ext.Rebuild()
    elif par.name in UPDATE:
        ext.Update(force=True)
    return
