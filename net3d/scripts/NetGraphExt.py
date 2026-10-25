"""
NetGraphExt - rebuild a TouchDesigner network in 3D.

Scans the Target COMP (and optionally nested COMPs), records every node's
position and size from the network editor, its family, flags and wiring, and
lays the result out in world space: 1 network unit = Scale world units, the
network's +Y stays +Y, nodes face +Z. Nested networks sit behind their COMP
node, one Layer Spacing further down -Z per level.

Rendering is data-driven so it can be animated:
  inst      Script CHOP, one sample per node  -> instanced node slabs
  conn      Script CHOP, one sample per connector -> instanced connector tabs
  wires     Script SOP, bezier ribbons between connectors
  cards/    one Geometry COMP per node with a Text TOP face (and the node's
            own image when it is a TOP with a preview)
Reveal (0..1) grows the network from its sources to its outputs, Explode
pushes each node back in Z by its rank (longest path from a source).
"""

import math

# Approximate network editor colours. Edit the 'colors' table to calibrate.
DEFAULT_COLORS = {
    'bg':      (0.20, 0.20, 0.20),
    'TOP':     (0.45, 0.33, 0.62),
    'CHOP':    (0.33, 0.55, 0.30),
    'SOP':     (0.28, 0.42, 0.66),
    'DAT':     (0.66, 0.32, 0.52),
    'MAT':     (0.70, 0.60, 0.24),
    'COMP':    (0.50, 0.50, 0.50),
    'POP':     (0.76, 0.44, 0.22),
    'tile':    (0.30, 0.30, 0.30),
    'text':    (0.90, 0.90, 0.90),
    'bypass':  (0.35, 0.35, 0.35),
    'annotate': (0.30, 0.30, 0.30),
}

# op.color of a node nobody has recoloured
DEFAULT_NODE_COLOR = (0.55, 0.55, 0.55)


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


class NetGraphExt:

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.Nodes = []      # list of dicts, see _scanNetwork
        self.Wires = []      # list of dicts: src, dst (node indices), points
        self.Conns = []      # list of dicts: node, side, x, y
        self.Annotations = []
        self.MaxRank = 0
        self._sig = None

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

    def _scanNetwork(self, comp, level, center, scale, maxLevel, previews):
        """Append the nodes of one network. center = world (x, y, z) the
        network's bounding-box centre maps to."""
        ops, notes = self._visibleChildren(comp)
        if not ops and not notes:
            return
        allOps = ops + notes
        x0 = min(o.nodeX for o in allOps)
        y0 = min(o.nodeY for o in allOps)
        x1 = max(o.nodeX + o.nodeWidth for o in allOps)
        y1 = max(o.nodeY + o.nodeHeight for o in allOps)
        mx, my = (x0 + x1) * 0.5, (y0 + y1) * 0.5

        def world(nx, ny):
            return (center[0] + (nx - mx) * scale, center[1] + (ny - my) * scale)

        cols = self.Colors()
        for a in notes:
            wx, wy = world(a.nodeX, a.nodeY)
            title = ''
            for pn in ('Titletext', 'Title', 'Text'):
                p = getattr(a.par, pn, None)
                if p is not None:
                    title = str(p.eval())
                    break
            color = cols['annotate']
            if all(hasattr(a.par, n) for n in ('Backcolorr', 'Backcolorg', 'Backcolorb')):
                color = (a.par.Backcolorr.eval(), a.par.Backcolorg.eval(), a.par.Backcolorb.eval())
            elif tuple(round(c, 3) for c in a.color) != DEFAULT_NODE_COLOR:
                color = tuple(a.color)
            self.Annotations.append({
                'path': a.path, 'title': title, 'level': level, 'color': color,
                'x': wx + a.nodeWidth * scale * 0.5, 'y': wy + a.nodeHeight * scale * 0.5,
                'z': center[2], 'w': a.nodeWidth * scale, 'h': a.nodeHeight * scale,
                'netw': a.nodeWidth,
            })

        first = len(self.Nodes)
        index = {}
        for o in ops:
            wx, wy = world(o.nodeX, o.nodeY)
            fam = o.family
            famCol = cols.get(fam, cols['COMP'])
            tint = tuple(o.color)
            custom = tuple(round(c, 3) for c in tint) != DEFAULT_NODE_COLOR
            preview = ''
            if fam == 'TOP' and (previews == 'all' or (previews == 'viewer' and o.viewer)):
                preview = o.path
            n = {
                'path': o.path, 'name': o.name, 'type': o.OPType, 'family': fam,
                'level': level, 'rank': 0,
                'x': wx + o.nodeWidth * scale * 0.5, 'y': wy + o.nodeHeight * scale * 0.5,
                'z': center[2], 'w': o.nodeWidth * scale, 'h': o.nodeHeight * scale,
                'netw': o.nodeWidth, 'neth': o.nodeHeight,
                'color': famCol, 'tint': tint if custom else cols['tile'],
                'bypass': bool(getattr(o, 'bypass', False)),
                'display': bool(getattr(o, 'display', False)),
                'render': bool(getattr(o, 'render', False)),
                'preview': preview, 'ins': [], 'outs': [],
            }
            index[o.path] = len(self.Nodes)
            self.Nodes.append(n)

        # connectors and wires inside this network
        for o in ops:
            ni = index[o.path]
            n = self.Nodes[ni]
            for side, conns, vertical in (
                    ('in', o.inputConnectors, False), ('out', o.outputConnectors, False),
                    ('cin', getattr(o, 'inputCOMPConnectors', []), True),
                    ('cout', getattr(o, 'outputCOMPConnectors', []), True)):
                k = len(conns)
                for i, c in enumerate(conns):
                    f = (i + 1) / (k + 1)
                    if vertical:
                        # COMP connectors: inputs on top, outputs on the bottom
                        dx, dy = (f - 0.5) * n['w'], (0.5 if side == 'cin' else -0.5) * n['h']
                    else:
                        dx, dy = (-0.5 if side == 'in' else 0.5) * n['w'], (0.5 - f) * n['h']
                    self.Conns.append({'node': ni, 'side': side, 'dx': dx, 'dy': dy})
                    if side in ('out', 'cout'):
                        n['outs'].append((dx, dy))
                        for other in c.connections:
                            dst = index.get(other.owner.path)
                            if dst is None:
                                continue
                            self.Wires.append({'src': ni, 'dst': dst, 'srcConn': len(self.Conns) - 1,
                                               'dstPath': other.owner.path, 'dstSide': 'cin' if vertical else 'in',
                                               'dstIndex': other.index, 'vertical': vertical})
                    else:
                        n['ins'].append((dx, dy))

        self._rank(first, len(self.Nodes))

        if level < maxLevel:
            for o in ops:
                if o.isCOMP and o.OPType != 'annotateCOMP':
                    n = self.Nodes[index[o.path]]
                    self._scanNetwork(o, level + 1, (n['x'], n['y'], center[2] - self._layerSpacing),
                                      scale, maxLevel, previews)

    def _rank(self, first, last):
        """Longest-path rank from sources, for the nodes [first, last)."""
        wires = [w for w in self.Wires if first <= w['src'] < last and first <= w['dst'] < last]
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
        for i in range(first, last):
            self.MaxRank = max(self.MaxRank, self.Nodes[i]['rank'])

    def _resolveWireEnds(self):
        """Map each wire's destination to the connector record it ends on."""
        byNode = {}
        for ci, c in enumerate(self.Conns):
            byNode.setdefault((c['node'], c['side']), []).append(ci)
        for w in self.Wires:
            ends = byNode.get((w['dst'], w['dstSide']), [])
            w['dstConn'] = ends[w['dstIndex']] if w['dstIndex'] < len(ends) else (ends[0] if ends else None)
        self.Wires = [w for w in self.Wires if w['dstConn'] is not None]

    # ---- public ----------------------------------------------------

    def Rebuild(self):
        p = self.ownerComp.par
        self.Nodes, self.Wires, self.Conns, self.Annotations = [], [], [], []
        self.MaxRank = 0
        self._layerSpacing = p.Layerspacing.eval()
        target = self._target()
        if target is None or not target.isCOMP:
            debug('net3d: Target is not a COMP')
        else:
            self._scanNetwork(target, 0, (0.0, 0.0, 0.0), p.Scale.eval(),
                              int(p.Recurse.eval()), p.Previews.eval())
            self._resolveWireEnds()
        self._sig = self._signature()
        self._writeTable()
        self._buildCards()
        for name in ('inst', 'notes', 'conn', 'wires'):
            o = self.ownerComp.op(name)
            if o is not None:
                o.cook(force=True)
        render = self.ownerComp.op('render')
        bg = self.Colors()['bg']
        render.par.bgcolorr, render.par.bgcolorg, render.par.bgcolorb = bg

    def CheckChanged(self):
        """Rebuild if the target network changed (cheap enough to poll)."""
        if self._signature() != self._sig:
            self.Rebuild()

    def _signature(self):
        target = self._target()
        if target is None:
            return None
        sig = []
        maxLevel = int(self.ownerComp.par.Recurse.eval())

        def walk(comp, level):
            ops, notes = self._visibleChildren(comp)
            for o in ops + notes:
                sig.append((o.path, o.nodeX, o.nodeY, o.nodeWidth, o.nodeHeight,
                            tuple(o.color), getattr(o, 'viewer', False), getattr(o, 'bypass', False),
                            tuple(c.owner.path for ic in o.inputConnectors for c in ic.connections)))
                if level < maxLevel and o.isCOMP and o.OPType != 'annotateCOMP':
                    walk(o, level + 1)
        walk(target, 0)
        return hash(tuple(sig))

    def Frame(self):
        """Point the internal camera at the whole network."""
        cam = self.ownerComp.op('cam')
        items = self.Nodes + self.Annotations
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

    # ---- animation -------------------------------------------------

    def Layout(self):
        """Current animated pose per node: list of (x, y, z, s) where s is
        the reveal scale 0..1. Also returns per-wire growth 0..1."""
        p = self.ownerComp.par
        reveal = p.Reveal.eval()
        explode = p.Explode.eval()
        span = self.MaxRank * 2 + 1
        r = reveal * span
        poses = []
        for n in self.Nodes:
            s = _smooth(r - n['rank'] * 2)
            poses.append((n['x'], n['y'], n['z'] - explode * n['rank'], s))
        grow = []
        for w in self.Wires:
            rs, rd = self.Nodes[w['src']]['rank'], self.Nodes[w['dst']]['rank']
            start = rs * 2 + 1
            length = max(1.0, rd * 2 - start)
            grow.append(_clamp((r - start) / length))
        return poses, grow

    # ---- outputs ---------------------------------------------------

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

    def _buildCards(self):
        """One Geometry COMP per node (and per annotation) with a texture
        face. Their transforms follow the 'inst' CHOP by expression."""
        cards = self.ownerComp.op('cards')
        for c in list(cards.children):
            c.destroy()
        p = self.ownerComp.par
        cols = self.Colors()
        res = p.Labelres.eval()

        def makeCard(name, idx, w, h, netw, neth, text, bg, fg, alignTop, preview, isNote):
            top = cards.create(textTOP, name + '_txt')
            _setpar(top, 'resolutionw', max(16, int(netw * res)))
            _setpar(top, 'resolutionh', max(16, int(neth * res)))
            _setpar(top, 'outputresolution', 'custom')
            top.par.text = text
            _setpar(top, 'fontsizex', 14 * res)
            _setpar(top, 'alignx', 'left' if isNote else 'center')
            _setpar(top, 'aligny', 'top' if alignTop else 'bottom')
            _setpar(top, 'positionx', 8 * res if isNote else 0)
            _setpar(top, 'positiony', -6 * res if alignTop else 6 * res)
            _setpar(top, 'fontcolorr', fg[0]); _setpar(top, 'fontcolorg', fg[1]); _setpar(top, 'fontcolorb', fg[2])
            _setpar(top, 'bgcolorr', bg[0]); _setpar(top, 'bgcolorg', bg[1]); _setpar(top, 'bgcolorb', bg[2])
            _setpar(top, 'bgalpha', 1)
            tex = top
            if preview:
                # node image fills the tile, name strip stays readable on top
                sel = cards.create(selectTOP, name + '_img')
                sel.par.top = preview
                _setpar(sel, 'outputresolution', 'custom')
                _setpar(sel, 'resolutionw', max(16, int(netw * res)))
                _setpar(sel, 'resolutionh', max(16, int(neth * res)))
                _setpar(top, 'bgalpha', 0)
                over = cards.create(overTOP, name + '_comp')
                over.inputConnectors[0].connect(top)
                over.inputConnectors[1].connect(sel)
                _setpar(over, 'outputresolution', 'input')
                for o_ in (sel, over):
                    o_.nodeY = top.nodeY - 150
                tex = over
            mat = cards.create(constantMAT, name + '_mat')
            mat.par.colormap = tex.name
            geo = cards.create(geometryCOMP, name)
            for c in list(geo.children):
                c.destroy()
            sel = geo.create(selectSOP, 'quad')
            sel.par.sop = '../../quad'
            sel.render = sel.display = True
            geo.par.material = mat.name
            # op paths in parameters resolve from the operator's own network
            src = "op('../{0}')".format('inst' if not isNote else 'notes')
            geo.par.tx.expr = "{0}['tx'][{1}]".format(src, idx)
            geo.par.ty.expr = "{0}['ty'][{1}]".format(src, idx)
            geo.par.tz.expr = "{0}['fz'][{1}]".format(src, idx)
            geo.par.sx.expr = "{0}['fx'][{1}]".format(src, idx)
            geo.par.sy.expr = "{0}['fy'][{1}]".format(src, idx)
            # tidy layout inside 'cards'
            row = idx % 20
            col = idx // 20
            base = 600 if isNote else 0
            for k, o_ in enumerate((top, mat, geo)):
                o_.nodeX = col * 600 + k * 180
                o_.nodeY = -row * 300 - base * 10

        for i, n in enumerate(self.Nodes):
            bg = cols['bypass'] if n['bypass'] else n['tint']
            makeCard('n{}'.format(i), i, n['w'], n['h'], n['netw'], n['neth'], n['name'],
                     bg, cols['text'], False, n['preview'], False)
        for i, a in enumerate(self.Annotations):
            netw = max(64, a['netw'])
            neth = netw * a['h'] / max(1e-6, a['w'])
            makeCard('a{}'.format(i), i, a['w'], a['h'], netw, neth, a['title'],
                     a['color'], cols['text'], True, '', True)

    # ---- cook callbacks (Script CHOP / SOP) ------------------------

    def CookInst(self, scriptOp):
        """Node slabs: tx ty tz sx sy sz r g b, plus card face fz fx fy."""
        p = self.ownerComp.par
        depth = p.Depth.eval()
        poses, _ = self.Layout()
        chans = {k: [] for k in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz', 'r', 'g', 'b', 'fz', 'fx', 'fy')}
        for n, (x, y, z, s) in zip(self.Nodes, poses):
            # border: the tile face is inset, the slab around it shows the family colour
            col = n['color'] if not n['bypass'] else (0.3, 0.3, 0.3)
            chans['tx'].append(x); chans['ty'].append(y); chans['tz'].append(z - depth * 0.5)
            chans['sx'].append(n['w'] * s); chans['sy'].append(n['h'] * s); chans['sz'].append(depth * max(s, 1e-4))
            chans['r'].append(col[0]); chans['g'].append(col[1]); chans['b'].append(col[2])
            inset = p.Border.eval()
            chans['fz'].append(z + 0.001)
            chans['fx'].append(max(0.0, n['w'] - inset * 2) * s)
            chans['fy'].append(max(0.0, n['h'] - inset * 2) * s)
        self._writeChop(scriptOp, chans, len(self.Nodes))

    def CookNotes(self, scriptOp):
        """Annotations: flat panels behind the nodes, shown from the start."""
        p = self.ownerComp.par
        chans = {k: [] for k in ('tx', 'ty', 'fz', 'fx', 'fy')}
        for a in self.Annotations:
            chans['tx'].append(a['x']); chans['ty'].append(a['y'])
            chans['fz'].append(a['z'] - p.Depth.eval() * 1.5)
            chans['fx'].append(a['w']); chans['fy'].append(a['h'])
        self._writeChop(scriptOp, chans, len(self.Annotations))

    def CookConn(self, scriptOp):
        """Connector tabs on the node edges."""
        p = self.ownerComp.par
        depth = p.Depth.eval()
        size = p.Connsize.eval()
        poses, _ = self.Layout()
        chans = {k: [] for k in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz', 'r', 'g', 'b')}
        for c in self.Conns:
            n = self.Nodes[c['node']]
            x, y, z, s = poses[c['node']]
            chans['tx'].append(x + c['dx'] * s); chans['ty'].append(y + c['dy'] * s)
            chans['tz'].append(z - depth * 0.5)
            chans['sx'].append(size * s); chans['sy'].append(size * s); chans['sz'].append(depth * 1.2 * max(s, 1e-4))
            col = n['color']
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
        """Bezier ribbons from output to input connector, like the editor."""
        p = self.ownerComp.par
        width = p.Wirewidth.eval()
        segs = max(2, int(p.Wiresegs.eval()))
        depth = p.Depth.eval()
        poses, grow = self.Layout()
        scriptOp.clear()
        scriptOp.primAttribs.create('Cd', (1.0, 1.0, 1.0, 1.0))
        for w, g in zip(self.Wires, grow):
            if g <= 0.0:
                continue
            a, b = self.Conns[w['srcConn']], self.Conns[w['dstConn']]
            sx, sy, sz, ss = poses[a['node']]
            dx, dy, dz, ds = poses[b['node']]
            p0 = (sx + a['dx'] * ss, sy + a['dy'] * ss, sz - depth * 0.5)
            p3 = (dx + b['dx'] * ds, dy + b['dy'] * ds, dz - depth * 0.5)
            if w['vertical']:
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
            col = self.Nodes[w['src']]['color']
            self._ribbon(scriptOp, pts, width, col)

    @staticmethod
    def _ribbon(scriptOp, pts, width, col):
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
            poly = scriptOp.appendPoly(4, closed=True, addPoints=False)
            poly[0].point = left[i]
            poly[1].point = right[i]
            poly[2].point = right[i + 1]
            poly[3].point = left[i + 1]
            poly.Cd = (col[0], col[1], col[2], 1.0)
