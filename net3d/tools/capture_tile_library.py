"""
One-time capture of net3d's tile library: one clean tile per operator family,
photographed from TouchDesigner's own network editor at high zoom.

Every operator of a family has the same tile surface; only the viewer and
the name change. net3d draws each card from its family's template and puts
the live viewer and the name on top (see NetGraphExt._makeCard).

Run inside TouchDesigner with net3d built in /project1 (it uses net3d's
screen grab and calibrated editor mapping), TouchDesigner in front:

    d = op('/project1').create(textDAT, 'tile_capture')
    d.text = open('C:/path/to/td-components/net3d/tools/capture_tile_library.py').read()
    d.module.Start('C:/path/to/td-components/net3d/assets/tiles')

It writes <family>.png per family and tiles.json (tile size and the viewer
and name rectangles in tile pixels, origin top left), then removes its
temporary network.
"""

import json

import td

FAMILIES = [('TOP', 'levelTOP'), ('CHOP', 'nullCHOP'), ('SOP', 'boxSOP'), ('DAT', 'textDAT'),
            ('MAT', 'constantMAT'), ('POP', 'spherePOP'), ('COMP', 'baseCOMP')]
ZOOM = 4.0          # editor zoom while photographing: 4 px per network unit
SETTLE = 20         # frames for the grab to show the editor's new view
NET3D = '/project1/net3d'
TEMP = '/project1/tile_library'


def _pane():
    return [p for p in ui.panes if p.type == PaneType.NETWORKEDITOR][0]


def Start(folder):
    me.store('folder', folder)
    me.store('result', {})
    me.store('restore', None)
    old = op(TEMP)
    if old is not None:
        old.destroy()
    temp = op('/project1').create(baseCOMP, 'tile_library')
    for i, (fam, cls) in enumerate(FAMILIES):
        o = temp.create(getattr(td, cls), fam.lower())
        o.nodeX, o.nodeY = i * 400, 0
        o.viewer = False
        o.current = False
        o.selected = False
    pane = _pane()
    # where the editor was, unless a previous run left it on the temp network
    owner = pane.owner.path if pane.owner is not None and not pane.owner.path.startswith(TEMP) else '/project1'
    me.store('restore', (owner, pane.x, pane.y, pane.zoom))
    pane.owner = temp
    run("op({0!r}).module._wait(0)".format(me.path), delayFrames=SETTLE)


def _wait(tries):
    """Start once TouchDesigner is the foreground window (the grab records
    whatever is on top), giving up after ten minutes."""
    me.store('waiting', tries)
    if _front():
        _aim(0)
    elif tries < 600:
        run("op({0!r}).module._wait({1})".format(me.path, tries + 1), delayFrames=60)
    else:
        debug('tile capture: TouchDesigner never came to the front, stopped')
        _finish()


def _front():
    try:
        import ctypes
        import os
        user32 = ctypes.windll.user32
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        return pid.value == os.getpid()
    except Exception:
        return True


def _aim(i):
    o = op(TEMP).op(FAMILIES[i][0].lower())
    for x in op(TEMP).children:
        x.current = x.selected = False
    pane = _pane()
    pane.zoom = ZOOM
    pane.x = o.nodeX + o.nodeWidth * 0.5
    pane.y = o.nodeY + o.nodeHeight * 0.5
    run("op({0!r}).module._shoot({1})".format(me.path, i), delayFrames=SETTLE)


def _shoot(i, tries=0, settled=False):
    fam = FAMILIES[i][0]
    temp = op(TEMP)
    o = temp.op(fam.lower())
    pane = _pane()
    # the editor animates zoom and pan: shoot once it has arrived
    there = (abs(pane.zoom - ZOOM) < 0.005 and abs(pane.x - (o.nodeX + o.nodeWidth * 0.5)) < 0.5
             and abs(pane.y - (o.nodeY + o.nodeHeight * 0.5)) < 0.5)
    if not there and tries < 60:
        run("op({0!r}).module._shoot({1}, {2})".format(me.path, i, tries + 1), delayFrames=5)
        return
    if not settled:
        # arrived: give the screen grab time to show the still view
        run("op({0!r}).module._shoot({1}, {2}, True)".format(me.path, i, tries), delayFrames=SETTLE)
        return
    X = op(NET3D).ext.UILayerExt
    a = X.NetToWindow(o.nodeX, o.nodeY)
    b = X.NetToWindow(o.nodeX + o.nodeWidth, o.nodeY + o.nodeHeight)
    # wires can't cross COMPs: select net3d's grab, crop the tile, save it
    src = temp.op('grab') or temp.create(selectTOP, 'grab')
    src.par.top = NET3D + '/grab'
    crop = temp.op('tile') or temp.create(cropTOP, 'tile')
    crop.inputConnectors[0].connect(src)
    crop.par.cropleft, crop.par.cropright = a[0], b[0]
    crop.par.cropbottom, crop.par.croptop = a[1], b[1]
    crop.cook(force=True)
    crop.save('{}/{}.png'.format(me.fetch('folder'), fam))
    tile = crop.numpyArray()[::-1, :, :3]          # top down, RGB 0..1
    if abs(tile.shape[1] - o.nodeWidth * ZOOM) > 2 and tries < 60:
        # not the settled view yet: shoot again
        run("op({0!r}).module._shoot({1}, {2})".format(me.path, i, tries + 1), delayFrames=10)
        return
    res = me.fetch('result')
    res[fam] = _measure(tile, o.nodeWidth, o.nodeHeight)
    me.store('result', res)
    if i + 1 < len(FAMILIES):
        _aim(i + 1)
    else:
        _finish()


def _measure(tile, netw, neth):
    """Viewer and name rectangles in tile pixels (x0, y0, x1, y1, top left
    origin) from the photographed tile: the viewer is the large near-black
    area above the name strip, the name box runs from the strip's left
    edge to its first full-height separator."""
    import numpy
    hgt, wid, _ = tile.shape
    unit = hgt / float(neth)
    strip = int(round((neth - 18) * unit))      # TD's name strip: the bottom 18 units
    body = tile[:strip - int(round(2 * unit))]
    dark = body.sum(axis=2) < 0.36
    rows = numpy.where(dark.mean(axis=1) > 0.5)[0]
    cols = numpy.where(dark.mean(axis=0) > 0.5)[0]
    view = [int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1]
    inner = tile[strip + int(2 * unit):hgt - int(2 * unit)]
    sep = [x for x in range(int(4 * unit), wid) if inner[:, x].sum(axis=1).min() > 1.1]
    name = [int(round(unit)), strip + int(round(unit)), (sep[0] if sep else wid) - int(round(unit)), hgt - int(round(unit))]
    return {'netw': netw, 'neth': neth, 'w': wid, 'h': hgt, 'view': view, 'name': name}


def _finish():
    folder = me.fetch('folder')
    res = me.fetch('result') or {}
    if res:
        with open('{}/tiles.json'.format(folder), 'w', encoding='utf-8') as f:
            json.dump({'zoom': ZOOM, 'build': app.build, 'families': res}, f, indent=1)
    back = me.fetch('restore', None)
    if back is not None:
        pane = _pane()
        pane.owner = op(back[0]) or op('/project1')
        pane.x, pane.y, pane.zoom = back[1], back[2], back[3]
    t = op(TEMP)
    if t is not None:
        t.destroy()
    me.store('done', True)
