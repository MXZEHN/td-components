"""
NetGraphExt - rebuild a TouchDesigner network in 3D.

Scans the Target COMP (and optionally nested COMPs), records every node's
position and size from the network editor, its family, flags and wiring, and
lays the result out in world space: 1 network unit = Scale world units, the
network's +Y stays +Y, nodes face +Z.

Hierarchy is stacked in Z: the target network keeps its own coordinates and
sits at z = 0; each nested network sits Layer Spacing further back than its
COMP node, centred behind it, inside a titled frame. All operators of one
component share one depth. Wires run through the hierarchy (COMP input ->
In OP, Out OP -> COMP output) and along operator references, drawn as the
same bezier wires as inside a network.

Rendering is data-driven so it can be animated:
  inst      Script CHOP, one sample per node -> instanced node slabs
  conn      Script CHOP, one sample per connector -> instanced connector tabs
  notes     Script CHOP, one sample per panel (frames, annotations)
  wires     Script SOP, bezier ribbons between connectors
  flags     Script CHOP, one sample per lit flag -> instanced flag tabs
  cards/    one Geometry COMP per node: a live viewer quad (the TOP's image,
            or an OP Viewer TOP showing any operator's viewer) above a name
            strip, inside the family-coloured slab; one per panel too
Tile proportions come from the 'tile' table, colours from 'colors'.
Reveal (0..1) grows the network from its sources to its outputs, Explode
pushes the hierarchy levels further apart in Z.

Live mode polls the network every few frames and updates in place: new
operators grow in over Birth Time, and the internal camera follows the
newest (or last moved) operator. When the network editor enters or leaves a
component, the camera dives through the COMP's tile into its network (or
back out through it) while Focus Level fades the layers: parents in front
almost vanish, children behind stay faint. Dive(path) does the same from a
script.
"""

import math

# Network editor colours measured on TD 2025.33230. build() fills the 'colors'
# table from the user's ui.colors; edit that table to override.
DEFAULT_COLORS = {
    'bg':       (0.098, 0.106, 0.122),
    'TOP':      (0.349, 0.310, 0.486),
    'CHOP':     (0.325, 0.459, 0.243),
    'SOP':      (0.251, 0.420, 0.584),
    'DAT':      (0.482, 0.310, 0.424),
    'MAT':      (0.518, 0.486, 0.247),
    'COMP':     (0.561, 0.565, 0.569),
    'POP':      (0.271, 0.267, 0.624),
    'tile':     (0.098, 0.098, 0.102),
    'text':     (0.75, 0.75, 0.75),
    'type':     (0.75, 0.75, 0.75),
    'bypass':   (0.30, 0.30, 0.30),
    'annotate': (0.30, 0.30, 0.30),
    'frame':    (0.25, 0.25, 0.25),
    'hier':     (0.80, 0.80, 0.80),
    'strip':    (0.161, 0.161, 0.169),
    'current':  (0.0, 1.0, 0.0),
    'selected': (0.85, 0.85, 0.0),
    'flag_bypass':  (0.90, 0.75, 0.20),
    'flag_lock':    (0.85, 0.30, 0.30),
    'flag_display': (0.195, 0.49, 1.0),
    'flag_render':  (0.531, 0.402, 1.0),
    'flag_viewer':  (0.80, 0.80, 0.80),
    'flag_error':   (1.0, 0.0, 0.0),
    'flag_warning': (1.0, 1.0, 0.0),
    'hover':        (0.75, 0.75, 0.75),
}

# Tile layout in network-editor units. Edit the 'tile' table to calibrate
# against a screenshot of the editor at 100% zoom.
DEFAULT_TILE = {
    'border':    3,    # family-coloured edge
    'namestrip': 18,   # height of the name strip along the bottom
    'namesize':  11,   # name font size
    'typesize':  16,   # operator type font size on tiles without a viewer
    'titlesize': 16,   # frame / annotation title font size
    'flagw':     7,    # flag width
    'flagh':     12,   # flag height
    'conn':      8,    # connector tab size
}

try:
    _OPVIEWER = opviewerTOP
except NameError:
    _OPVIEWER = None

# op.color of a node nobody has recoloured (0.67 in TD 2025; stored values
# drift in the third decimal, hence the tolerance)
DEFAULT_NODE_COLOR = (0.67, 0.67, 0.67)


def _isDefaultColor(c):
    return all(abs(a - b) < 0.01 for a, b in zip(tuple(c)[:3], DEFAULT_NODE_COLOR))

# padding around a nested network's frame, in network units
FRAME_PAD = 60

# opacity of frames and annotations, before the layer fade
PANEL_ALPHA = {'frame': 0.5, 'annotate': 0.6}


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _smooth(v):
    v = _clamp(v)
    return v * v * (3.0 - 2.0 * v)


def _setpar(o, name, value):
    """Set a parameter if it exists; names and menu entries differ
    between builds."""
    p = getattr(o.par, name, None)
    if p is None:
        return False
    try:
        if p.val != value:
            p.val = value
        return True
    except Exception:
        return False


def _typeLabel(o):
    """'noiseTOP' -> 'Noise'."""
    t = o.OPType
    if t.endswith(o.family):
        t = t[:-len(o.family)]
    return t[:1].upper() + t[1:]


class NetGraphExt:

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.Nodes = []      # dicts, see _scanNetwork
        self.Conns = []      # dicts: node, side, dx, dy
        self.Wires = []      # dicts: a, b (endpoints), rs, rd, kind, color
        self.Panels = []     # frames and annotations: flat titled rectangles
        self.MaxRank = 0
        self._born = {}      # path -> absTime.seconds the node first appeared
        self._raw = {}       # path -> (nodeX, nodeY) at the last scan
        self._cards = {}     # key -> (card id, content signature)
        self._nextCard = 0
        self._structure = None
        self._focus = None
        self._camPos = None
        self._camLook = None
        self._now = 0.0
        self._lastTick = None
        self.Networks = {}   # COMP path -> its network's level, depth and bounds
        self._ownerPath = None   # network the editor (or Dive) is showing
        self._chain = set()      # that network and its ancestors: always scanned
        self._trans = None       # running dive / surface transition
        self._typed = {}         # annotation path -> typewriter state
        # filled by _scan; defaults for the Script OPs that cook before it
        self._index, self._ops = {}, []
        self._cols, self._tile = dict(DEFAULT_COLORS), dict(DEFAULT_TILE)
        self._scale, self._layer, self._maxLevel = 0.01, 8.0, 0
        self._previews = 'all'
        self._targetPath = None
        self._hover = None

    # ---- helpers ---------------------------------------------------

    def _target(self):
        t = self.ownerComp.par.Target.eval()
        return t if t is not None else self.ownerComp.parent()

    def _isOwn(self, o):
        own = self.ownerComp.path
        return o.path == own or o.path.startswith(own + '/')

    def Colors(self):
        cols = dict(DEFAULT_COLORS)
        t = self.ownerComp.op('colors')
        if t is not None:
            for r in range(1, t.numRows):
                try:
                    cols[t[r, 0].val] = (float(t[r, 1]), float(t[r, 2]), float(t[r, 3]))
                except (ValueError, TypeError):
                    pass
        return cols

    def Tile(self):
        tile = dict(DEFAULT_TILE)
        t = self.ownerComp.op('tile')
        if t is not None:
            for r in range(1, t.numRows):
                try:
                    tile[t[r, 0].val] = float(t[r, 1])
                except (ValueError, TypeError):
                    pass
        return tile

    def _visibleChildren(self, comp):
        ops, notes = [], []
        for c in comp.children:
            if self._isOwn(c) or not getattr(c, 'expose', True):
                continue
            if c.OPType == 'annotateCOMP':
                notes.append(c)
            else:
                ops.append(c)
        return ops, notes

    # ---- scanning --------------------------------------------------

    def _scan(self):
        """Fresh scan of the target into Nodes/Conns/Wires/Panels."""
        p = self.ownerComp.par
        self.Nodes, self.Conns, self.Wires, self.Panels = [], [], [], []
        self.MaxRank = 0
        self._index = {}
        self._ops = []
        self.Networks = {}
        self._cols = self.Colors()
        self._tile = self.Tile()
        self._scale = p.Scale.eval()
        self._layer = p.Layerspacing.eval()
        self._maxLevel = int(p.Recurse.eval())
        self._previews = p.Previews.eval()
        target = self._target()
        if target is None or not target.isCOMP:
            debug('net3d: Target is not a COMP')
            return
        self._scanNetwork(target, 0, None, 0)
        self._targetPath = target.path
        if p.References.eval():
            self._linkReferences()

    def _scanNetwork(self, comp, level, parentNode, baseRank):
        ops, notes = self._visibleChildren(comp)
        if not ops and not notes:
            return
        s = self._scale
        allOps = ops + notes
        x0 = min(o.nodeX for o in allOps)
        y0 = min(o.nodeY for o in allOps)
        x1 = max(o.nodeX + o.nodeWidth for o in allOps)
        y1 = max(o.nodeY + o.nodeHeight for o in allOps)

        if parentNode is None:
            # the target keeps its own coordinates so live edits do not
            # shift everything that is already there
            ox, oy, oz = 0.0, 0.0, 0.0
        else:
            # one layer further back, centred behind the COMP node
            pn = self.Nodes[parentNode]
            ox = pn['x'] - (x0 + x1) * 0.5 * s
            oy = pn['y'] - (y0 + y1) * 0.5 * s
            oz = pn['z'] - self._layer

        def world(nx, ny):
            return ox + nx * s, oy + ny * s

        bx0, by0 = world(x0, y0)
        bx1, by1 = world(x1, y1)
        self.Networks[comp.path] = {
            'level': level, 'z': oz, 'ox': ox, 'oy': oy, 'x': (bx0 + bx1) * 0.5, 'y': (by0 + by1) * 0.5,
            'w': bx1 - bx0, 'h': by1 - by0, 'comp': parentNode,
            # the network holding the COMP node
            'parent': self.Nodes[parentNode]['path'].rsplit('/', 1)[0] if parentNode is not None else None}
        fx0, fy0 = world(x0 - FRAME_PAD, y0 - FRAME_PAD)
        fx1, fy1 = world(x1 + FRAME_PAD, y1 + FRAME_PAD)
        cols = self._cols

        if parentNode is not None:
            # nested networks get a frame; the target's would be an opaque
            # wall hiding every layer behind it
            self.Panels.append({
                'key': 'frame:' + comp.path, 'title': comp.path, 'kind': 'frame', 'level': level,
                'x': (fx0 + fx1) * 0.5, 'y': (fy0 + fy1) * 0.5,
                'w': fx1 - fx0, 'h': fy1 - fy0, 'netw': (x1 - x0) + FRAME_PAD * 2,
                'z': oz, 'color': cols['frame'],
            })
            # the COMP tile's corners fan out to its network's frame
            pn = self.Nodes[parentNode]
            for cx, cy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                fx = fx0 if cx < 0 else fx1
                fy = fy0 if cy < 0 else fy1
                self.Wires.append({
                    'a': (parentNode, cx * pn['w'] * 0.5, cy * pn['h'] * 0.5),
                    'b': (None, fx, fy, oz - self.ownerComp.par.Depth.eval() * 2.5, level),
                    'rs': pn['rank'], 'rd': baseRank, 'kind': 'frame', 'color': cols['hier']})

        for a in notes:
            wx, wy = world(a.nodeX, a.nodeY)
            title = self._parText(a, ('Titletext', 'Title'))
            body = self._parText(a, ('Bodytext', 'Body', 'Text'))
            color = cols['annotate']
            if all(hasattr(a.par, n) for n in ('Backcolorr', 'Backcolorg', 'Backcolorb')):
                color = (a.par.Backcolorr.eval(), a.par.Backcolorg.eval(), a.par.Backcolorb.eval())
            elif not _isDefaultColor(a.color):
                color = tuple(a.color)
            self.Panels.append({
                'key': a.path, 'title': title, 'body': body, 'kind': 'annotate', 'level': level,
                'x': wx + a.nodeWidth * s * 0.5, 'y': wy + a.nodeHeight * s * 0.5,
                'w': a.nodeWidth * s, 'h': a.nodeHeight * s, 'netw': a.nodeWidth,
                'z': oz, 'color': color,
            })

        first = len(self.Nodes)
        local = {}
        for o in ops:
            wx, wy = world(o.nodeX, o.nodeY)
            fam = o.family
            tint = tuple(o.color)
            custom = not _isDefaultColor(tint)
            n = {
                'path': o.path, 'name': o.name, 'type': o.OPType, 'label': _typeLabel(o),
                'family': fam, 'level': level, 'rank': baseRank,
                'nx': o.nodeX, 'ny': o.nodeY,
                'x': wx + o.nodeWidth * s * 0.5, 'y': wy + o.nodeHeight * s * 0.5, 'z': oz,
                'w': o.nodeWidth * s, 'h': o.nodeHeight * s,
                'netw': o.nodeWidth, 'neth': o.nodeHeight,
                'color': cols.get(fam, cols['COMP']), 'tint': tint, 'custom': custom,
                'bypass': bool(getattr(o, 'bypass', False)),
                'lock': bool(getattr(o, 'lock', False)),
                'display': bool(getattr(o, 'display', False)),
                'render': bool(getattr(o, 'render', False)),
                'viewer': bool(getattr(o, 'viewer', False)),
                'current': bool(getattr(o, 'current', False)),
                'selected': bool(getattr(o, 'selected', False)),
                'error': self._message(o, 'errors'),
                'warning': self._message(o, 'warnings'),
                'conns': {},
            }
            local[o.path] = len(self.Nodes)
            self._index[o.path] = len(self.Nodes)
            self.Nodes.append(n)
            self._ops.append(o)

        # connectors: inputs left, outputs right, COMP connectors top/bottom
        pending = []
        for o in ops:
            ni = local[o.path]
            n = self.Nodes[ni]
            for side, conns in (
                    ('in', o.inputConnectors), ('out', o.outputConnectors),
                    ('cin', getattr(o, 'inputCOMPConnectors', [])),
                    ('cout', getattr(o, 'outputCOMPConnectors', []))):
                k = len(conns)
                n['conns'][side] = []
                for i, c in enumerate(conns):
                    f = (i + 1) / (k + 1)
                    if side in ('cin', 'cout'):
                        dx, dy = (f - 0.5) * n['w'], (0.5 if side == 'cin' else -0.5) * n['h']
                    else:
                        dx, dy = (-0.5 if side == 'in' else 0.5) * n['w'], (0.5 - f) * n['h']
                    self.Conns.append({'node': ni, 'side': side, 'dx': dx, 'dy': dy})
                    n['conns'][side].append((dx, dy))
                    if side in ('out', 'cout'):
                        for other in c.connections:
                            pending.append((ni, side, i, other.owner.path, other.index))

        for ni, side, i, dstPath, dstIndex in pending:
            dst = local.get(dstPath)
            if dst is None:
                continue
            dside = 'cin' if side == 'cout' else 'in'
            ends = self.Nodes[dst]['conns'].get(dside, [])
            if not ends:
                continue
            b = ends[dstIndex] if dstIndex < len(ends) else ends[0]
            a = self.Nodes[ni]['conns'][side][i]
            self.Wires.append({
                'a': (ni,) + a, 'b': (dst,) + b, 'rs': 0, 'rd': 0,
                'kind': 'comp' if side == 'cout' else 'wire', 'color': self.Nodes[ni]['color'],
                'src': ni, 'dst': dst})

        self._rank(first, len(self.Nodes))

        for o in ops:
            # every COMP down to Recurse Depth, and deeper only along the
            # chain down to the network being edited
            if o.isCOMP and (level < self._maxLevel or o.path in self._chain):
                ni = local[o.path]
                before = len(self.Nodes)
                self._scanNetwork(o, level + 1, ni, self.Nodes[ni]['rank'] + 1)
                if len(self.Nodes) > before:
                    self._linkInOut(o, ni)

    @staticmethod
    def _parText(o, names):
        for name in names:
            par = getattr(o.par, name, None)
            if par is not None:
                return str(par.eval())
        return ''

    @staticmethod
    def _message(o, kind):
        """First line of an operator's errors() / warnings(), or ''."""
        fn = getattr(o, kind, None)
        try:
            return (fn() or '').strip().split('\n')[0] if fn else ''
        except Exception:
            return ''

    def _linkInOut(self, comp, ni):
        """Wires through the hierarchy, drawn like any other wire: COMP
        input i -> its In OP, Out OP -> COMP output i."""
        n = self.Nodes[ni]
        for i, c in enumerate(comp.inputConnectors):
            inner = getattr(c, 'inOP', None)
            di = self._index.get(inner.path) if inner is not None else None
            if di is None:
                continue
            d = self.Nodes[di]
            self.Wires.append({'a': (ni,) + n['conns']['in'][i], 'b': (di, -d['w'] * 0.5, 0.0),
                               'rs': n['rank'], 'rd': d['rank'], 'kind': 'in', 'color': d['color'],
                               'src': ni, 'dst': di})
        for i, c in enumerate(comp.outputConnectors):
            inner = getattr(c, 'outOP', None)
            si = self._index.get(inner.path) if inner is not None else None
            if si is None:
                continue
            sn = self.Nodes[si]
            a = sn['conns']['out'][0] if sn['conns'].get('out') else (sn['w'] * 0.5, 0.0)
            self.Wires.append({'a': (si,) + a, 'b': (ni,) + n['conns']['out'][i],
                               'rs': sn['rank'], 'rd': n['rank'] + 1, 'kind': 'out', 'color': sn['color'],
                               'src': si, 'dst': ni})

    def _linkReferences(self):
        """Operator references (a Select TOP's TOP, a Geometry COMP's
        material, ...) between scanned operators, on any level, drawn as
        wires from the referenced operator to the one referencing it."""
        wired = {(w['src'], w['dst']) for w in self.Wires if 'src' in w}
        for di, o in enumerate(self._ops):
            pars = getattr(o, 'pars', None)
            if pars is None:
                continue
            for par in pars():
                if not getattr(par, 'isOP', False):
                    continue
                try:
                    v = par.eval()
                except Exception:
                    continue
                for t in (v if isinstance(v, (list, tuple)) else [v]):
                    si = self._index.get(getattr(t, 'path', None))
                    if si is None or si == di or (si, di) in wired:
                        continue
                    wired.add((si, di))
                    sn, dn = self.Nodes[si], self.Nodes[di]
                    self.Wires.append({'a': (si, sn['w'] * 0.5, 0.0), 'b': (di, -dn['w'] * 0.5, 0.0),
                                       'rs': sn['rank'], 'rd': dn['rank'], 'kind': 'ref',
                                       'color': sn['color'], 'src': si, 'dst': di})

    def _rank(self, first, last):
        """Longest-path rank from sources, for the nodes [first, last)."""
        wires = [w for w in self.Wires if w['kind'] in ('wire', 'comp')
                 and first <= w['src'] < last and first <= w['dst'] < last]
        for _ in range(last - first):
            changed = False
            for w in wires:
                r = self.Nodes[w['src']]['rank'] + 1
                if r > self.Nodes[w['dst']]['rank']:
                    self.Nodes[w['dst']]['rank'] = r
                    changed = True
            if not changed:
                break
        # with feedback loops the relaxation stops at the node count
        for w in wires:
            w['rs'] = self.Nodes[w['src']]['rank']
            w['rd'] = self.Nodes[w['dst']]['rank']
        for i in range(first, last):
            self.MaxRank = max(self.MaxRank, self.Nodes[i]['rank'])

    # ---- public ----------------------------------------------------

    def Rebuild(self):
        """Full rescan; cards are rebuilt from scratch."""
        for c in list(self.ownerComp.op('cards').children):
            c.destroy()
        self._cards = {}
        self._born = {}
        self._raw = {}
        self._focus = None
        self._typed = {}
        self.Update(force=True)
        self._camPos = None
        render = self.ownerComp.op('render')
        render.par.bgcolorr, render.par.bgcolorg, render.par.bgcolorb = self.Colors()['bg']

    def Update(self, force=False):
        """Rescan and apply what changed: new or removed operators update
        their cards, moved ones just move. Returns True if anything changed."""
        self._now = absTime.seconds
        self._scan()
        moved, added = None, None
        seen = set()
        for n in self.Nodes:
            path = n['path']
            seen.add(path)
            if path not in self._born:
                # on a full rebuild everything is simply there
                self._born[path] = -1e9 if (force or not self._raw) else self._now
                if not force and self._raw:
                    added = path
            raw = (n['nx'], n['ny'])
            if path in self._raw and self._raw[path] != raw:
                moved = path
            self._raw[path] = raw
        for path in list(self._born):
            if path not in seen:
                del self._born[path]
                self._raw.pop(path, None)
        if added or moved:
            self._focus = added or moved

        structure = hash(tuple(
            (n['path'], n['name'], n['type'], n['tint'], n['netw'], n['neth'],
             round(n['x'], 4), round(n['y'], 4), n['bypass'], n['lock'], n['display'],
             n['render'], n['viewer'], n['current'], n['selected'], n['error'], n['warning'])
            for n in self.Nodes) +
            tuple((w['a'], w['b'], w['kind']) for w in self.Wires) +
            tuple((pl['key'], pl['title'], pl['color'], round(pl['x'], 4), round(pl['y'], 4),
                   round(pl['w'], 4), round(pl['h'], 4)) for pl in self.Panels))
        if not force and structure == self._structure:
            return False
        self._structure = structure
        self._writeTable()
        self._syncCards()
        self._cook()
        return True

    def Tick(self):
        """Called every frame by frame_exec."""
        p = self.ownerComp.par
        now = absTime.seconds
        dt = 0.0 if self._lastTick is None else max(0.0, now - self._lastTick)
        self._lastTick = now
        self._now = now
        live = p.Live.eval()
        interval = int(p.Livepoll.eval()) if live else 30
        if (live or p.Autorebuild.eval()) and absTime.frame % max(1, interval) == 0:
            self.Update()
        if live and p.Followeditor.eval():
            owner = self._editorOwner()
            if owner is not None and owner != self._ownerPath:
                self.Dive(owner)
        if self._trans is not None:
            self._stepTransition()
        if p.Annotations.eval() == 'typewriter':
            self._typeStep()
        if live:
            # keep cooking while operators are still growing in
            birth = p.Birthtime.eval()
            if any(now - b < birth for b in self._born.values()):
                self._cook()
            if p.Follow.eval() and self._trans is None and p.Cameramode.eval() != 'mirror':
                self._follow(dt)

    def Frame(self):
        """Point the internal camera at the network being edited, or at
        everything when no component has been entered."""
        if self._ownerPath in self.Networks and self._ownerPath != getattr(self, '_targetPath', None):
            self._setCam(*self._framePose(self._ownerPath))
            self._camPos = None
            return
        cam = self.ownerComp.op('cam')
        items = self.Nodes + self.Panels
        if cam is None or not items:
            return
        x0 = min(n['x'] - n['w'] * 0.5 for n in items)
        x1 = max(n['x'] + n['w'] * 0.5 for n in items)
        y0 = min(n['y'] - n['h'] * 0.5 for n in items)
        y1 = max(n['y'] + n['h'] * 0.5 for n in items)
        res = self.ownerComp.op('render')
        aspect = res.width / max(1, res.height)
        half = max((y1 - y0) * 0.5, (x1 - x0) * 0.5 / aspect) * 1.1
        cam.par.tx = (x0 + x1) * 0.5
        cam.par.ty = (y0 + y1) * 0.5
        cam.par.tz = half / self.TanHalfV(aspect)
        cam.par.rx = cam.par.ry = cam.par.rz = 0
        self._camPos = None

    def Focus(self, path):
        """Make the live camera fly to the operator at path."""
        self._focus = path

    # ---- annotations: typewriter -----------------------------------

    @staticmethod
    def _fullText(pl):
        return pl['title'] + ('\n\n' + pl['body'] if pl.get('body') else '')

    def _panelText(self, pl):
        """What a panel shows right now: frames their title, annotations
        their text as far as it has been typed."""
        if pl['kind'] != 'annotate' or self.ownerComp.par.Annotations.eval() != 'typewriter':
            return self._fullText(pl) if pl['kind'] == 'annotate' else pl['title']
        st = self._typed.get(pl['key'])
        return st['shown'] if st else ''

    def RetypeAnnotations(self):
        """Forget which annotations have been typed; they type again on
        the next approach."""
        self._typed = {}
        self.Update(force=True)

    def _typeStep(self):
        """Annotations type themselves out the first time the camera comes
        close enough (centre in view, at least Approach of the frame high),
        then stay. Text added later while editing types on from where it
        was; other edits just show."""
        p = self.ownerComp.par
        ui_ = getattr(self.ownerComp.ext, 'UILayerExt', None)
        speed = max(1.0, p.Typespeed.eval())
        now = absTime.seconds
        explode = p.Explode.eval()
        for i, pl in enumerate(self.Panels):
            if pl['kind'] != 'annotate':
                continue
            full = self._fullText(pl)
            st = self._typed.get(pl['key'])
            if st is None:
                st = self._typed[pl['key']] = {'t0': None, 'text': full, 'shown': None, 'from': 0}
            if st['text'] != full:
                # edited while on screen: keep typing appended text, show the rest
                st['from'] = len(st['text']) if full.startswith(st['text']) else len(full)
                st['text'], st['t0'] = full, (now if st['t0'] is not None else None)
            if st['t0'] is None:
                z = pl['z'] - explode * pl['level']
                if ui_ is None or self._approached(ui_, pl, z, p.Approach.eval()):
                    st['t0'] = now
            n = st['from'] if st['t0'] is None else self._typedCount(full, st['from'], (now - st['t0']) * speed)
            caret = '_' if st['t0'] is not None and n < len(full) and int(now * 3) % 2 == 0 else ''
            shown = full[:n] + caret
            if shown != st['shown']:
                st['shown'] = shown
                card = self._cards.get('panel:' + pl['key'])
                geo = self.ownerComp.op('cards').op('c{}'.format(card[0])) if card else None
                if geo is not None:
                    geo.op('name').par.text = shown

    @staticmethod
    def _typedCount(text, start, ticks):
        """Characters typed after 'ticks' character-durations, starting at
        'start': punctuation and line breaks pause like a typist would."""
        n = start
        while n < len(text):
            ch = text[n]
            cost = 6.0 if ch == '\n' else 4.0 if ch in '.!?' else 2.0 if ch in ',;:' else 1.0
            if ticks < cost:
                break
            ticks -= cost
            n += 1
        return n

    @staticmethod
    def _approached(ui_, pl, z, approach):
        """The panel's centre is in the frame and its top-to-bottom height
        on screen is at least 'approach' of the frame."""
        c = ui_.ProjectWorld((pl['x'], pl['y'], z))
        top = ui_.ProjectWorld((pl['x'], pl['y'] + pl['h'] * 0.5, z))
        bot = ui_.ProjectWorld((pl['x'], pl['y'] - pl['h'] * 0.5, z))
        if c is None or top is None or bot is None:
            return False
        r = ui_.WorldRect()
        inside = r[0] <= c[0] <= r[2] and r[1] <= c[1] <= r[3]
        return inside and (top[1] - bot[1]) / max(1e-6, r[3] - r[1]) >= approach

    # ---- diving in and out of components ---------------------------

    def _editorOwner(self):
        """Path of the COMP the network editor is showing: the current
        pane if it is a network editor, else the first network editor."""
        try:
            panes = [pn for pn in ui.panes if pn.type == PaneType.NETWORKEDITOR]
            cur = ui.panes.current
        except Exception:
            return None
        pane = next((pn for pn in panes if pn.id == getattr(cur, 'id', None)), None)
        pane = pane or (panes[0] if panes else None)
        owner = getattr(pane, 'owner', None) if pane is not None else None
        return owner.path if owner is not None else None

    def Dive(self, path, duration=None):
        """Animate the camera to the network of the COMP at path: into
        components through their tile, out of them back through it, via
        the common parent for jumps across the tree. Live mode calls this
        whenever the network editor enters or leaves a component; call it
        yourself to script a fly-through."""
        old = self._ownerPath
        self._ownerPath = path
        target = getattr(self, '_targetPath', None)
        if target is None or not (path == target or path.startswith(target + '/')):
            return
        # scan the chain down to it, even below Recurse Depth, and keep the
        # one we come from until the camera has left it
        self._chain = self._chainOf(path) | (self._chainOf(old) if old else set())
        if path not in self.Networks:
            self.Update(force=True)
        if path not in self.Networks:
            return   # empty network: nothing to fly to
        cam = self.ownerComp.op('cam')
        start = ((cam.par.tx.eval(), cam.par.ty.eval(), cam.par.tz.eval()), self._camLookNow())
        hops = self._hops(old, path) if old in self.Networks else [(None, path)]
        dur = self.ownerComp.par.Transitiontime.eval() if duration is None else duration
        if dur <= 0 or old is None:
            pos, look = self._framePose(path)
            self._setCam(pos, look)
            self._setFocusLevel(self.Networks[path]['level'])
            return
        # a jump across several levels takes longer, but not hops x longer
        dur = dur * (1.0 + 0.5 * (len(hops) - 1)) / len(hops)
        self._trans = {'hops': hops, 'start': absTime.seconds, 'dur': dur, 'from': start,
                       'level0': self.ownerComp.par.Focuslevel.eval()}
        self._focus = None

    @staticmethod
    def _chainOf(path):
        """A COMP path and all its ancestors."""
        return {path[:i] for i in range(1, len(path) + 1) if path[i:i + 1] in ('/', '')}

    def _hops(self, a, b):
        """Networks visited from a to b: up to the common parent, then down."""
        def chain(p_):
            out = [p_]
            while self.Networks.get(out[-1], {}).get('parent'):
                out.append(self.Networks[out[-1]]['parent'])
            return out
        up, down = chain(a), chain(b)
        common = next(x for x in up if x in down)
        path = up[:up.index(common) + 1] + list(reversed(down[:down.index(common)]))
        return list(zip(path[:-1], path[1:]))

    def _netZ(self, net):
        n = self.Networks[net]
        return n['z'] - self.ownerComp.par.Explode.eval() * n['level']

    def _framePose(self, net):
        """Camera pose that shows a whole network. Inside a component the
        camera stays behind the layer in front, so it is really 'in' it.
        With Camera Mode 'mirror' a dive ends where the editor shows it."""
        if self.ownerComp.par.Cameramode.eval() == 'mirror' and net == self._ownerPath:
            ext = getattr(self.ownerComp.ext, 'UILayerExt', None)
            pose = ext.MirrorPose() if ext is not None else None
            if pose is not None:
                return pose
        n = self.Networks[net]
        cam = self.ownerComp.op('cam')
        res = self.ownerComp.op('render')
        aspect = res.width / max(1, res.height)
        dist = max(n['h'] * 0.5, n['w'] * 0.5 / aspect) * 1.15 / self.TanHalfV(aspect)
        if n['level'] > 0:
            dist = min(dist, (self.ownerComp.par.Layerspacing.eval() + self.ownerComp.par.Explode.eval()) * 0.85)
        z = self._netZ(net)
        return (n['x'], n['y'], z + dist), (n['x'], n['y'], z)

    def _doorPose(self, net):
        """Camera pose right in front of the COMP tile of a network: the
        tile fills the view, the moment the editor would 'enter' it."""
        n = self.Nodes[self.Networks[net]['comp']]
        res = self.ownerComp.op('render')
        tanh = self.TanHalfV(res.width / max(1, res.height))
        z = self._netZ(self.Networks[net]['parent'])
        return (n['x'], n['y'], z + n['h'] * 0.5 / tanh * 1.1), (n['x'], n['y'], z)

    def TanHalfV(self, aspect):
        """tan of half the vertical field of view. TD cameras measure FOV
        horizontally unless their View Angle Method says otherwise."""
        cam = self.ownerComp.op('cam')
        t = math.tan(math.radians(cam.par.fov.eval()) * 0.5)
        method = getattr(cam.par, 'viewanglemethod', None)
        vertical = method is not None and 'vert' in str(method.eval()).lower()
        return t if vertical else t / aspect

    def NetToWorld(self, net, nx, ny):
        """Network-editor coordinates inside the network of COMP 'net' ->
        world X/Y."""
        n = self.Networks[net]
        return n['ox'] + nx * self._scale, n['oy'] + ny * self._scale

    def SetHover(self, path):
        """The UI layer reports the operator under the mouse; its border
        lights up like the editor's hover."""
        self._hover = path
        o = self.ownerComp.op('inst')
        if o is not None:
            o.cook(force=True)

    def _stepTransition(self):
        tr = self._trans
        t = (absTime.seconds - tr['start']) / tr['dur']
        k = int(t)
        if k >= len(tr['hops']):
            pos, look = self._framePose(tr['hops'][-1][1])
            self._setCam(pos, look)
            self._setFocusLevel(self.Networks[tr['hops'][-1][1]]['level'])
            self._trans = None
            self._camPos = None   # follow picks up from here
            self._chain = self._chainOf(self._ownerPath)
            return
        u = _smooth(t - k)
        a, b = tr['hops'][k]
        pa = tr['from'] if k == 0 else self._framePose(a)
        pb = self._framePose(b)
        # into a child goes through its tile, out of one too
        door = None
        if a is not None and self.Networks[b].get('parent') == a:
            door = self._doorPose(b)
        elif a is not None and self.Networks[a].get('parent') == b:
            door = self._doorPose(a)
        if door is None:
            pos = tuple(x + (y - x) * u for x, y in zip(pa[0], pb[0]))
            look = tuple(x + (y - x) * u for x, y in zip(pa[1], pb[1]))
        else:
            q = lambda p0, p1, p2: tuple((1 - u) ** 2 * x + 2 * (1 - u) * u * y + u * u * w
                                         for x, y, w in zip(p0, p1, p2))
            pos, look = q(pa[0], door[0], pb[0]), q(pa[1], door[1], pb[1])
        la = tr['level0'] if k == 0 else self.Networks[a]['level']
        self._setCam(pos, look)
        self._setFocusLevel(la + (self.Networks[b]['level'] - la) * u)

    def _camLookNow(self):
        """Point the camera is looking at, from its position and rotation."""
        cam = self.ownerComp.op('cam')
        rx, ry = math.radians(cam.par.rx.eval()), math.radians(cam.par.ry.eval())
        d = (-math.sin(ry) * math.cos(rx), math.sin(rx), -math.cos(ry) * math.cos(rx))
        pos = (cam.par.tx.eval(), cam.par.ty.eval(), cam.par.tz.eval())
        return tuple(p_ + d_ * 5.0 for p_, d_ in zip(pos, d))

    def _setCam(self, pos, look):
        cam = self.ownerComp.op('cam')
        dx, dy, dz = (look[0] - pos[0], look[1] - pos[1], look[2] - pos[2])
        cam.par.tx, cam.par.ty, cam.par.tz = pos
        # camera looks down -Z; rotate order XYZ = pitch, then yaw
        cam.par.ry = math.degrees(math.atan2(-dx, -dz))
        cam.par.rx = math.degrees(math.atan2(dy, math.hypot(dx, dz)))
        cam.par.rz = 0

    def _setFocusLevel(self, v):
        if abs(self.ownerComp.par.Focuslevel.eval() - v) > 1e-6:
            self.ownerComp.par.Focuslevel = v

    # ---- camera follow ---------------------------------------------

    def _follow(self, dt):
        cam = self.ownerComp.op('cam')
        i = self._index.get(self._focus) if self._focus else None
        if cam is None or i is None:
            return
        p = self.ownerComp.par
        poses, _ = self.Layout()
        x, y, z, _s = poses[i]
        look = (x, y, z)
        off = (p.Followoffsetx.eval(), p.Followoffsety.eval(), p.Followoffsetz.eval())
        want = (x + off[0], y + off[1], z + off[2])
        if self._camPos is None:
            self._camPos = (cam.par.tx.eval(), cam.par.ty.eval(), cam.par.tz.eval())
            self._camLook = look
        k = 1.0 - math.exp(-dt / max(1e-3, p.Followsmooth.eval()))
        self._camPos = tuple(c + (w - c) * k for c, w in zip(self._camPos, want))
        self._camLook = tuple(c + (w - c) * k for c, w in zip(self._camLook, look))
        self._setCam(self._camPos, self._camLook)

    # ---- animation -------------------------------------------------

    def LayerAlpha(self, level):
        """Opacity of a hierarchy level: the level in focus is solid,
        each level behind it multiplies by Layer Opacity, each level in
        front of it (the parents, when you are inside a component) by
        Front Opacity."""
        p = self.ownerComp.par
        d = level - p.Focuslevel.eval()
        return p.Layeropacity.eval() ** d if d >= 0 else p.Frontopacity.eval() ** -d

    def Layout(self):
        """Current animated pose per node: list of (x, y, z, s) where s is
        the reveal/birth scale 0..1, and per-wire growth 0..1."""
        p = self.ownerComp.par
        reveal = p.Reveal.eval()
        explode = p.Explode.eval()
        birth = max(1e-3, p.Birthtime.eval()) if p.Live.eval() else None
        # one extra step so links that run back up the ranks finish too
        r = reveal * (self.MaxRank * 2 + 2)
        poses = []
        for n in self.Nodes:
            s = _smooth(r - n['rank'] * 2)
            if birth is not None:
                s *= _smooth((self._now - self._born.get(n['path'], -1e9)) / birth)
            # every operator of a component shares its depth
            poses.append((n['x'], n['y'], n['z'] - explode * n['level'], s))
        grow = []
        for w in self.Wires:
            start = w['rs'] * 2 + 1
            g = _clamp((r - start) / max(1.0, w['rd'] * 2 - start))
            # in live mode a wire grows once both ends are there
            ends = [poses[e[0]][3] for e in (w['a'], w['b']) if e[0] is not None]
            if ends:
                g = min(g, *ends)
            grow.append(g)
        return poses, grow

    # ---- outputs ---------------------------------------------------

    def _cook(self):
        for name in ('inst', 'flags', 'notes', 'conn', 'wires'):
            o = self.ownerComp.op(name)
            if o is not None:
                o.cook(force=True)

    def _writeTable(self):
        t = self.ownerComp.op('nodes')
        if t is None:
            return
        t.clear()
        t.appendRow(['index', 'path', 'name', 'family', 'type', 'level', 'rank',
                     'x', 'y', 'z', 'w', 'h', 'view'])
        for i, n in enumerate(self.Nodes):
            t.appendRow([i, n['path'], n['name'], n['family'], n['type'], n['level'], n['rank'],
                         round(n['x'], 4), round(n['y'], 4), round(n['z'], 4),
                         round(n['w'], 4), round(n['h'], 4), self._viewSource(n)])

    def _viewSource(self, n):
        """What fills a node's viewer area: 'top' (the TOP's own image),
        'op' (an OP Viewer TOP showing the operator's viewer, live) or
        'icon' (the operator type, like a tile without a viewer)."""
        mode = self._previews
        if mode == 'none':
            return 'icon'
        if mode == 'viewer' and not n['viewer']:
            return 'icon'
        if n['family'] == 'TOP':
            return 'top'
        if mode == 'tops':
            return 'icon'
        return 'op' if _OPVIEWER is not None else 'icon'

    def _syncCards(self):
        """One card per node and panel, keyed by path so live edits only
        touch what changed. A node card is a Geometry COMP holding a live
        viewer quad and a name strip quad; the card follows the 'inst' /
        'notes' CHOPs by expression."""
        cards = self.ownerComp.op('cards')
        # the card expressions index these CHOPs per node: cook them for the
        # new node list first, or a new index is out of range until they do
        for name in ('inst', 'notes', 'tiles'):
            o = self.ownerComp.op(name)
            if o is not None:
                o.cook(force=True)
        cols = self._cols
        tile = self._tile
        s = self._scale
        p = self.ownerComp.par
        lres, vres = p.Labelres.eval(), p.Viewerres.eval()
        captured = p.Tilesource.eval() == 'captured'
        wanted = {}
        for i, n in enumerate(self.Nodes):
            b, ns = tile['border'], tile['namestrip']
            vw, vh = n['netw'] - 2 * b, n['neth'] - 2 * b - ns
            src = self._viewSource(n)
            wanted[n['path']] = ('inst', i, dict(
                panel=False, path=n['path'], src=src, text=n['name'], label=n['label'],
                strip=n['tint'] if n['custom'] else cols['strip'],
                iconbg=cols['tile'], bypass=n['bypass'],
                # local layout in world units, relative to the node centre
                view=(0.0, ns * 0.5 * s, vw * s, vh * s) if vh > 4 else None,
                name=(0.0, (-n['neth'] * 0.5 + b + ns * 0.5) * s, vw * s, ns * s),
                viewpx=(max(8, int(vw * vres)), max(8, int(vh * vres))),
                namepx=(max(8, int(vw * lres)), max(8, int(ns * lres))),
                # the real tile, cropped from the screen grab (see UILayerExt)
                face=(0.0, 0.0, n['w'], n['h']) if captured else None))
        for i, pl in enumerate(self.Panels):
            netw = max(64, pl['netw'])
            neth = netw * pl['h'] / max(1e-6, pl['w'])
            wanted['panel:' + pl['key']] = ('notes', i, dict(
                panel=True, path='', src='', text=self._panelText(pl), label='', strip=pl['color'],
                iconbg=pl['color'], bypass=False, view=None,
                name=(0.0, 0.0, pl['w'], pl['h']), viewpx=None,
                namepx=(max(8, int(netw * lres * 0.5)), max(8, int(neth * lres * 0.5)))))

        for key in list(self._cards):
            if key not in wanted:
                cid = self._cards.pop(key)[0]
                old = cards.op('c{}'.format(cid))
                if old is not None:
                    old.destroy()

        for key, (src, idx, spec) in wanted.items():
            content = (spec['src'], spec['path'], spec['view'] is not None, spec['viewpx'], spec['namepx'],
                       spec.get('face') is not None)
            have = self._cards.get(key)
            if have is not None and have[1] != content:
                old = cards.op('c{}'.format(have[0]))
                if old is not None:
                    old.destroy()
                have = None
            if have is None:
                cid = self._nextCard
                self._nextCard += 1
                self._makeCard(cards, cid, spec)
                have = (cid, content, None)
            cid = have[0]
            geo = cards.op('c{}'.format(cid))
            self._styleCard(geo, spec, cols, tile)
            if have[2] != (src, idx):
                # sample index changes when operators come and go
                ref = "op('../{0}')".format(src)
                geo.par.tx.expr = "{0}['tx'][{1}]".format(ref, idx)
                geo.par.ty.expr = "{0}['ty'][{1}]".format(ref, idx)
                geo.par.tz.expr = "{0}['fz'][{1}]".format(ref, idx)
                for sp in ('sx', 'sy', 'sz'):
                    getattr(geo.par, sp).expr = "{0}['sc'][{1}]".format(ref, idx)
                # deeper layers fade; the MATs sit one network further down
                for part in ('view', 'name'):
                    mat = geo.op(part + '_mat')
                    if mat is not None:
                        mat.par.alpha.expr = "op('../../{0}')['ca'][{1}]".format(src, idx)
                if geo.op('face') is not None:
                    # crop follows the tile on screen; the cache holds the last
                    # frame it was fully visible; shown once it has been seen
                    crop = geo.op('face_src')
                    for par_, ch in (('cropleft', 'l'), ('cropright', 'r'), ('cropbottom', 'b'), ('croptop', 't')):
                        getattr(crop.par, par_).expr = "op('../../tiles')['{0}'][{1}]".format(ch, idx)
                    geo.op('face').par.active.expr = "op('../../tiles')['vis'][{0}] > 0.5".format(idx)
                    geo.op('face_mat').par.alpha.expr = (
                        "op('../../inst')['ca'][{0}] * op('../../tiles')['got'][{0}]".format(idx))
            self._cards[key] = (cid, content, (src, idx))

    def _makeCard(self, cards, cid, spec):
        geo = cards.create(geometryCOMP, 'c{}'.format(cid))
        for c in list(geo.children):
            c.destroy()
        geo.nodeX, geo.nodeY = (cid % 10) * 150, -(cid // 10) * 120
        parts = [('name', spec['namepx'])]
        if spec['view'] is not None:
            parts.insert(0, ('view', spec['viewpx']))
        for k, (part, (pw, ph)) in enumerate(parts):
            y = -k * 300
            if part == 'view' and spec['src'] == 'top':
                sel = geo.create(selectTOP, 'view_src')
                sel.par.top = spec['path']
                tex = geo.create(fitTOP, 'view')
                tex.inputConnectors[0].connect(sel)
                _setpar(tex, 'fit', 'fitbest')
                sel.nodeX, sel.nodeY = -200, y
            elif part == 'view' and spec['src'] == 'op':
                tex = geo.create(_OPVIEWER, 'view')
                _setpar(tex, 'opviewer', spec['path'])
            else:
                tex = geo.create(textTOP, part)
            _setpar(tex, 'outputresolution', 'custom')
            _setpar(tex, 'resolutionw', pw)
            _setpar(tex, 'resolutionh', ph)
            mat = geo.create(constantMAT, part + '_mat')
            mat.par.colormap = tex.name
            _setpar(mat, 'blending', True)
            g = geo.create(geometryCOMP, 'g' + part)
            for c in list(g.children):
                c.destroy()
            q = g.create(selectSOP, 'quad')
            q.par.sop = '../../../quad'
            q.render = q.display = True
            g.par.material = mat.name
            for j, o_ in enumerate((tex, mat, g)):
                o_.nodeX, o_.nodeY = j * 200, y
        if spec.get('face') is not None:
            # wires can't cross COMPs: select the grab into this card first
            grab = geo.create(selectTOP, 'grab')
            grab.par.top = '../../grab'
            crop = geo.create(cropTOP, 'face_src')
            crop.inputConnectors[0].connect(grab)
            cache = geo.create(cacheTOP, 'face')
            cache.inputConnectors[0].connect(crop)
            _setpar(cache, 'cachesize', 1)
            mat = geo.create(constantMAT, 'face_mat')
            mat.par.colormap = 'face'
            _setpar(mat, 'blending', True)
            g = geo.create(geometryCOMP, 'gface')
            for c in list(g.children):
                c.destroy()
            q = g.create(selectSOP, 'quad')
            q.par.sop = '../../../quad'
            q.render = q.display = True
            g.par.material = 'face_mat'
            g.par.tz = 0.0008
            for j, o_ in enumerate((grab, crop, cache, mat, g)):
                o_.nodeX, o_.nodeY = j * 200 - 400, 300

    def _styleCard(self, geo, spec, cols, tile):
        for part in ('view', 'name', 'face'):
            rect = spec.get(part)
            g = geo.op('g' + part)
            if rect is None or g is None:
                continue
            g.par.tx, g.par.ty = rect[0], rect[1]
            g.par.sx, g.par.sy = rect[2], rect[3]
        res = self.ownerComp.par.Labelres.eval()
        name = geo.op('name')
        name.par.text = spec['text']
        fg = cols['text']
        _setpar(name, 'fontcolorr', fg[0]); _setpar(name, 'fontcolorg', fg[1]); _setpar(name, 'fontcolorb', fg[2])
        bg = spec['strip']
        _setpar(name, 'bgcolorr', bg[0]); _setpar(name, 'bgcolorg', bg[1]); _setpar(name, 'bgcolorb', bg[2])
        _setpar(name, 'bgalpha', 1)
        if spec['panel']:
            _setpar(name, 'wordwrap', True)
            _setpar(name, 'fontsizex', tile['titlesize'] * res * 0.5)
            _setpar(name, 'alignx', 'left')
            _setpar(name, 'aligny', 'top')
            _setpar(name, 'positionx', 8 * res * 0.5)
            _setpar(name, 'positiony', -6 * res * 0.5)
        else:
            _setpar(name, 'fontsizex', tile['namesize'] * res)
            _setpar(name, 'alignx', 'left')
            _setpar(name, 'aligny', 'center')
            _setpar(name, 'positionx', 3 * res)
        view = geo.op('view')
        if view is not None and spec['src'] == 'icon':
            # no viewer: the operator type where the editor draws its icon
            tc = cols['type']
            bg = cols['bypass'] if spec['bypass'] else spec['iconbg']
            view.par.text = spec['label']
            _setpar(view, 'fontsizex', tile['typesize'] * self.ownerComp.par.Viewerres.eval())
            _setpar(view, 'alignx', 'center')
            _setpar(view, 'aligny', 'center')
            _setpar(view, 'fontcolorr', tc[0]); _setpar(view, 'fontcolorg', tc[1]); _setpar(view, 'fontcolorb', tc[2])
            _setpar(view, 'bgcolorr', bg[0]); _setpar(view, 'bgcolorg', bg[1]); _setpar(view, 'bgcolorb', bg[2])
            _setpar(view, 'bgalpha', 1)
        # bypassed operators read dimmed, like the editor
        for part in ('view', 'name'):
            mat = geo.op(part + '_mat')
            if mat is not None:
                k = 0.45 if spec['bypass'] else 1.0
                _setpar(mat, 'colorr', k); _setpar(mat, 'colorg', k); _setpar(mat, 'colorb', k)

    # ---- cook callbacks (Script CHOP / SOP) ------------------------

    def CookInst(self, scriptOp):
        """Node slabs (tx ty tz sx sy sz r g b a) and card placement
        (fz = face depth, sc = reveal/birth scale, ca = card opacity). The slab is the tile's
        border: family colour, or the highlight for the current/selected
        operator."""
        p = self.ownerComp.par
        depth = p.Depth.eval()
        cols = self._cols
        hl = p.Highlight.eval()
        poses, _ = self.Layout()
        chans = {k: [] for k in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz', 'r', 'g', 'b', 'a', 'fz', 'sc', 'ca')}
        for n, (x, y, z, s) in zip(self.Nodes, poses):
            col = n['color']
            if hl and n['path'] == getattr(self, '_hover', None):
                col = cols['hover']
            elif hl and n['current']:
                col = cols['current']
            elif hl and n['selected']:
                col = cols['selected']
            chans['tx'].append(x); chans['ty'].append(y); chans['tz'].append(z - depth * 0.5)
            chans['sx'].append(n['w'] * s); chans['sy'].append(n['h'] * s); chans['sz'].append(depth * max(s, 1e-4))
            chans['r'].append(col[0]); chans['g'].append(col[1]); chans['b'].append(col[2])
            # the slab fades faster than the card on it, so a faded tile
            # reads as its viewer rather than a block of family colour
            alpha = self.LayerAlpha(n['level'])
            chans['a'].append(alpha ** 2)
            chans['ca'].append(alpha)
            chans['fz'].append(z + 0.001)
            chans['sc'].append(max(s, 1e-4))
        self._writeChop(scriptOp, chans, len(self.Nodes))

    def CookFlags(self, scriptOp):
        """Lit flags on the tile edges: bypass and lock on the left,
        display and render on the right, viewer-active bottom right."""
        depth = self.ownerComp.par.Depth.eval()
        cols = self._cols
        tile = self._tile
        sc = self._scale
        fw, fh, b = tile['flagw'] * sc, tile['flagh'] * sc, tile['border'] * sc
        poses, _ = self.Layout()
        chans = {k: [] for k in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz', 'r', 'g', 'b', 'a')}
        for n, (x, y, z, s) in zip(self.Nodes, poses):
            top = n['h'] * 0.5 - b - fh * 0.5
            left = -n['w'] * 0.5 + b + fw * 0.5
            right = -left
            slots = (('bypass', left, top), ('lock', left, top - fh * 1.2),
                     ('display', right, top), ('render', right, top - fh * 1.2),
                     ('viewer', right, -n['h'] * 0.5 + b + fh * 0.5))
            badge = 'error' if n['error'] else 'warning' if n['warning'] else None
            if badge:
                slots = slots + ((badge, right + fw, n['h'] * 0.5 + fh * 0.4),)
            for flag, fx, fy in slots:
                if not n[flag]:
                    continue
                col = cols['flag_' + flag]
                chans['tx'].append(x + fx * s); chans['ty'].append(y + fy * s); chans['tz'].append(z + 0.002)
                chans['sx'].append(fw * s); chans['sy'].append(fh * s); chans['sz'].append(depth * 0.1 * max(s, 1e-4))
                chans['r'].append(col[0]); chans['g'].append(col[1]); chans['b'].append(col[2])
                chans['a'].append(self.LayerAlpha(n['level']))
        self._writeChop(scriptOp, chans, len(chans['tx']))

    def CookNotes(self, scriptOp):
        """Frames and annotations: flat panels behind the nodes."""
        depth = self.ownerComp.par.Depth.eval()
        explode = self.ownerComp.par.Explode.eval()
        chans = {k: [] for k in ('tx', 'ty', 'fz', 'fx', 'fy', 'sc', 'ca')}
        for pl in self.Panels:
            chans['sc'].append(1.0)
            # panels are see-through so they never hide nodes pushed behind them
            chans['ca'].append(self.LayerAlpha(pl['level']) * PANEL_ALPHA[pl['kind']])
            chans['tx'].append(pl['x']); chans['ty'].append(pl['y'])
            chans['fz'].append(pl['z'] - explode * pl['level'] - depth * (2.5 if pl['kind'] == 'frame' else 1.5))
            chans['fx'].append(pl['w']); chans['fy'].append(pl['h'])
        self._writeChop(scriptOp, chans, len(self.Panels))

    def CookConn(self, scriptOp):
        """Connector tabs on the node edges."""
        p = self.ownerComp.par
        depth = p.Depth.eval()
        size = self._tile['conn'] * self._scale
        poses, _ = self.Layout()
        chans = {k: [] for k in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz', 'r', 'g', 'b', 'a')}
        for c in self.Conns:
            col = self.Nodes[c['node']]['color']
            x, y, z, s = poses[c['node']]
            chans['tx'].append(x + c['dx'] * s); chans['ty'].append(y + c['dy'] * s)
            chans['tz'].append(z - depth * 0.5)
            chans['sx'].append(size * s); chans['sy'].append(size * s); chans['sz'].append(depth * 1.2 * max(s, 1e-4))
            chans['r'].append(col[0] * 0.8); chans['g'].append(col[1] * 0.8); chans['b'].append(col[2] * 0.8)
            chans['a'].append(self.LayerAlpha(self.Nodes[c['node']]['level']))
        self._writeChop(scriptOp, chans, len(self.Conns))

    @staticmethod
    def _writeChop(scriptOp, chans, n):
        scriptOp.clear()
        scriptOp.numSamples = max(1, n)
        for name, vals in chans.items():
            c = scriptOp.appendChan(name)
            c.vals = vals if n else [0.0]

    def CookWires(self, scriptOp):
        """Bezier ribbons, like the editor's wires, for every connection:
        wires inside a network, through the hierarchy (COMP <-> In/Out OP)
        and operator references. Wires that change depth keep the same
        horizontal tangents and ease from one layer to the other."""
        p = self.ownerComp.par
        width = p.Wirewidth.eval()
        segs = max(2, int(p.Wiresegs.eval()))
        depth = p.Depth.eval()
        explode = p.Explode.eval()
        show = {'in': p.Hierlinks.eval(), 'out': p.Hierlinks.eval(), 'frame': p.Framelinks.eval()}
        poses, grow = self.Layout()
        scriptOp.clear()
        scriptOp.primAttribs.create('Cd')

        def end(e):
            ni, dx, dy = e[:3]
            if ni is None:
                return (dx, dy, e[3] - explode * e[4])
            x, y, z, s = poses[ni]
            return (x + dx * s, y + dy * s, z - depth * 0.5)

        for w, g in zip(self.Wires, grow):
            kind = w['kind']
            if g <= 0.0 or not show.get(kind, True):
                continue
            p0, p3 = end(w['a']), end(w['b'])
            # handle length grows with the distance, in depth too
            dx = abs(p3[0] - p0[0])
            dz = abs(p3[2] - p0[2])
            if kind == 'frame':
                p1 = tuple(a + (b - a) / 3.0 for a, b in zip(p0, p3))
                p2 = tuple(a + (b - a) * 2.0 / 3.0 for a, b in zip(p0, p3))
            elif kind == 'comp':
                d = max(abs(p3[1] - p0[1]) * 0.5, 0.3)
                p1 = (p0[0], p0[1] - d, p0[2])
                p2 = (p3[0], p3[1] + d, p3[2])
            elif kind == 'in':
                # out of the COMP's input to the left, into the In OP from the left
                d = max(dx * 0.5, dz * 0.25, 0.3)
                p1 = (p0[0] - d, p0[1], p0[2])
                p2 = (p3[0] - d, p3[1], p3[2])
            elif kind == 'out':
                # out of the Out OP to the right, into the COMP's output from the right
                d = max(dx * 0.5, dz * 0.25, 0.3)
                p1 = (p0[0] + d, p0[1], p0[2])
                p2 = (p3[0] + d, p3[1], p3[2])
            else:
                d = max(dx * 0.5, dz * 0.25, 0.3)
                p1 = (p0[0] + d, p0[1], p0[2])
                p2 = (p3[0] - d, p3[1], p3[2])
            n = max(2, int(segs * g))
            pts = []
            for i in range(n + 1):
                t = g * i / n
                u = 1.0 - t
                k0, k1, k2, k3 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
                pts.append(tuple(k0 * p0[j] + k1 * p1[j] + k2 * p2[j] + k3 * p3[j] for j in range(3)))
            levels = [self.Nodes[e[0]]['level'] if e[0] is not None else e[4] for e in (w['a'], w['b'])]
            alpha = min(self.LayerAlpha(lv) for lv in levels)
            frame = kind == 'frame'
            self._ribbon(scriptOp, pts, width * (0.5 if frame else 1.0), w['color'] + (alpha,), dashed=frame)

    @staticmethod
    def _ribbon(scriptOp, pts, width, col, dashed=False):
        half = width * 0.5
        left, right = [], []
        for i, pt in enumerate(pts):
            a = pts[max(0, i - 1)]
            b = pts[min(len(pts) - 1, i + 1)]
            tx, ty = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(tx, ty)
            if ln < 1e-6:
                # running straight back in Z: keep the ribbon facing the camera
                nx, ny = half, 0.0
            else:
                nx, ny = -ty / ln * half, tx / ln * half
            pl = scriptOp.appendPoint(); pl.P = (pt[0] + nx, pt[1] + ny, pt[2])
            pr = scriptOp.appendPoint(); pr.P = (pt[0] - nx, pt[1] - ny, pt[2])
            left.append(pl); right.append(pr)
        for i in range(len(pts) - 1):
            if dashed and i % 2:
                continue
            poly = scriptOp.appendPoly(4, closed=True, addPoints=False)
            poly[0].point = left[i]
            poly[1].point = right[i]
            poly[2].point = right[i + 1]
            poly[3].point = left[i + 1]
            poly.Cd = (col[0], col[1], col[2], col[3])
