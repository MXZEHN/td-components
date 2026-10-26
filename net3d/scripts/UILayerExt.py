"""
UILayerExt - the 2D layer on top of net3d's 3D network, for recording
tutorials that look like TouchDesigner itself.

TouchDesigner already renders every piece of its UI, so this layer re-uses
those pixels instead of imitating them. A Screen Grab TOP of the TD window
('grab') is the source; everything is laid out in window coordinates (u, v
in 0..1, origin bottom left, like a TOP), so a crop of the grab lands exactly
where TD drew it.

The layer itself is 3D: 'ui_cards' is a plane (window aspect x 1) filmed by
the perspective camera 'cam_ui', which by default sits exactly where the
plane fills the frame, so it looks flat and pixel exact. The plane can be
moved, tilted and scaled (UI Translate / Rotate / Scale), and its sublayers
(chrome, popups, overlays, calibration) sit UI Depth apart in Z, each scaled
to stay exact head on, so they separate with parallax as soon as the plane
turns.

  Chrome    every pane except the network editor (parameters, textport,
            palette, ...) and the regions in the 'regions' table (timeline,
            menu bar, ...) are crops of the grab. Chrome 'editor' keeps them
            all on screen like TD and puts the 3D network in the network
            editor's rectangle; 'float' shows the 3D network full frame and
            fades each piece of chrome in while it is being used.
  Popups    menus and popups TD draws over the editor (context menu, OP
            Create dialog, middle-click info) are cropped around the point
            they open from, while they are presumed open.
  Tiles     CookTiles maps every node's editor rectangle into the grab, so
            the 3D cards can show the real tile (see NetGraphExt).
  Overlays  what TD does not draw: the cursor (projected onto the 3D
            network while it is over the editor), click ripples, the mouse
            buttons held and the keys pressed.

Sensors: Mouse In CHOP 'mouse', Keyboard In DAT 'keys' (-> OnKey), ui.panes,
the network editor's view (x, y, zoom), the current operator's parameters
and the root time. Anything whose geometry TD does not report is a region or
popup size you calibrate in the 'regions' / 'popups' tables.
"""

import math

# Popups TD opens over the editor, and what opens them. Sizes in pixels,
# anchor = where the popup's top-left corner sits relative to the click.
DEFAULT_POPUPS = {
    'context': {'w': 246, 'h': 609, 'dx': 6, 'dy': 202},     # right click
    'create':  {'w': 784, 'h': 633, 'dx': -392, 'dy': 317},  # Tab: OP Create dialog
    'info':    {'w': 307, 'h': 233, 'dx': 7, 'dy': 77},      # middle click on a node
}

MODIFIER_KEYS = {'ctrl', 'lctrl', 'rctrl', 'shift', 'lshift', 'rshift', 'alt', 'lalt', 'ralt',
                 'cmd', 'lcmd', 'rcmd'}


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _setpar(o, name, value):
    p = getattr(o.par, name, None)
    if p is None:
        return False
    try:
        if p.val != value:
            p.val = value
        return True
    except Exception:
        return False


class UILayerExt:

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.Elements = []       # see _elements
        self.Hover = None        # path of the operator under the mouse
        self._fade = {}          # element key -> current alpha
        self._active = {}        # trigger key -> last time it fired
        self._ripples = []       # [u, v, t0, button]
        self._keys = []          # [text, t0]
        self._popup = None       # {'kind', 'u', 'v', 't0'}
        self._buttons = (0, 0, 0)
        self._mouseUV = None
        self._params = None      # (op path, {par: (value, mode)})
        self._time = None        # (frame, play)
        self._cards = {}         # element key -> (id, signature)
        self._nextCard = 0
        self._lastTick = None
        self._now = 0.0
        self._hoverSince = 0.0

    # ---- geometry: window, panes, network editor -------------------

    def WindowSize(self):
        try:
            return float(ui.windowWidth), float(ui.windowHeight)
        except Exception:
            p = self.ownerComp.par
            return float(p.Res1.eval()), float(p.Res2.eval())

    def _paneRect(self, pane):
        """Pane rectangle in window UV (u0, v0, u1, v1). Pane corners may
        come as UV or as pixels depending on the build; both are handled."""
        try:
            bl, tr = pane.bottomLeft, pane.topRight
            x0, y0 = (bl.x, bl.y) if hasattr(bl, 'x') else (bl[0], bl[1])
            x1, y1 = (tr.x, tr.y) if hasattr(tr, 'x') else (tr[0], tr[1])
        except Exception:
            return None
        # pane corners count from the window's client area, which starts
        # Window Inset pixels inside the window (the OS frame)
        w, h = self.WindowSize()
        ix, iy = self.ownerComp.par.Windowinsetx.eval(), self.ownerComp.par.Windowinsety.eval()
        if max(abs(x1), abs(y1)) > 1.5:
            x0, x1, y0, y1 = x0 / w, x1 / w, y0 / h, y1 / h
        return (x0 + ix / w, y0 + iy / h, x1 + ix / w, y1 + iy / h)

    def _panes(self):
        try:
            return list(ui.panes)
        except Exception:
            return []

    def _editorPane(self):
        panes = [pn for pn in self._panes() if pn.type == PaneType.NETWORKEDITOR]
        try:
            cur = ui.panes.current
        except Exception:
            cur = None
        pane = next((pn for pn in panes if pn.id == getattr(cur, 'id', None)), None)
        return pane or (panes[0] if panes else None)

    def EditorRect(self):
        pane = self._editorPane()
        return self._paneRect(pane) if pane is not None else None

    def ViewRect(self):
        """The editor pane without its path bar: the area that shows the
        network, whose centre is the editor's view centre."""
        rect = self.EditorRect()
        if rect is None:
            return None
        return (rect[0], rect[1], rect[2], rect[3] - self.ownerComp.par.Pathbarheight.eval() / self.WindowSize()[1])

    def NetToWindow(self, nx, ny):
        """Network-editor coordinates of the editor's current network ->
        window UV, from the editor's view centre (x, y) and zoom (pixels per
        network unit), plus the Net Calibration parameters."""
        pane, rect = self._editorPane(), self.ViewRect()
        if pane is None or rect is None:
            return None
        p = self.ownerComp.par
        w, h = self.WindowSize()
        zoom = getattr(pane, 'zoom', 1.0) * p.Netcalscale.eval()
        uc, vc = (rect[0] + rect[2]) * 0.5, (rect[1] + rect[3]) * 0.5
        return (uc + (nx - getattr(pane, 'x', 0.0)) * zoom / w + p.Netcaloffsetx.eval(),
                vc + (ny - getattr(pane, 'y', 0.0)) * zoom / h + p.Netcaloffsety.eval())

    def WindowToNet(self, u, v):
        pane, rect = self._editorPane(), self.ViewRect()
        if pane is None or rect is None:
            return None
        p = self.ownerComp.par
        w, h = self.WindowSize()
        zoom = getattr(pane, 'zoom', 1.0) * p.Netcalscale.eval()
        uc, vc = (rect[0] + rect[2]) * 0.5, (rect[1] + rect[3]) * 0.5
        return (getattr(pane, 'x', 0.0) + (u - p.Netcaloffsetx.eval() - uc) * w / zoom,
                getattr(pane, 'y', 0.0) + (v - p.Netcaloffsety.eval() - vc) * h / zoom)

    def _inRect(self, uv, rect):
        return uv is not None and rect is not None and rect[0] <= uv[0] <= rect[2] and rect[1] <= uv[1] <= rect[3]

    def WorldRect(self):
        """Where the 3D render goes in the window: the network editor's
        view (below the path bar) with Chrome 'editor', the whole window
        otherwise."""
        if self.ownerComp.par.Chrome.eval() == 'editor':
            r = self.ViewRect()
            if r is not None:
                return r
        return (0.0, 0.0, 1.0, 1.0)

    def WorldRes(self):
        w, h = self.WindowSize()
        r = self.WorldRect()
        return max(16, int((r[2] - r[0]) * w)), max(16, int((r[3] - r[1]) * h))

    def MirrorPose(self):
        """Camera pose that puts the edited network exactly where the
        network editor shows it: same centre, same zoom. Straight on, the
        3D layer then lines up pixel for pixel with TD's editor."""
        g = self.ownerComp.ext.NetGraphExt
        rect, net = self.ViewRect(), g._ownerPath or getattr(g, '_targetPath', None)
        if rect is None or net not in g.Networks:
            return None
        centre = self.WindowToNet((rect[0] + rect[2]) * 0.5, (rect[1] + rect[3]) * 0.5)
        top = self.WindowToNet((rect[0] + rect[2]) * 0.5, rect[3])
        wx, wy = g.NetToWorld(net, *centre)
        half = (top[1] - centre[1]) * g._scale   # half the visible height, in world units
        res = self.WorldRes()
        z = g._netZ(net)
        dist = half / g.TanHalfV(res[0] / res[1])
        return (wx, wy, z + dist), (wx, wy, z)

    def ProjectWorld(self, pt):
        """3D point -> window UV through the internal camera, or None when
        it is behind the camera."""
        cam = self.ownerComp.op('cam')
        g = self.ownerComp.ext.NetGraphExt
        px, py, pz = (pt[0] - cam.par.tx.eval(), pt[1] - cam.par.ty.eval(), pt[2] - cam.par.tz.eval())
        ry, rx = math.radians(cam.par.ry.eval()), math.radians(cam.par.rx.eval())
        # undo yaw, then pitch (camera rotate order XYZ)
        x1 = px * math.cos(-ry) + pz * math.sin(-ry)
        z1 = -px * math.sin(-ry) + pz * math.cos(-ry)
        y2 = py * math.cos(-rx) - z1 * math.sin(-rx)
        z2 = py * math.sin(-rx) + z1 * math.cos(-rx)
        if z2 >= -1e-4:
            return None
        rect = self.WorldRect()
        aspect = self.WorldRes()[0] / self.WorldRes()[1]
        tv = g.TanHalfV(aspect)
        sx = (x1 / -z2) / (tv * aspect)
        sy = (y2 / -z2) / tv
        return (rect[0] + (sx * 0.5 + 0.5) * (rect[2] - rect[0]),
                rect[1] + (sy * 0.5 + 0.5) * (rect[3] - rect[1]))

    # ---- sensors ----------------------------------------------------

    def _readMouse(self):
        """Mouse In CHOP -> window UV and buttons. The CHOP reports the
        position over the screen in -1..1; the window position turns it into
        window UV, Mouse Calibration fixes the rest."""
        m = self.ownerComp.op('mouse')
        if m is None:
            return None, (0, 0, 0)

        def ch(*names):
            for n in names:
                c = m.chan(n) if hasattr(m, 'chan') else None
                if c is not None:
                    return c.eval()
            return 0.0
        sx, sy = ch('tx', 'posx'), ch('ty', 'posy')
        buttons = (int(ch('lselect', 'left') > 0.5), int(ch('mselect', 'middle') > 0.5),
                   int(ch('rselect', 'right') > 0.5))
        try:
            mon = monitors.primary
            px = mon.left + (sx * 0.5 + 0.5) * mon.width
            py = mon.bottom + (sy * 0.5 + 0.5) * mon.height
            w, h = self.WindowSize()
            u, v = (px - ui.windowX) / w, (py - ui.windowY) / h
        except Exception:
            u, v = sx * 0.5 + 0.5, sy * 0.5 + 0.5
        p = self.ownerComp.par
        u = u * p.Mousecalscalex.eval() + p.Mousecaloffsetx.eval()
        v = v * p.Mousecalscaley.eval() + p.Mousecaloffsety.eval()
        return (u, v), buttons

    def OnKey(self, key, character, ctrl=False, shift=False, alt=False, cmd=False, state=True):
        """Called by the Keyboard In DAT callbacks for every key."""
        if not state:
            return
        k = key.lower()
        if k in MODIFIER_KEYS:
            return
        name = {'tab': 'Tab', 'esc': 'Esc', 'escape': 'Esc', 'enter': 'Enter', 'return': 'Enter',
                'space': 'Space', 'backspace': 'Backspace', 'delete': 'Del', 'up': 'Up', 'down': 'Down',
                'left': 'Left', 'right': 'Right'}.get(k, key.upper() if len(key) == 1 else key.title())
        combo = '+'.join([m_ for m_, on in (('Ctrl', ctrl), ('Cmd', cmd), ('Alt', alt), ('Shift', shift)) if on] + [name])
        self._keys = (self._keys + [[combo, self._now]])[-4:]
        self._active['keys'] = self._now
        if name == 'Tab' and self._mouseOverEditor():
            self._openPopup('create')
        elif name in ('Esc', 'Enter'):
            self._popup = None

    def _mouseOverEditor(self):
        return self._inRect(self._mouseUV, self.EditorRect())

    def _openPopup(self, kind):
        if self._mouseUV is not None:
            self._popup = {'kind': kind, 'u': self._mouseUV[0], 'v': self._mouseUV[1], 't0': self._now}

    def _readParams(self):
        """Snapshot of the current operator's parameters; a change marks
        the parameter pane active."""
        g = self.ownerComp.ext.NetGraphExt
        owner = g._ownerPath
        try:
            comp = op(owner) if owner else None
            cur = comp.currentChild if comp is not None else None
        except Exception:
            cur = None
        if cur is None:
            return
        try:
            snap = {pp.name: (str(pp.eval()), str(pp.mode)) for pp in cur.pars()}
        except Exception:
            return
        if self._params is not None and self._params[0] == cur.path and self._params[1] != snap:
            self._active['params'] = self._now
        if self._params is None or self._params[0] != cur.path:
            self._active['params'] = self._now
        self._params = (cur.path, snap)

    def _readTime(self):
        try:
            t = op('/').time
            state = (t.frame, bool(t.play))
        except Exception:
            return
        if self._time is not None:
            frame, play = self._time
            # playing on is not news; a play/pause or a jump is
            if play != state[1] or abs(state[0] - frame) > 3:
                self._active['time'] = self._now
        self._time = state

    # ---- per frame ---------------------------------------------------

    def Tick(self):
        p = self.ownerComp.par
        now = absTime.seconds
        dt = 0.0 if self._lastTick is None else max(0.0, now - self._lastTick)
        self._lastTick, self._now = now, now
        if not p.Uilayer.eval():
            return
        uv, buttons = self._readMouse()
        if uv != self._mouseUV:
            self._active['mouse'] = now
        self._mouseUV = uv
        for i, (was, isnow) in enumerate(zip(self._buttons, buttons)):
            if isnow and not was and uv is not None:
                self._ripples = (self._ripples + [[uv[0], uv[1], now, i]])[-4:]
                self._active['mouse'] = now
                if i == 2 and self._mouseOverEditor():
                    self._openPopup('context')
                elif i == 1 and self.Hover:
                    self._openPopup('info')
                elif i == 0 and self._popup and self._popup['kind'] == 'context' and now - self._popup['t0'] > 0.2:
                    self._popup = None   # a menu item was picked or the menu dismissed
            if was and not isnow and i == 1 and self._popup and self._popup['kind'] == 'info':
                self._popup = None
        self._buttons = buttons
        if absTime.frame % max(1, int(p.Livepoll.eval())) == 0:
            self._readParams()
            self._readTime()
        g = self.ownerComp.ext.NetGraphExt
        if g._ownerPath != getattr(self, '_lastOwner', None):
            self._lastOwner = g._ownerPath
            self._active['dive'] = now
        if p.Cameramode.eval() == 'mirror' and g._trans is None:
            pose = self.MirrorPose()
            if pose is not None:
                g._setCam(*pose)
        self._updateHover()
        self._fadeStep(dt)
        self._sync()
        o = self.ownerComp.op('ui')
        if o is not None:
            o.cook(force=True)
        t = self.ownerComp.op('tiles')
        if t is not None and p.Tilesource.eval() == 'captured':
            t.cook(force=True)

    def _updateHover(self):
        g = self.ownerComp.ext.NetGraphExt
        hover = None
        if self._mouseOverEditor():
            nxy = self.WindowToNet(*self._mouseUV)
            owner = g._editorOwner()
            for n in g.Nodes:
                if n['path'].rsplit('/', 1)[0] != owner:
                    continue
                if n['nx'] <= nxy[0] <= n['nx'] + n['netw'] and n['ny'] <= nxy[1] <= n['ny'] + n['neth']:
                    hover = n['path']
        if hover != self.Hover:
            self.Hover = hover
            self._hoverSince = self._now
            g.SetHover(hover)

    # ---- elements ----------------------------------------------------

    def _triggered(self, key, hold=None):
        hold = self.ownerComp.par.Uihold.eval() if hold is None else hold
        return self._now - self._active.get(key, -1e9) < hold

    def _elements(self):
        """Everything on the UI layer this frame. Each element: key, kind
        ('grab' crop | 'text' | 'rect' | 'ring'), rect in window UV
        (u0, v0, u1, v1), want (target opacity) and style."""
        p = self.ownerComp.par
        els = []
        chrome = p.Chrome.eval()
        mouse = self._mouseUV
        if chrome != 'off':
            for pane in self._panes():
                if pane.type == PaneType.NETWORKEDITOR:
                    continue
                r = self._paneRect(pane)
                if r is None:
                    continue
                key = 'pane:{}'.format(pane.id)
                params = pane.type == getattr(PaneType, 'PARAMETERS', None)
                used = self._inRect(mouse, r) or (params and self._triggered('params'))
                if used:
                    self._active[key] = self._now
                want = 1.0 if chrome == 'editor' else float(self._triggered(key))
                els.append({'key': key, 'kind': 'grab', 'rect': r, 'want': want, 'layer': 0})
            for reg in self._regions():
                key = 'region:' + reg['name']
                r = reg['rect']
                if self._inRect(mouse, r) or (reg['trigger'] in self._active and self._triggered(reg['trigger'])):
                    self._active[key] = self._now
                want = 1.0 if chrome == 'editor' or reg['trigger'] == 'always' else float(self._triggered(key))
                els.append({'key': key, 'kind': 'grab', 'rect': r, 'want': want, 'layer': 0})
        rect = self.EditorRect()
        if chrome != 'off' and rect is not None and p.Pathbarheight.eval() > 0:
            # the editor's path bar sits inside the editor pane, over the 3D view
            hgt = p.Pathbarheight.eval() / self.WindowSize()[1]
            r = (rect[0], rect[3] - hgt, rect[2], rect[3])
            if self._inRect(mouse, r):
                self._active['pathbar'] = self._now
            want = 1.0 if chrome == 'editor' else float(self._triggered('pathbar') or self._triggered('dive'))
            els.append({'key': 'pathbar', 'kind': 'grab', 'rect': r, 'want': want, 'layer': 0})
        if self._popup is not None:
            pop = self._popupSizes().get(self._popup['kind'])
            if pop is not None:
                w, h = self.WindowSize()
                u0 = self._popup['u'] + pop['dx'] / w
                v1 = self._popup['v'] + pop['dy'] / h
                r = (u0, v1 - pop['h'] / h, u0 + pop['w'] / w, v1)
                els.append({'key': 'popup', 'kind': 'grab', 'rect': r, 'want': 1.0, 'layer': 1})
            if self._now - self._popup['t0'] > 20:
                self._popup = None
        if p.Showcursor.eval() and mouse is not None:
            c = self._cursorUV()
            if c is not None:
                s = p.Cursorsize.eval() / self.WindowSize()[0]
                a = self.WindowSize()[0] / self.WindowSize()[1]
                els.append({'key': 'cursor', 'kind': 'ring', 'rect': (c[0] - s, c[1] - s * a, c[0] + s, c[1] + s * a),
                            'want': 1.0, 'color': (1.0, 1.0, 1.0), 'fill': True})
        if p.Showclicks.eval():
            dur = 0.6
            self._ripples = [r_ for r_ in self._ripples if self._now - r_[2] < dur]
            for i, (u, v, t0, b) in enumerate(self._ripples):
                k = (self._now - t0) / dur
                c = self._cursorUV((u, v)) or (u, v)
                s = (8 + 40 * k) / self.WindowSize()[0]
                a = self.WindowSize()[0] / self.WindowSize()[1]
                col = ((1.0, 0.85, 0.3), (0.4, 0.8, 1.0), (1.0, 0.45, 0.45))[b]
                els.append({'key': 'ripple{}'.format(i), 'kind': 'ring', 'rect': (c[0] - s, c[1] - s * a, c[0] + s, c[1] + s * a),
                            'want': 1.0 - k, 'instant': True, 'color': col, 'fill': False})
        if p.Showkeys.eval() and self._keys:
            text = '   '.join(k_ for k_, t0 in self._keys if self._now - t0 < p.Uihold.eval())
            if text:
                w, h = self.WindowSize()
                tw = (len(text) * 15 + 40) / w
                els.append({'key': 'keys', 'kind': 'text', 'text': text, 'rect': (0.5 - tw / 2, 0.08, 0.5 + tw / 2, 0.08 + 46 / h),
                            'want': float(self._triggered('keys')), 'size': 24})
        if p.Showmouse.eval():
            w, h = self.WindowSize()
            x0, y0, bw, bh = 1 - 110 / w, 0.08, 26 / w, 34 / h
            want = float(any(self._buttons) or self._triggered('mouse', 0.8) and any(
                self._now - r_[2] < 0.8 for r_ in self._ripples))
            for i, lit in enumerate(self._buttons):
                els.append({'key': 'mbtn{}'.format(i), 'kind': 'rect', 'want': want,
                            'rect': (x0 + i * (bw + 3 / w), y0 + 30 / h, x0 + i * (bw + 3 / w) + bw, y0 + 30 / h + bh),
                            'color': (0.95, 0.75, 0.3) if lit else (0.35, 0.35, 0.35)})
            els.append({'key': 'mbody', 'kind': 'rect', 'want': want, 'color': (0.25, 0.25, 0.25),
                        'rect': (x0, y0, x0 + 3 * bw + 6 / w, y0 + 27 / h)})
        if p.Uidebug.eval():
            els += self._debugElements()
        return els

    def _cursorUV(self, uv=None):
        """Where the cursor belongs on the output: over the editor it sits
        on the 3D network (projected from the network plane it points at),
        elsewhere it stays where it is in the window."""
        uv = uv or self._mouseUV
        if uv is None:
            return None
        if self.ownerComp.par.Chrome.eval() != 'off' and not self._inRect(uv, self.EditorRect()):
            return uv
        nxy = self.WindowToNet(*uv) if self._inRect(uv, self.EditorRect()) else None
        g = self.ownerComp.ext.NetGraphExt
        net = g.Networks.get(g._ownerPath) if g._ownerPath else None
        if nxy is None or net is None:
            return uv
        s = g._scale
        # the network keeps editor coordinates at level 0; nested ones are offset
        wx, wy = g.NetToWorld(g._ownerPath, nxy[0], nxy[1])
        return self.ProjectWorld((wx, wy, g._netZ(g._ownerPath)))

    def _debugElements(self):
        """Predicted node rectangles over the grab: when they line up with
        the real tiles, the Net Calibration is right."""
        g = self.ownerComp.ext.NetGraphExt
        owner = g._ownerPath or getattr(g, '_targetPath', None)
        els = []
        for n in g.Nodes:
            if n['path'].rsplit('/', 1)[0] != owner:
                continue
            a, b = self.NetToWindow(n['nx'], n['ny']), self.NetToWindow(n['nx'] + n['netw'], n['ny'] + n['neth'])
            if a and b:
                els.append({'key': 'dbg:' + n['path'], 'kind': 'rect', 'rect': (a[0], a[1], b[0], b[1]),
                            'want': 0.35, 'color': (1.0, 0.2, 0.6), 'layer': 3})
        return els

    def _regions(self):
        t = self.ownerComp.op('regions')
        out = []
        if t is None:
            return out
        for r in range(1, t.numRows):
            try:
                out.append({'name': t[r, 'name'].val, 'trigger': t[r, 'trigger'].val,
                            'rect': tuple(float(t[r, c]) for c in ('u0', 'v0', 'u1', 'v1'))})
            except (ValueError, TypeError, AttributeError):
                pass
        return out

    def _popupSizes(self):
        sizes = {k: dict(v) for k, v in DEFAULT_POPUPS.items()}
        t = self.ownerComp.op('popups')
        if t is not None:
            for r in range(1, t.numRows):
                try:
                    sizes[t[r, 'kind'].val] = {c: float(t[r, c]) for c in ('w', 'h', 'dx', 'dy')}
                except (ValueError, TypeError, AttributeError):
                    pass
        return sizes

    def _fadeStep(self, dt):
        p = self.ownerComp.par
        rate = dt / max(1e-3, p.Uifade.eval())
        els = self._elements()
        for e in els:
            cur = self._fade.get(e['key'], 0.0)
            if e.get('instant'):
                cur = e['want']
            elif cur < e['want']:
                cur = min(e['want'], cur + rate)
            else:
                cur = max(e['want'], cur - rate)
            self._fade[e['key']] = cur
            e['alpha'] = cur
        keys = {e['key'] for e in els}
        for k in list(self._fade):
            if k not in keys:
                del self._fade[k]
        self.Elements = [e for e in els if e['alpha'] > 0.001]

    # ---- operators for the elements --------------------------------

    def _sync(self):
        """One Geometry COMP per element in 'ui_cards' (a quad textured by a
        Crop TOP of the grab, a Text TOP, a Constant TOP or a Circle TOP);
        transforms and opacity come from the 'ui' CHOP by expression."""
        cards = self.ownerComp.op('ui_cards')
        if cards is None:
            return
        w, h = self.WindowSize()
        wanted = {}
        for i, e in enumerate(self.Elements):
            r = e['rect']
            px = (max(4, int((r[2] - r[0]) * w)), max(4, int((r[3] - r[1]) * h)))
            wanted[e['key']] = (i, e, (e['kind'], px if e['kind'] in ('text', 'ring') else None))
        for key in list(self._cards):
            if key not in wanted:
                old = cards.op('u{}'.format(self._cards.pop(key)[0]))
                if old is not None:
                    old.destroy()
        for key, (i, e, sig) in wanted.items():
            have = self._cards.get(key)
            if have is not None and have[1] != sig:
                old = cards.op('u{}'.format(have[0]))
                if old is not None:
                    old.destroy()
                have = None
            if have is None:
                cid = self._nextCard
                self._nextCard += 1
                self._make(cards, cid, e)
                have = (cid, sig, None)
            geo = cards.op('u{}'.format(have[0]))
            self._style(geo, e, w, h)
            if have[2] != i:
                for par_, ch in (('tx', 'tx'), ('ty', 'ty'), ('tz', 'tz'), ('sx', 'sx'), ('sy', 'sy')):
                    getattr(geo.par, par_).expr = "op('../ui')['{0}'][{1}]".format(ch, i)
                geo.op('mat').par.alpha.expr = "op('../../ui')['a'][{0}]".format(i)
            self._cards[key] = (have[0], sig, i)

    def _make(self, cards, cid, e):
        geo = cards.create(geometryCOMP, 'u{}'.format(cid))
        for c in list(geo.children):
            c.destroy()
        geo.nodeX, geo.nodeY = (cid % 10) * 150, -(cid // 10) * 120
        kind = e['kind']
        if kind == 'grab':
            # wires can't cross COMPs: select the grab into this card first
            src = geo.create(selectTOP, 'grab')
            src.par.top = '../../grab'
            src.nodeX = -200
            tex = geo.create(cropTOP, 'tex')
            tex.inputConnectors[0].connect(src)
        elif kind == 'text':
            tex = geo.create(textTOP, 'tex')
        elif kind == 'ring':
            tex = geo.create(circleTOP, 'tex')
        else:
            tex = geo.create(constantTOP, 'tex')
        mat = geo.create(constantMAT, 'mat')
        mat.par.colormap = tex.name
        _setpar(mat, 'blending', True)
        q = geo.create(selectSOP, 'quad')
        q.par.sop = '../../quad'
        q.render = q.display = True
        # a bare name would look for a sibling of the COMP; the MAT is inside
        geo.par.material = './' + mat.name

    def _style(self, geo, e, w, h):
        tex = geo.op('tex')
        r = e['rect']
        kind = e['kind']
        if kind == 'grab':
            _setpar(tex, 'cropleft', r[0]); _setpar(tex, 'cropright', r[2])
            _setpar(tex, 'cropbottom', r[1]); _setpar(tex, 'croptop', r[3])
            return
        _setpar(tex, 'outputresolution', 'custom')
        _setpar(tex, 'resolutionw', max(4, int((r[2] - r[0]) * w)))
        _setpar(tex, 'resolutionh', max(4, int((r[3] - r[1]) * h)))
        col = e.get('color', (1.0, 1.0, 1.0))
        if kind == 'text':
            tex.par.text = e['text']
            _setpar(tex, 'fontsizex', e.get('size', 20))
            _setpar(tex, 'alignx', 'center'); _setpar(tex, 'aligny', 'center')
            _setpar(tex, 'bgcolorr', 0.12); _setpar(tex, 'bgcolorg', 0.12); _setpar(tex, 'bgcolorb', 0.12)
            _setpar(tex, 'bgalpha', 0.85)
        elif kind == 'ring':
            _setpar(tex, 'radiusx', 0.42); _setpar(tex, 'radiusy', 0.42)
            _setpar(tex, 'fillcolorr', col[0]); _setpar(tex, 'fillcolorg', col[1]); _setpar(tex, 'fillcolorb', col[2])
            _setpar(tex, 'fillalpha', 1.0 if e.get('fill') else 0.0)
            _setpar(tex, 'bordercolorr', col[0]); _setpar(tex, 'bordercolorg', col[1]); _setpar(tex, 'bordercolorb', col[2])
            _setpar(tex, 'borderwidth', 0.08)
            _setpar(tex, 'bgalpha', 0.0)
        else:
            _setpar(tex, 'colorr', col[0]); _setpar(tex, 'colorg', col[1]); _setpar(tex, 'colorb', col[2])

    # ---- cook callbacks ---------------------------------------------

    def UICamDistance(self):
        """Distance at which the UI plane (height 1) fills cam_ui's frame."""
        cam = self.ownerComp.op('cam_ui')
        w, h = self.WindowSize()
        t = math.tan(math.radians(cam.par.fov.eval() if cam is not None else 45.0) * 0.5)
        method = getattr(cam.par, 'viewanglemethod', None) if cam is not None else None
        tv = t if method is not None and 'vert' in str(method.eval()).lower() else t / (w / h)
        return 0.5 / tv

    def CookUI(self, scriptOp):
        """Element placement on the UI plane: window UV -> plane X/Y
        (centred, window aspect x 1), Z by sublayer. An element lifted by z
        towards the camera is shrunk by (D - z) / D around the frame centre,
        so head on it still covers exactly its window pixels."""
        w, h = self.WindowSize()
        aspect = w / h
        dist = self.UICamDistance()
        gap = self.ownerComp.par.Uidepth.eval()
        chans = {k: [] for k in ('tx', 'ty', 'tz', 'sx', 'sy', 'a')}
        for e in self.Elements:
            r = e['rect']
            z = e.get('layer', 2) * gap
            k = (dist - z) / dist
            chans['tx'].append(((r[0] + r[2]) * 0.5 - 0.5) * aspect * k)
            chans['ty'].append(((r[1] + r[3]) * 0.5 - 0.5) * k)
            chans['tz'].append(z)
            chans['sx'].append((r[2] - r[0]) * aspect * k)
            chans['sy'].append((r[3] - r[1]) * k)
            chans['a'].append(e['alpha'])
        scriptOp.clear()
        n = len(self.Elements)
        scriptOp.numSamples = max(1, n)
        for k, v in chans.items():
            scriptOp.appendChan(k).vals = v if n else [0.0]

    def CookTiles(self, scriptOp):
        """Per node of NetGraphExt: its tile's rectangle in the grab (crop
        l r b t), whether it is fully on screen in the editor right now
        (vis: the card's Cache TOP records it) and whether it has ever been
        (got: the captured face is shown instead of the drawn one)."""
        g = self.ownerComp.ext.NetGraphExt
        rect = self.EditorRect()
        # only the network the editor really shows is on screen; net3d's own
        # owner path stays put while the editor is somewhere net3d ignores
        owner = g._editorOwner()
        got = getattr(self, '_got', set())
        chans = {k: [] for k in ('l', 'r', 'b', 't', 'vis', 'got')}
        for n in g.Nodes:
            a = b = None
            if rect is not None and n['path'].rsplit('/', 1)[0] == owner:
                a = self.NetToWindow(n['nx'], n['ny'])
                b = self.NetToWindow(n['nx'] + n['netw'], n['ny'] + n['neth'])
            vis = bool(a and b and self._inRect(a, rect) and self._inRect(b, rect)
                       and not (self._popup and self._popup['kind'] != 'info'))
            if vis:
                got.add(n['path'])
            a, b = a or (0, 0), b or (1, 1)
            chans['l'].append(a[0]); chans['r'].append(b[0]); chans['b'].append(a[1]); chans['t'].append(b[1])
            chans['vis'].append(float(vis)); chans['got'].append(float(n['path'] in got))
        self._got = got
        scriptOp.clear()
        n = len(g.Nodes)
        scriptOp.numSamples = max(1, n)
        for k, v in chans.items():
            scriptOp.appendChan(k).vals = v if n else [0.0]
