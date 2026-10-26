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

# Measured from the network editor of TD 2025.33230 (default UI colours).
# build() replaces most of them with the user's own ui.colors, see _uiColors.
COLORS = [
    ('bg', 0.098, 0.106, 0.122),
    ('TOP', 0.349, 0.310, 0.486),
    ('CHOP', 0.325, 0.459, 0.243),
    ('SOP', 0.251, 0.420, 0.584),
    ('DAT', 0.482, 0.310, 0.424),
    ('MAT', 0.518, 0.486, 0.247),
    ('COMP', 0.561, 0.565, 0.569),
    ('POP', 0.271, 0.267, 0.624),
    ('tile', 0.098, 0.098, 0.102),
    ('text', 0.75, 0.75, 0.75),
    ('bypass', 0.30, 0.30, 0.30),
    ('annotate', 0.30, 0.30, 0.30),
    ('type', 0.75, 0.75, 0.75),
    ('frame', 0.25, 0.25, 0.25),
    ('hier', 0.80, 0.80, 0.80),
    ('strip', 0.161, 0.161, 0.169),
    ('current', 0.0, 1.0, 0.0),
    ('selected', 0.85, 0.85, 0.0),
    ('flag_bypass', 0.90, 0.75, 0.20),
    ('flag_lock', 0.85, 0.30, 0.30),
    ('flag_display', 0.195, 0.49, 1.0),
    ('flag_render', 0.531, 0.402, 1.0),
    ('flag_viewer', 0.80, 0.80, 0.80),
    ('flag_error', 1.0, 0.0, 0.0),
    ('flag_warning', 1.0, 1.0, 0.0),
    ('hover', 0.75, 0.75, 0.75),
]

# colours key -> ui.colors entry and the factor the editor draws it with
# (family colours appear at 0.85 of the table value on tiles)
UI_COLORS = {
    'bg': ('worksheet.bg', 1.0),
    'TOP': ('TOP', 0.85), 'CHOP': ('CHOP', 0.85), 'SOP': ('SOP', 0.85), 'DAT': ('DAT', 0.85),
    'MAT': ('MAT', 0.85), 'POP': ('POP', 0.85),
    'text': ('tile.name.fg', 1.0), 'type': ('tile.name.fg', 1.0),
    'current': ('tile.current', 1.0), 'selected': ('tile.picked', 1.0),
    'flag_display': ('tile.flag.display', 1.0), 'flag_render': ('tile.flag.render', 1.0),
    'flag_viewer': ('tile.flag.viewer', 1.0), 'flag_error': ('tile.error', 1.0),
    'flag_warning': ('tile.warning', 1.0),
}

# Window regions TD does not report as panes, in window UV (origin bottom
# left). Measured on a maximised 1920x1080 window (Windows 10, TD 2025.33230):
# timeline 1002-1072 px from the top, menu bar + toolbar 32-79 px, 8 px frame.
# Calibrate with the Calibration Overlay against the grab on other layouts.
REGIONS = [
    ('name', 'u0', 'v0', 'u1', 'v1', 'trigger'),
    ('timeline', 0.0042, 0.0074, 0.9958, 0.0722, 'time'),
    ('menubar', 0.0042, 0.9269, 0.9958, 0.9704, 'always'),
]

# Popups opened over the editor: pixels, anchor = top-left corner relative
# to the click (dy up). Measured on TD 2025.33230:
#   context  right-click on empty editor space; TD shifts the menu so the
#            last used item sits under the cursor, so dy varies
#   create   OP Create Dialog (Tab), centred on the cursor; its height
#            follows the longest family list (TOP here)
#   info     middle-click on a node; height grows with the operator's info
POPUPS = [
    ('kind', 'w', 'h', 'dx', 'dy'),
    ('context', 246, 609, 6, 202),
    ('create', 784, 633, -392, 317),
    ('info', 307, 233, 7, 77),
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
    p.menuLabels = ['Drawn', 'Captured Snapshots']
    p.default = p.val = 'captured'
    page.appendPulse('Capturetiles', label='Capture Tile Faces')
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
    p = page.appendFloat('Pathbarheight', label='Path Bar Height')[0]; p.default = p.val = 23; p.normMax = 60
    page.appendXYZ('Uitranslate', label='UI Translate')
    page.appendXYZ('Uirotate', label='UI Rotate')
    p = page.appendFloat('Uiscale', label='UI Scale')[0]; p.default = p.val = 1
    p = page.appendFloat('Uidepth', label='UI Depth')[0]; p.default = p.val = 0.03; p.normMax = 0.5
    p = page.appendXY('Mousecaloffset', label='Mouse Offset')
    p = page.appendXY('Mousecalscale', label='Mouse Scale')
    for par_ in p:
        par_.default = par_.val = 1
    # pane coordinates start inside the OS window frame (8 px on Windows 10/11)
    p = page.appendXY('Windowinset', label='Window Inset (px)')
    for par_ in p:
        par_.default = par_.val = 8
    p = page.appendXY('Netcaloffset', label='Network Offset')
    p = page.appendFloat('Netcalscale', label='Network Zoom Scale')[0]; p.default = p.val = 1

    page = comp.appendCustomPage('Render')
    p = page.appendMenu('Cameramode', label='Camera Mode')[0]
    p.menuNames = ['mirror', 'follow']
    p.menuLabels = ['Mirror Editor View', 'Follow New Operators']
    p.default = p.val = 'mirror'
    page.appendCOMP('Camera', label='Camera')
    page.appendPulse('Frameall', label='Frame All')
    page.appendPulse('Examine', label='Open Examine Viewer')
    page.appendPulse('Examinehome', label='Home Examine Camera')
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
    # -1..1 over the primary monitor on both axes (the default 'aspect'
    # scales y by the width)
    _setparSafe(mouse, 'output', 'normal')
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


# TD's palette camera with tumble, pan and zoom like the built-in 3D viewers
EXAMINE_TOX = 'Palette/Tools/cameraViewport.tox'


def _buildExamine(comp):
    """A second render of the same geometry through TD's palette
    cameraViewport, shown in the 'examine' panel, for looking around the 3D
    network with the mouse. It never touches the main render or its camera,
    so mirror and animation cameras stay as they are. It only cooks while
    the panel is viewed."""
    src = comp.op('render')
    try:
        holder = comp.loadTox(app.samplesFolder + '/' + EXAMINE_TOX)
        holder.name = 'examine_cam'
        cam = holder.op('cameraViewport')
    except Exception:
        # no palette in this install: a plain camera, no mouse control
        holder = cam = comp.create(cameraCOMP, 'examine_cam')
        cam.par.tz = 30
    holder.nodeX, holder.nodeY = 200, -500
    # 5x the default depth precision; the scene is tens of units away
    _setparSafe(cam, 'near', 0.5)
    r = comp.create(renderTOP, 'render_examine')
    r.par.camera = cam
    # constant, not an expression: cameraViewport homes on the bounds of
    # the geometry parameter's constant value
    r.par.geometry = src.par.geometry.val
    r.par.lights = ''
    r.par.outputresolution = 'custom'
    r.par.resolutionw.expr = 'parent().par.Res1'
    r.par.resolutionh.expr = 'parent().par.Res2'
    for pn in ('antialias', 'transparency', 'bgcolorr', 'bgcolorg', 'bgcolorb', 'bgcolora'):
        if hasattr(r.par, pn):
            getattr(r.par, pn).expr = "op('render').par.{0}.eval()".format(pn)
    r.nodeX, r.nodeY = 400, -500
    v = comp.create(containerCOMP, 'examine')
    v.par.w.expr = 'parent().par.Res1'
    v.par.h.expr = 'parent().par.Res2'
    v.par.top = r.name
    # cameraViewport navigates with all three buttons and the wheel; panels
    # pass only the left button unless told otherwise
    for pn in ('uvbuttonsleft', 'uvbuttonsmiddle', 'uvbuttonsright', 'mousewheel'):
        _setparSafe(v, pn, True)
    v.nodeX, v.nodeY = 600, -500
    if hasattr(cam.par, 'Refpanel'):
        cam.par.Refpanel = v
        cam.par.Refrender = r
    return cam


def _uiColors(rows):
    """COLORS with the user's own editor colours from ui.colors where TD
    has them, so the drawn tiles follow a changed colour scheme."""
    out = []
    for key, r, g, b in rows:
        name, k = UI_COLORS.get(key, (None, 1.0))
        try:
            c = ui.colors[name] if name else None
            if c is not None:
                r, g, b = (round(min(1.0, v * k), 3) for v in tuple(c)[:3])
        except Exception:
            pass
        out.append((key, r, g, b))
    return out


def _windowDisplay():
    """Screen Grab source for the display the TD window sits on: '1', '2', ...
    (window titles change on every save, displays don't). The Screen Grab
    numbers displays in the order of the monitors list, not by their
    Windows name (DISPLAY1 can be Display 2)."""
    try:
        cx, cy = ui.windowX + ui.windowWidth // 2, ui.windowY + ui.windowHeight // 2
        for i, m in enumerate(monitors):
            if m.left <= cx <= m.right and m.bottom <= cy <= m.top:
                return str(i + 1)
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
    keep = None
    if old is not None:
        # tile snapshots outlive a rebuild of the component
        if old.op('snapshots') is not None:
            keep = parentComp.copy(old.op('snapshots'), name='net3d_snapshots_keep')
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
    for row in _uiColors(COLORS):
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
    # locked tile snapshots (Capture Tile Faces), kept through rebuilds
    if keep is not None:
        snaps = comp.copy(keep, name='snapshots')
        keep.destroy()
    else:
        snaps = comp.create(baseCOMP, 'snapshots')
    snaps.nodeX, snaps.nodeY = 0, -350

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
    # Script OPs cooked once while being created, before the extensions
    # existed; drop those errors and cook them again
    comp.clearScriptErrors(recurse=True)
    for o in comp.children:
        if o.OPType in ('scriptCHOP', 'scriptSOP'):
            o.cook(force=True)

    # Target left empty = the network net3d sits in
    comp.ext.NetGraphExt.Rebuild()
    comp.ext.NetGraphExt.Frame()
    cam = _buildExamine(comp)
    if hasattr(cam, 'ext') and getattr(cam.ext, 'CameraExt', None) is not None:
        cam.ext.CameraExt.Home()
    comp.viewer = True
    return comp
