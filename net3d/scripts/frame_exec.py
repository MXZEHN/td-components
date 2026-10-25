def onFrameStart(frame):
    parent().ext.NetGraphExt.Tick()
    parent().ext.UILayerExt.Tick()
    return
