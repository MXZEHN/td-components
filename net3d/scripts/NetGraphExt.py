"""
NetGraphExt - rebuild a TouchDesigner network in 3D.

Scans the Target COMP (and optionally nested COMPs), records every node's
position and size from the network editor, its family, flags and wiring, and
lays the result out in world space: 1 network unit = Scale world units, the
network's +Y stays +Y, nodes face +Z.

Hierarchy is stacked along X: the target network keeps its own coordinates,
each nested network (depth first) gets the next slot to the right, centred
vertically on its COMP node, inside a titled frame. Hierarchy links join a
COMP to its network: COMP input -> In OP, Out OP -> COMP output, and a link
from the COMP to the frame.

Rendering is data-driven so it can be animated:
  inst      Script CHOP, one sample per node -> instanced node slabs
  conn      Script CHOP, one sample per connector -> instanced connector tabs
  notes     Script CHOP, one sample per panel (frames, annotations)
  wires     Script SOP, bezier ribbons between connectors
  cards/    one Geometry COMP per node and panel with a Text TOP face (and the
            node's own image when it is a TOP with a preview)
Reveal (0..1) grows the network from its sources to its outputs, Explode
pushes each node back in Z by its rank (longest path from a source).

Live mode polls the network every few frames and updates in place: new
operators grow in over Birth Time, and the internal camera follows the
newest (or last moved) operator.
"""

import math

# Approximate network editor colours. Edit the 'colors' table to calibrate.
DEFAULT_COLORS = {
    'bg':       (0.20, 0.20, 0.20),
    'TOP':      (0.45, 0.33, 0.62),
    'CHOP':     (0.33, 0.55, 0.30),
    'SOP':      (0.28, 0.42, 0.66),
    'DAT':      (0.66, 0.32, 0.52),
    'MAT':      (0.70, 0.60, 0.24),
    'COMP':     (0.50, 0.50, 0.50),
    'POP':      (0.76, 0.44, 0.22),
    'tile':     (0.30, 0.30, 0.30),
    'text':     (0.90, 0.90, 0.90),
    'type':     (0.60, 0.60, 0.60),
    'bypass':   (0.35, 0.35, 0.35),
    'annotate': (0.30, 0.30, 0.30),
    'frame':    (0.25, 0.25, 0.25),
    'hier':     (0.80, 0.80, 0.80),
}

# op.color of a node nobody has recoloured
DEFAULT_NODE_COLOR = (0.55, 0.55, 0.55)

# padding around a nested network's frame, in network units
FRAME_PAD = 60


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _smooth(v):
    v = _clamp(v)
    return v * v * (3.0 - 2.0 * v)


def _setpar(o, name, value):
    """Set a parameter if it exists; parameter names differ between builds."""
    p = getattr(o.par, name, None)
    if p is not None:
        p.val = value
        return True
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
        self._cols = self.Colors()
        self._scale = p.Scale.eval()
        self._gap = p.Networkgap.eval()
        self._maxLevel = int(p.Recurse.eval())
        self._previews = p.Previews.eval()
        self._cursorX = 0.0
        target = self._target()
        if target is None or not target.isCOMP:
            debug('net3d: Target is not a COMP')
            return
        self._scanNetwork(target, 0, None, 0)

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
            ox, oy = 0.0, 0.0
        else:
            # next slot along X, vertically centred on the COMP node
            pn = self.Nodes[parentNode]
            ox = self._cursorX + FRAME_PAD * s - x0 * s
            oy = pn['y'] - (y0 + y1) * 0.5 * s

        def world(nx, ny):
            return ox + nx * s, oy + ny * s

        fx0, fy0 = world(x0 - FRAME_PAD, y0 - FRAME_PAD)
        fx1, fy1 = world(x1 + FRAME_PAD, y1 + FRAME_PAD)
        self._cursorX = max(self._cursorX, fx1 + self._gap)
        cols = self._cols

        if self._maxLevel > 0:
            self.Panels.append({
                'key': 'frame:' + comp.path, 'title': comp.path, 'kind': 'frame',
                'x': (fx0 + fx1) * 0.5, 'y': (fy0 + fy1) * 0.5,
                'w': fx1 - fx0, 'h': fy1 - fy0, 'netw': (x1 - x0) + FRAME_PAD * 2,
                'color': cols['frame'],
            })
            if parentNode is not None:
                pn = self.Nodes[parentNode]
                self.Wires.append({
                    'a': (parentNode, pn['w'] * 0.5, 0.0), 'b': (None, fx0, (fy0 + fy1) * 0.5),
                    'rs': pn['rank'], 'rd': baseRank, 'kind': 'hier', 'color': cols['hier']})

        for a in notes:
            wx, wy = world(a.nodeX, a.nodeY)
            title = ''
            for pn_ in ('Titletext', 'Title', 'Text'):
                par = getattr(a.par, pn_, None)
                if par is not None:
                    title = str(par.eval())
                    break
            color = cols['annotate']
            if all(hasattr(a.par, n) for n in ('Backcolorr', 'Backcolorg', 'Backcolorb')):
                color = (a.par.Backcolorr.eval(), a.par.Backcolorg.eval(), a.par.Backcolorb.eval())
            elif tuple(round(c, 3) for c in a.color) != DEFAULT_NODE_COLOR:
                color = tuple(a.color)
            self.Panels.append({
                'key': a.path, 'title': title, 'kind': 'annotate',
                'x': wx + a.nodeWidth * s * 0.5, 'y': wy + a.nodeHeight * s * 0.5,
                'w': a.nodeWidth * s, 'h': a.nodeHeight * s, 'netw': a.nodeWidth,
                'color': color,
            })

        first = len(self.Nodes)
        local = {}
        for o in ops:
            wx, wy = world(o.nodeX, o.nodeY)
            fam = o.family
            tint = tuple(o.color)
            custom = tuple(round(c, 3) for c in tint) != DEFAULT_NODE_COLOR
            preview = ''
            if fam == 'TOP' and (self._previews == 'all' or (self._previews == 'viewer' and o.viewer)):
                preview = o.path
            n = {
                'path': o.path, 'name': o.name, 'type': o.OPType, 'label': _typeLabel(o),
                'family': fam, 'level': level, 'rank': baseRank,
                'nx': o.nodeX, 'ny': o.nodeY,
                'x': wx + o.nodeWidth * s * 0.5, 'y': wy + o.nodeHeight * s * 0.5, 'z': 0.0,
                'w': o.nodeWidth * s, 'h': o.nodeHeight * s,
                'netw': o.nodeWidth, 'neth': o.nodeHeight,
                'color': cols.get(fam, cols['COMP']), 'tint': tint if custom else cols['tile'],
                'bypass': bool(getattr(o, 'bypass', False)),
                'preview': preview, 'conns': {},
            }
            local[o.path] = len(self.Nodes)
            self._index[o.path] = len(self.Nodes)
            self.Nodes.append(n)

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

        if level < self._maxLevel:
            for o in ops:
                if o.isCOMP:
                    ni = local[o.path]
                    before = len(self.Nodes)
                    self._scanNetwork(o, level + 1, ni, self.Nodes[ni]['rank'] + 1)
                    if len(self.Nodes) > before:
                        self._linkInOut(o, ni)

    def _linkInOut(self, comp, ni):
        """Hierarchy links: COMP input i -> its In OP, Out OP -> COMP output i."""
        n = self.Nodes[ni]
        col = self._cols['hier']
        for i, c in enumerate(comp.inputConnectors):
            inner = getattr(c, 'inOP', None)
            di = self._index.get(inner.path) if inner is not None else None
            if di is None:
                continue
            d = self.Nodes[di]
            self.Wires.append({'a': (ni,) + n['conns']['in'][i], 'b': (di, -d['w'] * 0.5, 0.0),
                               'rs': n['rank'], 'rd': d['rank'], 'kind': 'hier', 'color': col})
        for i, c in enumerate(comp.outputConnectors):
            inner = getattr(c, 'outOP', None)
            si = self._index.get(inner.path) if inner is not None else None
            if si is None:
                continue
            sn = self.Nodes[si]
            self.Wires.append({'a': (si, sn['w'] * 0.5, 0.0), 'b': (ni,) + n['conns']['out'][i],
                               'rs': sn['rank'], 'rd': n['rank'] + 1, 'kind': 'hier', 'color': col})

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
            (n['path'], n['name'], n['type'], n['tint'], n['bypass'], n['preview'],
             n['netw'], n['neth'], round(n['x'], 4), round(n['y'], 4)) for n in self.Nodes) +
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
        if live:
            # keep cooking while operators are still growing in
            birth = p.Birthtime.eval()
            if any(now - b < birth for b in self._born.values()):
                self._cook()
            if p.Follow.eval():
                self._follow(dt)

    def Frame(self):
        """Point the internal camera at the whole network."""
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
        fov = math.radians(cam.par.fov.eval())
        half = max((y1 - y0) * 0.5, (x1 - x0) * 0.5 / aspect) * 1.1
        cam.par.tx = (x0 + x1) * 0.5
        cam.par.ty = (y0 + y1) * 0.5
        cam.par.tz = half / math.tan(fov * 0.5)
        cam.par.rx = cam.par.ry = cam.par.rz = 0
        self._camPos = None

    def Focus(self, path):
        """Make the live camera fly to the operator at path."""
        self._focus = path

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
        cx, cy, cz = self._camPos
        dx, dy, dz = (self._camLook[0] - cx, self._camLook[1] - cy, self._camLook[2] - cz)
        cam.par.tx, cam.par.ty, cam.par.tz = cx, cy, cz
        # camera looks down -Z; rotate order XYZ = pitch, then yaw
        cam.par.ry = math.degrees(math.atan2(-dx, -dz))
        cam.par.rx = math.degrees(math.atan2(dy, math.hypot(dx, dz)))
        cam.par.rz = 0

    # ---- animation -------------------------------------------------

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
            poses.append((n['x'], n['y'], n['z'] - explode * n['rank'], s))
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
        for name in ('inst', 'notes', 'conn', 'wires'):
            o = self.ownerComp.op(name)
            if o is not None:
                o.cook(force=True)

    def _writeTable(self):
        t = self.ownerComp.op('nodes')
        if t is None:
            return
        t.clear()
        t.appendRow(['index', 'path', 'name', 'family', 'type', 'level', 'rank',
                     'x', 'y', 'z', 'w', 'h', 'preview'])
        for i, n in enumerate(self.Nodes):
            t.appendRow([i, n['path'], n['name'], n['family'], n['type'], n['level'], n['rank'],
                         round(n['x'], 4), round(n['y'], 4), round(n['z'], 4),
                         round(n['w'], 4), round(n['h'], 4), n['preview']])

    def _syncCards(self):
        """One Geometry COMP per node and panel with a texture face, keyed
        by path so live edits only touch what changed. Their transforms
        follow the 'inst' / 'notes' CHOPs by expression."""
        cards = self.ownerComp.op('cards')
        cols = self._cols
        res = self.ownerComp.par.Labelres.eval()
        wanted = {}
        for i, n in enumerate(self.Nodes):
            bg = cols['bypass'] if n['bypass'] else n['tint']
            wanted[n['path']] = ('inst', i, dict(
                netw=n['netw'], neth=n['neth'], text=n['name'], label=n['label'], bg=bg,
                preview=n['preview'], panel=False))
        for i, pl in enumerate(self.Panels):
            netw = max(64, pl['netw'])
            wanted['panel:' + pl['key']] = ('notes', i, dict(
                netw=netw, neth=netw * pl['h'] / max(1e-6, pl['w']), text=pl['title'], label='',
                bg=pl['color'], preview='', panel=True))

        for key in list(self._cards):
            if key not in wanted:
                cid, _ = self._cards.pop(key)
                for c in cards.ops('c{}_*'.format(cid)) + cards.ops('c{}'.format(cid)):
                    c.destroy()

        for key, (src, idx, spec) in wanted.items():
            content = (int(spec['netw'] * res), int(spec['neth'] * res), spec['preview'], spec['panel'])
            have = self._cards.get(key)
            if have is not None and have[1] != content:
                for c in cards.ops('c{}_*'.format(have[0])) + cards.ops('c{}'.format(have[0])):
                    c.destroy()
                have = None
            if have is None:
                cid = self._nextCard
                self._nextCard += 1
                self._makeCard(cards, cid, spec, res)
                self._cards[key] = (cid, content)
            cid = self._cards[key][0]
            self._styleCard(cards, cid, spec, cols)
            geo = cards.op('c{}'.format(cid))
            ref = "op('../{0}')".format(src)
            geo.par.tx.expr = "{0}['tx'][{1}]".format(ref, idx)
            geo.par.ty.expr = "{0}['ty'][{1}]".format(ref, idx)
            geo.par.tz.expr = "{0}['fz'][{1}]".format(ref, idx)
            geo.par.sx.expr = "{0}['fx'][{1}]".format(ref, idx)
            geo.par.sy.expr = "{0}['fy'][{1}]".format(ref, idx)

    def _makeCard(self, cards, cid, spec, res):
        name = 'c{}'.format(cid)
        w = max(16, int(spec['netw'] * res))
        h = max(16, int(spec['neth'] * res))
        layers = []
        txt = cards.create(textTOP, name + '_name')
        layers.append(txt)
        if spec['preview']:
            img = cards.create(selectTOP, name + '_img')
            img.par.top = spec['preview']
            layers.append(img)
        elif not spec['panel']:
            typ = cards.create(textTOP, name + '_type')
            layers.insert(0, typ)
        for t in layers:
            _setpar(t, 'outputresolution', 'custom')
            _setpar(t, 'resolutionw', w)
            _setpar(t, 'resolutionh', h)
        tex = layers[-1]
        for k in range(len(layers) - 2, -1, -1):
            over = cards.create(overTOP, '{}_over{}'.format(name, k))
            over.inputConnectors[0].connect(layers[k])
            over.inputConnectors[1].connect(tex)
            tex = over
        mat = cards.create(constantMAT, name + '_mat')
        mat.par.colormap = tex.name
        geo = cards.create(geometryCOMP, name)
        for c in list(geo.children):
            c.destroy()
        quad = geo.create(selectSOP, 'quad')
        quad.par.sop = '../../quad'
        quad.render = quad.display = True
        geo.par.material = mat.name
        # tidy layout inside 'cards'
        x, y = (cid % 8) * 900, -(cid // 8) * 250
        for k, o_ in enumerate(cards.ops(name + '_*') + [geo]):
            o_.nodeX, o_.nodeY = x + k * 130, y

    def _styleCard(self, cards, cid, spec, cols):
        name = 'c{}'.format(cid)
        res = self.ownerComp.par.Labelres.eval()
        txt = cards.op(name + '_name')
        txt.par.text = spec['text']
        panel = spec['panel']
        _setpar(txt, 'fontsizex', (16 if panel else 14) * res)
        _setpar(txt, 'alignx', 'left' if panel else 'center')
        _setpar(txt, 'aligny', 'top' if panel else 'bottom')
        _setpar(txt, 'positionx', 10 * res if panel else 0)
        _setpar(txt, 'positiony', -8 * res if panel else 6 * res)
        fg = cols['text']
        _setpar(txt, 'fontcolorr', fg[0]); _setpar(txt, 'fontcolorg', fg[1]); _setpar(txt, 'fontcolorb', fg[2])
        bg = spec['bg']
        _setpar(txt, 'bgcolorr', bg[0]); _setpar(txt, 'bgcolorg', bg[1]); _setpar(txt, 'bgcolorb', bg[2])
        _setpar(txt, 'bgalpha', 0 if spec['preview'] else 1)
        typ = cards.op(name + '_type')
        if typ is not None:
            # operator type where the editor draws its icon
            typ.par.text = spec['label']
            tc = cols['type']
            _setpar(typ, 'fontsizex', 20 * res)
            _setpar(typ, 'alignx', 'center')
            _setpar(typ, 'aligny', 'center')
            _setpar(typ, 'positiony', 8 * res)
            _setpar(typ, 'fontcolorr', tc[0]); _setpar(typ, 'fontcolorg', tc[1]); _setpar(typ, 'fontcolorb', tc[2])
            _setpar(typ, 'bgalpha', 0)

    # ---- cook callbacks (Script CHOP / SOP) ------------------------

    def CookInst(self, scriptOp):
        """Node slabs: tx ty tz sx sy sz r g b, plus card face fz fx fy."""
        p = self.ownerComp.par
        depth = p.Depth.eval()
        inset = p.Border.eval()
        poses, _ = self.Layout()
        chans = {k: [] for k in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz', 'r', 'g', 'b', 'fz', 'fx', 'fy')}
        for n, (x, y, z, s) in zip(self.Nodes, poses):
            # the tile face is inset, the slab around it shows the family colour
            col = n['color'] if not n['bypass'] else (0.3, 0.3, 0.3)
            chans['tx'].append(x); chans['ty'].append(y); chans['tz'].append(z - depth * 0.5)
            chans['sx'].append(n['w'] * s); chans['sy'].append(n['h'] * s); chans['sz'].append(depth * max(s, 1e-4))
            chans['r'].append(col[0]); chans['g'].append(col[1]); chans['b'].append(col[2])
            chans['fz'].append(z + 0.001)
            chans['fx'].append(max(0.0, n['w'] - inset * 2) * s)
            chans['fy'].append(max(0.0, n['h'] - inset * 2) * s)
        self._writeChop(scriptOp, chans, len(self.Nodes))

    def CookNotes(self, scriptOp):
        """Frames and annotations: flat panels behind the nodes."""
        depth = self.ownerComp.par.Depth.eval()
        chans = {k: [] for k in ('tx', 'ty', 'fz', 'fx', 'fy')}
        for pl in self.Panels:
            chans['tx'].append(pl['x']); chans['ty'].append(pl['y'])
            chans['fz'].append(-depth * (2.5 if pl['kind'] == 'frame' else 1.5))
            chans['fx'].append(pl['w']); chans['fy'].append(pl['h'])
        self._writeChop(scriptOp, chans, len(self.Panels))

    def CookConn(self, scriptOp):
        """Connector tabs on the node edges."""
        p = self.ownerComp.par
        depth = p.Depth.eval()
        size = p.Connsize.eval()
        poses, _ = self.Layout()
        chans = {k: [] for k in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz', 'r', 'g', 'b')}
        for c in self.Conns:
            col = self.Nodes[c['node']]['color']
            x, y, z, s = poses[c['node']]
            chans['tx'].append(x + c['dx'] * s); chans['ty'].append(y + c['dy'] * s)
            chans['tz'].append(z - depth * 0.5)
            chans['sx'].append(size * s); chans['sy'].append(size * s); chans['sz'].append(depth * 1.2 * max(s, 1e-4))
            chans['r'].append(col[0] * 0.8); chans['g'].append(col[1] * 0.8); chans['b'].append(col[2] * 0.8)
        self._writeChop(scriptOp, chans, len(self.Conns))

    @staticmethod
    def _writeChop(scriptOp, chans, n):
        scriptOp.clear()
        scriptOp.numSamples = max(1, n)
        for name, vals in chans.items():
            c = scriptOp.appendChan(name)
            c.vals = vals if n else [0.0]

    def CookWires(self, scriptOp):
        """Bezier ribbons from output to input connector, like the editor.
        Hierarchy links are straight and dashed."""
        p = self.ownerComp.par
        width = p.Wirewidth.eval()
        segs = max(2, int(p.Wiresegs.eval()))
        depth = p.Depth.eval()
        showHier = p.Hierlinks.eval()
        poses, grow = self.Layout()
        scriptOp.clear()
        scriptOp.primAttribs.create('Cd', (1.0, 1.0, 1.0, 1.0))

        def end(e):
            ni, dx, dy = e
            if ni is None:
                return (dx, dy, -depth * 0.5)
            x, y, z, s = poses[ni]
            return (x + dx * s, y + dy * s, z - depth * 0.5)

        for w, g in zip(self.Wires, grow):
            if g <= 0.0 or (w['kind'] == 'hier' and not showHier):
                continue
            p0, p3 = end(w['a']), end(w['b'])
            if w['kind'] == 'hier':
                p1 = tuple(a + (b - a) / 3.0 for a, b in zip(p0, p3))
                p2 = tuple(a + (b - a) * 2.0 / 3.0 for a, b in zip(p0, p3))
            elif w['kind'] == 'comp':
                d = max(abs(p3[1] - p0[1]) * 0.5, 0.3)
                p1 = (p0[0], p0[1] - d, p0[2])
                p2 = (p3[0], p3[1] + d, p3[2])
            else:
                d = max(abs(p3[0] - p0[0]) * 0.5, 0.3)
                p1 = (p0[0] + d, p0[1], p0[2])
                p2 = (p3[0] - d, p3[1], p3[2])
            n = max(2, int(segs * g))
            pts = []
            for i in range(n + 1):
                t = g * i / n
                u = 1.0 - t
                k0, k1, k2, k3 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
                pts.append(tuple(k0 * p0[j] + k1 * p1[j] + k2 * p2[j] + k3 * p3[j] for j in range(3)))
            kind = w['kind']
            self._ribbon(scriptOp, pts, width * (0.6 if kind == 'hier' else 1.0), w['color'],
                         dashed=kind == 'hier')

    @staticmethod
    def _ribbon(scriptOp, pts, width, col, dashed=False):
        half = width * 0.5
        left, right = [], []
        for i, pt in enumerate(pts):
            a = pts[max(0, i - 1)]
            b = pts[min(len(pts) - 1, i + 1)]
            tx, ty = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(tx, ty) or 1.0
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
            poly.Cd = (col[0], col[1], col[2], 1.0)
