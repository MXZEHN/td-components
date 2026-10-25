def onFrameStart(frame):
    p = parent().par
    if p.Autorebuild.eval() and frame % 30 == 0:
        parent().ext.NetGraphExt.CheckChanged()
    return
