"""
Demo animation for net3d: a small network built one operator at a time,
recorded from net3d's 3D render.

In TouchDesigner, with net3d built in /project1:

    d = op('/project1').create(textDAT, 'demo_build')
    d.text = open('C:/path/to/td-components/net3d/demo/build_demo.py').read()
    d.module.Start(record=True, file='C:/path/to/net3d_demo.mp4')

Start() resets /project1/demo, points net3d at it (Live, Follow camera,
drawn tiles, UI layer off) and schedules one step every STEP frames.
With record=True a Movie File Out TOP writes the render, in realtime (out of
realtime the render came out empty in TD 2025.33230). Restore() puts net3d back.
"""

STEP = 45          # frames between steps
DWELL = 210        # frames on the annotation while it types on
HOLD = 180         # frames to ease out to the whole network and hold it
NET3D = '/project1/net3d'
DEMO = '/project1/demo'
REC = '/project1/demo_rec'

# what Start() changes on net3d, to put back afterwards
_SAVE = ('Target', 'Live', 'Livepoll', 'Cameramode', 'Uilayer', 'Tilesource', 'Previews', 'Highlight')


def _add(kind, name, x, y, src=None, **pars):
    demo = op(DEMO)
    o = demo.create(kind, name)
    o.nodeX, o.nodeY = x, y
    if src is not None:
        o.inputConnectors[0].connect(demo.op(src))
    for k, v in pars.items():
        setattr(o.par, k, v)
    return o


def _step0():
    _add(noiseTOP, 'noise1', 0, 0, monochrome=False, period=2)


def _step1():
    _add(levelTOP, 'level1', 200, 0, 'noise1', contrast=1.6)


def _step2():
    _add(lfoCHOP, 'lfo1', 0, -220, frequency=0.25)


def _step3():
    _add(nullCHOP, 'null_lfo', 200, -220, 'lfo1')


def _step4():
    _add(transformTOP, 'transform1', 400, 0, 'level1')


def _step4b():
    # its own beat: the CHOP starts driving the TOP's Rotate parameter
    op(DEMO).op('transform1').par.rotate.expr = "op('null_lfo')['chan1'] * 45"


def _step5():
    _add(rampTOP, 'ramp1', 400, 180)


def _step6():
    c = _add(compositeTOP, 'comp1', 600, 0, 'transform1', operand='multiply')
    c.inputConnectors[1].connect(op(DEMO).op('ramp1'))


def _step7():
    o = _add(nullTOP, 'null_out', 800, 0, 'comp1')
    o.viewer = True


def _step8():
    a = op(DEMO).create(annotateCOMP, 'note1')
    a.nodeX, a.nodeY, a.nodeWidth, a.nodeHeight = -40, 300, 900, 160
    for name, value in (('Titletext', 'Animated noise'),
                        ('Bodytext', 'noise -> level -> transform, rotated by an LFO, tinted by a ramp.')):
        if hasattr(a.par, name):
            setattr(a.par, name, value)


STEPS = [_step0, _step1, _step2, _step3, _step4, _step4b, _step5, _step6, _step7, _step8]
# frames to wait before a step when it needs longer than STEP: the new
# reference gets time for the camera, the pulses and its parameter tag
WAIT = {_step5: 150}


def Step(i):
    STEPS[i]()


def Start(record=False, file=''):
    n = op(NET3D)
    # keep the user's settings from before the first run, not a previous demo's
    if me.fetch('saved', None) is None:
        me.store('saved', {k: getattr(n.par, k).eval() for k in _SAVE})
    old = op(DEMO)
    if old is not None:
        old.destroy()
    demo = op('/project1').create(baseCOMP, 'demo')
    demo.nodeX, demo.nodeY = -400, 400
    n.par.Target = demo
    n.par.Live, n.par.Livepoll = True, 1
    n.par.Cameramode = 'follow'
    n.par.Uilayer = False
    n.par.Tilesource = 'drawn'
    n.par.Previews = 'all'
    # every new operator becomes current: a green rim like the editor's outline
    n.par.Highlight = True
    n.ext.NetGraphExt.Rebuild()
    for o in op('/project1').findChildren(name='demo_rec*', depth=1) + op('/project1').findChildren(name='demo_src*', depth=1):
        o.destroy()
    if record:
        src = op('/project1').create(selectTOP, 'demo_src')
        src.par.top = NET3D + '/render'
        rec = op('/project1').create(moviefileoutTOP, 'demo_rec')
        rec.inputConnectors[0].connect(src)
        rec.par.file = file
        rec.par.type = 'movie'
        rec.par.videocodec = 'h264'
        rec.par.moviecontainer = 'mp4'
        src.nodeX, src.nodeY, rec.nodeX, rec.nodeY = -400, 250, -200, 250
        rec.par.record = True
    path = me.path
    t = 0
    for i, step in enumerate(STEPS):
        t += WAIT.get(step, STEP)
        run("op({0!r}).module.Step({1})".format(path, i), delayFrames=t)
    end = t + DWELL
    run("op({0!r}).module.FrameAll()".format(path), delayFrames=end)
    run("op({0!r}).module.Finish()".format(path), delayFrames=end + HOLD)
    return end + HOLD


def FrameAll():
    op(NET3D).ext.NetGraphExt.Frame(smooth=True)


def Finish():
    rec = op(REC)
    if rec is not None:
        rec.par.record = False
    me.store('done', True)


def Restore():
    n = op(NET3D)
    for k, v in (me.fetch('saved', {}) or {}).items():
        try:
            getattr(n.par, k).val = v
        except Exception:
            pass
    for o in op('/project1').findChildren(name='demo_rec*', depth=1) + op('/project1').findChildren(name='demo_src*', depth=1):
        o.destroy()
    me.unstore('saved')
