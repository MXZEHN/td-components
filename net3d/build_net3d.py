"""
Build the net3d component inside a running TouchDesigner session.

In the Textport (Alt+T), or through a TD MCP 'run python' tool:

    exec(open('C:/path/to/td-components/net3d/build_net3d.py').read())
    build(op('/project1'), 'C:/path/to/td-components/net3d/scripts')

The scripts are copied into the DATs (no file sync), so the result can be
saved straight away with  op('/project1/net3d').save('net3d.tox').
"""

import os

SCRIPTS = {
    'NetGraphExt': 'NetGraphExt.py',
    'UILayerExt': 'UILayerExt.py',
    'ui_cb': 'ui_cb.py',
    'tiles_cb': 'tiles_cb.py',
    'keys_cb': 'keys_cb.py',
    'inst_cb': 'inst_cb.py',
    'notes_cb': 'notes_cb.py',
    'conn_cb': 'conn_cb.py',
    'flags_cb': 'flags_cb.py',
    'wires_cb': 'wires_cb.py',
    'quad_cb': 'quad_cb.py',
    'frame_exec': 'frame_exec.py',
    'par_exec': 'par_exec.py',
}

COLORS = [
    ('bg', 0.20, 0.20, 0.20),
    ('TOP', 0.45, 0.33, 0.62),
    ('CHOP', 0.33, 0.55, 0.30),
    ('SOP', 0.28, 0.42, 0.66),
    ('DAT', 0.66, 0.32, 0.52),
    ('MAT', 0.70, 0.60, 0.24),
    ('COMP', 0.50, 0.50, 0.50),
    ('POP', 0.76, 0.44, 0.22),
    ('tile', 0.30, 0.30, 0.30),
    ('text', 0.90, 0.90, 0.90),
    ('bypass', 0.35, 0.35, 0.35),
    ('annotate', 0.30, 0.30, 0.30),
    ('type', 0.60, 0.60, 0.60),
    ('frame', 0.25, 0.25, 0.25),
    ('hier', 0.80, 0.80, 0.80),
    ('strip', 0.16, 0.16, 0.16),
    ('current', 0.95, 0.80, 0.30),
    ('selected', 0.85, 0.85, 0.85),
    ('flag_bypass', 0.90, 0.75, 0.20),
    ('flag_lock', 0.85, 0.30, 0.30),
    ('flag_display', 0.30, 0.60, 0.95),
    ('flag_render', 0.70, 0.40, 0.90),
    ('flag_viewer', 0.85, 0.85, 0.85),
    ('flag_error', 0.90, 0.20, 0.20),
    ('flag_warning', 0.95, 0.75, 0.10),
    ('hover', 0.75, 0.75, 0.75),
]

# Window regions TD does not report as panes, in window UV (origin bottom
# left). Rough defaults; calibrate with UI Debug against the grab.
REGIONS = [
    ('name', 'u0', 'v0', 'u1', 'v1', 'trigger'),
    ('timeline', 0.0, 0.0, 1.0, 0.045, 'time'),
    ('menubar', 0.0, 0.97, 1.0, 1.0, 'always'),
]

# Popups opened over the editor: pixels, anchor = top-left corner relative
# to the click.
POPUPS = [
    ('kind', 'w', 'h', 'dx', 'dy'),
    ('context', 260, 420, 0, 0),
    ('create', 680, 470, -340, 235),
    ('info', 380, 280, 10, 0),
]

# network-editor units, see DEFAULT_TILE in NetGraphExt
TILE = [
    ('border', 3), ('namestrip', 18), ('namesize', 11), ('typesize', 16),
    ('titlesize', 16), ('flagw', 7), ('flagh', 12), ('conn', 8),
]


def _clearChildren(comp):
    for c in list(comp.children):
        c.destroy()


def _scriptOp(comp, opType, name, cbName, x, y):
    o = comp.create(opType, name)
    # Script OPs create their own '<name>_callbacks' DAT; use ours instead
    auto = comp.op(name + '_callbacks')
    o.par.callbacks = cbName
    if auto is not None:
        auto.destroy()
    o.nodeX, o.nodeY = x, y
    return o


def _instancedGeo(comp, name, sop, chop, mat, x, y):
    geo = comp.create(geometryCOMP, name)
    _clearChildren(geo)
    sel = geo.create(selectSOP, 'in')
    sel.par.sop = '../' + sop.name
    sel.render = sel.display = True
    geo.par.material = mat.name
    geo.par.instancing = True
    geo.par.instanceop = chop.name
    for p in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz'):
        setattr(geo.par, 'instance' + p, p)
    # instance colour parameter names changed across builds
    for prefix in ('instance', 'instancecolor'):
        if hasattr(geo.par, prefix + 'r'):
            getattr(geo.par, prefix + 'r').val = 'r'
            getattr(geo.par, prefix + 'g').val = 'g'
            getattr(geo.par, prefix + 'b').val = 'b'
            if hasattr(geo.par, prefix + 'a'):
                getattr(geo.par, prefix + 'a').val = 'a'
            break
    geo.nodeX, geo.nodeY = x, y
    return geo


def _customPars(comp):
    page = comp.appendCustomPage('Net3D')
    page.appendCOMP('Target', label='Target')
    page.appendPulse('Rebuild', label='Rebuild')
    p = page.appendToggle('Autorebuild', label='Auto Rebuild')[0]; p.default = True; p.val = True
    p = page.appendInt('Recurse', label='Recurse Depth')[0]; p.default = 0; p.normMax = 4; p.clampMin = True
    p = page.appendFloat('Scale', label='Scale')[0]; p.default = p.val = 0.01; p.normMax = 0.05
    p = page.appendFloat('Depth', label='Node Depth')[0]; p.default = p.val = 0.12; p.normMax = 1
    p = page.appendFloat('Wirewidth', label='Wire Width')[0]; p.default = p.val = 0.035; p.normMax = 0.2
    p = page.appendInt('Wiresegs', label='Wire Segments')[0]; p.default = p.val = 32; p.normMax = 64
    p = page.appendFloat('Layerspacing', label='Layer Spacing')[0]; p.default = p.val = 8; p.normMax = 20
    p = page.appendToggle('Hierlinks', label='Hierarchy Wires')[0]; p.default = p.val = True
    p = page.appendToggle('References', label='Reference Wires')[0]; p.default = p.val = True
    p = page.appendToggle('Framelinks', label='Frame Guides')[0]; p.default = p.val = False
    p = page.appendMenu('Previews', label='TOP Previews')[0]
    p.menuNames = ['all', 'tops', 'viewer', 'none']
    p.menuLabels = ['All Operators', 'TOPs Only', 'Viewer Active Only', 'None (Type Labels)']
    p.default = p.val = 'all'
    p = page.appendFloat('Viewerres', label='Viewer Resolution')[0]; p.default = p.val = 2; p.normMin = 0.5; p.normMax = 4
    p = page.appendMenu('Tilesource', label='Tile Source')[0]
    p.menuNames = ['drawn', 'captured']
    p.menuLabels = ['Drawn', 'Captured from Editor']
    p.default = p.val = 'captured'
    p = page.appendFloat('Labelres', label='Label Resolution')[0]; p.default = p.val = 3; p.normMin = 0.5; p.normMax = 6
    p = page.appendToggle('Highlight', label='Highlight Current')[0]; p.default = p.val = True

    page = comp.appendCustomPage('Animate')
    p = page.appendFloat('Reveal', label='Reveal')[0]; p.default = p.val = 1; p.clampMin = p.clampMax = True
    p = page.appendFloat('Explode', label='Explode')[0]; p.default = p.val = 0; p.normMax = 5
    p = page.appendFloat('Layeropacity', label='Layer Opacity')[0]; p.default = p.val = 0.35; p.clampMin = p.clampMax = True
    p = page.appendMenu('Annotations', label='Annotations')[0]
    p.menuNames = ['typewriter', 'static']
    p.menuLabels = ['Type On First Approach', 'Static']
    p.default = p.val = 'typewriter'
    p = page.appendFloat('Typespeed', label='Type Speed')[0]; p.default = p.val = 30; p.normMax = 120
    p = page.appendFloat('Approach', label='Approach')[0]; p.default = p.val = 0.2; p.clampMin = p.clampMax = True
    page.appendPulse('Retype', label='Retype Annotations')
    p = page.appendFloat('Frontopacity', label='Front Opacity')[0]; p.default = p.val = 0.08; p.clampMin = p.clampMax = True
    p = page.appendFloat('Focuslevel', label='Focus Level')[0]; p.default = p.val = 0; p.normMax = 4

    page = comp.appendCustomPage('Live')
    p = page.appendToggle('Live', label='Live')[0]; p.default = p.val = False
    p = page.appendInt('Livepoll', label='Poll Every N Frames')[0]; p.default = p.val = 3; p.normMin = 1; p.normMax = 30
    p = page.appendFloat('Birthtime', label='Birth Time')[0]; p.default = p.val = 0.6; p.normMax = 3
    p = page.appendToggle('Follow', label='Camera Follows')[0]; p.default = p.val = True
    p = page.appendXYZ('Followoffset', label='Follow Offset')
    for par_, v in zip(p, (0.6, -0.4, 3.0)):
        par_.default = par_.val = v
    p = page.appendFloat('Followsmooth', label='Follow Smooth')[0]; p.default = p.val = 0.5; p.normMax = 3
    p = page.appendToggle('Followeditor', label='Follow Editor')[0]; p.default = p.val = True
    p = page.appendFloat('Transitiontime', label='Dive Time')[0]; p.default = p.val = 1.2; p.normMax = 4

    page = comp.appendCustomPage('UI Layer')
    p = page.appendToggle('Uilayer', label='UI Layer')[0]; p.default = p.val = True
    p = page.appendMenu('Chrome', label='TD Chrome')[0]
    p.menuNames = ['editor', 'float', 'off']
    p.menuLabels = ['Around the Editor (like TD)', 'Fade In When Used', 'Off']
    p.default = p.val = 'editor'
    p = page.appendFloat('Uihold', label='Hold')[0]; p.default = p.val = 2.5; p.normMax = 10
    p = page.appendFloat('Uifade', label='Fade Time')[0]; p.default = p.val = 0.25; p.normMax = 2
    for name, label, val in (('Showcursor', 'Cursor', True), ('Showclicks', 'Click Ripples', True),
                             ('Showkeys', 'Keys', True), ('Showmouse', 'Mouse Buttons', True),
                             ('Uidebug', 'Calibration Overlay', False)):
        p = page.appendToggle(name, label=label)[0]; p.default = p.val = val
    p = page.appendFloat('Cursorsize', label='Cursor Size')[0]; p.default = p.val = 7; p.normMax = 30
    p = page.appendFloat('Pathbarheight', label='Path Bar Height')[0]; p.default = p.val = 28; p.normMax = 60
    page.appendXYZ('Uitranslate', label='UI Translate')
    page.appendXYZ('Uirotate', label='UI Rotate')
    p = page.appendFloat('Uiscale', label='UI Scale')[0]; p.default = p.val = 1
    p = page.appendFloat('Uidepth', label='UI Depth')[0]; p.default = p.val = 0.03; p.normMax = 0.5
    p = page.appendXY('Mousecaloffset', label='Mouse Offset')
    p = page.appendXY('Mousecalscale', label='Mouse Scale')
    for par_ in p:
        par_.default = par_.val = 1
    p = page.appendXY('Netcaloffset', label='Network Offset')
    p = page.appendFloat('Netcalscale', label='Network Zoom Scale')[0]; p.default = p.val = 1

    page = comp.appendCustomPage('Render')
    p = page.appendMenu('Cameramode', label='Camera Mode')[0]
    p.menuNames = ['mirror', 'follow']
    p.menuLabels = ['Mirror Editor View', 'Follow New Operators']
    p.default = p.val = 'mirror'
    page.appendCOMP('Camera', label='Camera')
    page.appendPulse('Frameall', label='Frame All')
    p = page.appendInt('Res', label='Resolution', size=2)
    p[0].default = p[0].val = 1920
    p[1].default = p[1].val = 1080


def _table(comp, name, rows, x, y):
    t = comp.create(tableDAT, name)
    t.clear()
    for row in rows:
        t.appendRow(list(row))
    t.nodeX, t.nodeY = x, y
    return t


def _buildUILayer(comp, render):
    """Inputs (screen grab, mouse, keyboard), the UI layer render and the
    final composite: UI layer over the 3D render placed in the window."""
    try:
        grab = comp.create(screengrabTOP, 'grab')
    except NameError:
        # no Screen Grab TOP in this build: captured tiles and chrome stay empty
        grab = comp.create(constantTOP, 'grab')
    _setparSafe(grab, 'source', _windowDisplay())
    grab.nodeX, grab.nodeY = 200, 450
    mouse = comp.create(mouseinCHOP, 'mouse')
    # button channels are off unless named
    _setparSafe(mouse, 'lbuttonname', 'lselect')
    _setparSafe(mouse, 'mbuttonname', 'mselect')
    _setparSafe(mouse, 'rbuttonname', 'rselect')
    mouse.nodeX, mouse.nodeY = 200, 600
    keys = comp.create(keyboardinDAT, 'keys')
    keys.par.callbacks = 'keys_cb'
    auto = comp.op('keys_callbacks')
    if auto is not None:
        auto.destroy()
    keys.nodeX, keys.nodeY = 200, 750
    _table(comp, 'regions', REGIONS, -600, -100)
    _table(comp, 'popups', POPUPS, -600, -250)
    _scriptOp(comp, scriptCHOP, 'ui', 'ui_cb', 400, 600)
    _scriptOp(comp, scriptCHOP, 'tiles', 'tiles_cb', 400, 450)
    cards = comp.create(geometryCOMP, 'ui_cards')
    _clearChildren(cards)
    cards.nodeX, cards.nodeY = 400, 300
    # the UI layer is a plane in 3D; by default its camera sits exactly where
    # the plane fills the frame, so it looks flat and pixel exact
    p = 'parent().par.'
    for axis in 'xyz':
        getattr(cards.par, 't' + axis).expr = p + 'Uitranslate' + axis
        getattr(cards.par, 'r' + axis).expr = p + 'Uirotate' + axis
        getattr(cards.par, 's' + axis).expr = p + 'Uiscale'
    cam = comp.create(cameraCOMP, 'cam_ui')
    cam.par.fov = 45
    cam.par.tx, cam.par.ty = 0, 0
    cam.par.tz.expr = 'parent().ext.UILayerExt.UICamDistance()'
    cam.nodeX, cam.nodeY = 400, 150
    rui = comp.create(renderTOP, 'render_ui')
    rui.par.camera = 'cam_ui'
    rui.par.geometry = 'ui_cards'
    rui.par.lights = ''
    rui.par.outputresolution = 'custom'
    rui.par.resolutionw.expr = 'parent().ext.UILayerExt.WindowSize()[0]'
    rui.par.resolutionh.expr = 'parent().ext.UILayerExt.WindowSize()[1]'
    _setparSafe(rui, 'bgcolora', 0)
    rui.nodeX, rui.nodeY = 600, 300
    place = comp.create(transformTOP, 'world_place')
    place.inputConnectors[0].connect(render)
    place.par.outputresolution = 'custom'
    place.par.resolutionw.expr = 'parent().ext.UILayerExt.WindowSize()[0]'
    place.par.resolutionh.expr = 'parent().ext.UILayerExt.WindowSize()[1]'
    _setparSafe(place, 'extend', 'zero')
    _setparSafe(place, 'tunit', 'fraction')
    r = 'parent().ext.UILayerExt.WorldRect()'
    place.par.tx.expr = '({0}[0] + {0}[2]) * 0.5 - 0.5'.format(r)
    place.par.ty.expr = '({0}[1] + {0}[3]) * 0.5 - 0.5'.format(r)
    place.par.sx.expr = '{0}[2] - {0}[0]'.format(r)
    place.par.sy.expr = '{0}[3] - {0}[1]'.format(r)
    place.nodeX, place.nodeY = 600, 100
    over = comp.create(overTOP, 'over_ui')
    over.inputConnectors[0].connect(rui)
    over.inputConnectors[1].connect(place)
    over.nodeX, over.nodeY = 800, 200
    out = comp.create(outTOP, 'out1')
    out.inputConnectors[0].connect(over)
    out.nodeX, out.nodeY = 1000, 200


def _windowDisplay():
    """Screen Grab source for the display the TD window sits on: '1', '2', ...
    (window titles change on every save, displays don't)."""
    try:
        cx, cy = ui.windowX + ui.windowWidth // 2, ui.windowY + ui.windowHeight // 2
        for m in monitors:
            if m.left <= cx <= m.right and m.bottom <= cy <= m.top:
                digits = ''.join(ch for ch in str(m.displayName) if ch.isdigit())
                return digits or '1'
    except Exception:
        pass
    return '1'


def _setparSafe(o, name, value):
    p = getattr(o.par, name, None)
    if p is not None:
        try:
            p.val = value
        except Exception:
            pass


def build(parentComp, scriptsDir, name='net3d'):
    old = parentComp.op(name)
    if old is not None:
        old.destroy()
    comp = parentComp.create(baseCOMP, name)
    comp.color = (0.25, 0.35, 0.5)
    _customPars(comp)

    # scripts
    for i, (dat, fname) in enumerate(SCRIPTS.items()):
        kind = {'frame_exec': executeDAT, 'par_exec': parameterexecuteDAT}.get(dat, textDAT)
        d = comp.create(kind, dat)
        with open(os.path.join(scriptsDir, fname), encoding='utf-8') as f:
            d.text = f.read()
        d.nodeX, d.nodeY = -800, 400 - i * 150
    fe = comp.op('frame_exec')
    fe.par.framestart = True
    fe.par.active = True
    pe = comp.op('par_exec')
    pe.par.op = '..'
    pe.par.pars = '*'
    pe.par.valuechange = True
    pe.par.onpulse = True
    pe.par.active = True

    colors = comp.create(tableDAT, 'colors')
    colors.clear()
    colors.appendRow(['key', 'r', 'g', 'b'])
    for row in COLORS:
        colors.appendRow(list(row))
    colors.nodeX, colors.nodeY = -600, 400
    tile = comp.create(tableDAT, 'tile')
    tile.clear()
    tile.appendRow(['key', 'value'])
    for row in TILE:
        tile.appendRow(list(row))
    tile.nodeX, tile.nodeY = -600, 100
    nodes = comp.create(tableDAT, 'nodes')
    nodes.nodeX, nodes.nodeY = -600, 250

    # data ops
    inst = _scriptOp(comp, scriptCHOP, 'inst', 'inst_cb', -400, 400)
    notes = _scriptOp(comp, scriptCHOP, 'notes', 'notes_cb', -400, 250)
    conn = _scriptOp(comp, scriptCHOP, 'conn', 'conn_cb', -400, 100)
    flags = _scriptOp(comp, scriptCHOP, 'flags', 'flags_cb', -400, 550)
    wires = _scriptOp(comp, scriptSOP, 'wires', 'wires_cb', -400, -50)
    quad = _scriptOp(comp, scriptSOP, 'quad', 'quad_cb', -400, -200)
    box = comp.create(boxSOP, 'box')
    box.nodeX, box.nodeY = -400, -350

    # materials: flat like the editor
    mat = comp.create(constantMAT, 'flat')
    mat.par.blending = True
    mat.nodeX, mat.nodeY = -200, -350

    # geometry
    _instancedGeo(comp, 'geo_slabs', box, inst, mat, 0, 400)
    _instancedGeo(comp, 'geo_conn', box, conn, mat, 0, 250)
    _instancedGeo(comp, 'geo_flags', box, flags, mat, 0, 550)
    gw = comp.create(geometryCOMP, 'geo_wires')
    _clearChildren(gw)
    sel = gw.create(selectSOP, 'in')
    sel.par.sop = '../wires'
    sel.render = sel.display = True
    gw.par.material = mat.name
    gw.nodeX, gw.nodeY = 0, 100
    cards = comp.create(geometryCOMP, 'cards')
    _clearChildren(cards)
    cards.nodeX, cards.nodeY = 0, -50

    cam = comp.create(cameraCOMP, 'cam')
    cam.nodeX, cam.nodeY = 0, -200

    render = comp.create(renderTOP, 'render')
    render.par.camera.expr = "parent().par.Camera.eval() or op('cam')"
    render.par.geometry = 'geo_slabs geo_conn geo_flags geo_wires cards'
    render.par.lights = ''
    render.par.outputresolution = 'custom'
    # with the UI layer the 3D render fills the network editor's rectangle
    render.par.resolutionw.expr = "parent().ext.UILayerExt.WorldRes()[0] if parent().par.Uilayer else parent().par.Res1"
    render.par.resolutionh.expr = "parent().ext.UILayerExt.WorldRes()[1] if parent().par.Uilayer else parent().par.Res2"
    # order-independent transparency, so faded layers blend whatever the
    # camera angle; the parameter name differs between builds
    for pn, v in (('antialias', 'aa16'), ('bgcolora', 1),
                  ('transparency', 'orderind')):
        if hasattr(render.par, pn):
            try:
                getattr(render.par, pn).val = v
            except Exception:
                pass
    render.nodeX, render.nodeY = 200, 100
    _buildUILayer(comp, render)

    # extensions
    comp.par.ext0object = "op('./NetGraphExt').module.NetGraphExt(me)"
    comp.par.ext0promote = True
    comp.par.ext1object = "op('./UILayerExt').module.UILayerExt(me)"
    comp.initializeExtensions()

    # Target left empty = the network net3d sits in
    comp.ext.NetGraphExt.Rebuild()
    comp.ext.NetGraphExt.Frame()
    comp.viewer = True
    return comp
