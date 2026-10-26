# Runs the real NetGraphExt against a stand-in TD network and dumps what the
# component would put in its CHOPs, SOP and cards, for an offline preview render.
import sys, types, builtins, json
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else '../scripts')
builtins.debug = print
builtins.absTime = types.SimpleNamespace(seconds=0.0, frame=0)

class P:
    def __init__(s, v): s.v = v
    def eval(s): return s.v
class Par:
    def __init__(s, **kw):
        for k, v in kw.items(): object.__setattr__(s, k, P(v))
    def __setattr__(s, k, v): object.__setattr__(s, k, P(v))
class Conn:
    def __init__(s, owner, idx): s.owner, s.index, s.connections = owner, idx, []
class Op:
    def __init__(s, parent, name, fam, typ, x, y, nin=1, nout=1, **flags):
        s.name, s.family, s.nodeX, s.nodeY = name, fam, x, y
        s.nodeWidth, s.nodeHeight = 130, 90
        s.path = parent.path + '/' + name if parent else '/' + name
        s.OPType = typ + fam; s.color = (0.67, 0.67, 0.67); s.expose = True
        s.isCOMP = fam == 'COMP'; s.children = []; s.par = types.SimpleNamespace()
        for f in ('viewer', 'bypass', 'lock', 'display', 'render', 'current', 'selected'):
            setattr(s, f, flags.get(f, False))
        s.inputConnectors = [Conn(s, i) for i in range(nin)]
        s.outputConnectors = [Conn(s, i) for i in range(nout)]
        if parent: parent.children.append(s)
def W(a, b, i=0):
    a.outputConnectors[0].connections.append(b.inputConnectors[i])
    b.inputConnectors[i].connections.append(a.outputConnectors[0])

proj = Op(None, 'project1', 'COMP', 'container', 0, 0)
mf = Op(proj, 'moviefilein1', 'TOP', 'moviefilein', 0, 0, nin=0)
lv = Op(proj, 'level1', 'TOP', 'level', 200, 0)
fx = Op(proj, 'fx', 'COMP', 'base', 400, 0)
nz = Op(proj, 'noise1', 'TOP', 'noise', 400, -160, nin=0)
cp = Op(proj, 'comp1', 'TOP', 'composite', 600, 0, nin=2)
nl = Op(proj, 'null1', 'TOP', 'null', 800, 0, display=True, viewer=True, current=True)
W(mf, lv); W(lv, fx); W(fx, cp, 0); W(nz, cp, 1); W(cp, nl)
lf = Op(proj, 'lfo1', 'CHOP', 'lfo', 0, -400, nin=0)
ma = Op(proj, 'math1', 'CHOP', 'math', 200, -400)
fl = Op(proj, 'filter1', 'CHOP', 'filter', 400, -400, bypass=True)
n2 = Op(proj, 'null2', 'CHOP', 'null', 600, -400, selected=True)
W(lf, ma); W(ma, fl); W(fl, n2)
bx = Op(proj, 'box1', 'SOP', 'box', 800, -400, nin=0)
tr = Op(proj, 'transform1', 'SOP', 'transform', 1000, -400, display=True, render=True)
W(bx, tr)
tb = Op(proj, 'table1', 'DAT', 'table', 0, 250, nin=0)
sd = Op(proj, 'select1', 'DAT', 'select', 200, 250)
W(tb, sd)
Op(proj, 'constant1', 'MAT', 'constant', 1000, 0, nin=0, nout=0)
note = Op(proj, 'annotate1', 'COMP', 'annotate', -40, -480, nin=0, nout=0)
note.OPType = 'annotateCOMP'; note.nodeWidth, note.nodeHeight = 780, 330
note.par = types.SimpleNamespace(Titletext=P('Control'), Bodytext=P('LFO drives the levels. Bypass filter1 to compare, null2 feeds the export.'))

i1 = Op(fx, 'in1', 'TOP', 'in', 0, 0, nin=0)
bl = Op(fx, 'blur1', 'TOP', 'blur', 200, 0)
gl = Op(fx, 'glow', 'COMP', 'base', 400, 0)
ed = Op(fx, 'edge1', 'TOP', 'edge', 400, -170)
ad = Op(fx, 'add1', 'TOP', 'add', 600, 0, nin=2)
o1 = Op(fx, 'out1', 'TOP', 'out', 800, 0)
W(i1, bl); W(bl, gl); W(bl, ed); W(gl, ad, 0); W(ed, ad, 1); W(ad, o1)
fx.inputConnectors[0].inOP = i1; fx.outputConnectors[0].outOP = o1
gi = Op(gl, 'in1', 'TOP', 'in', 0, 0, nin=0)
th = Op(gl, 'threshold1', 'TOP', 'threshold', 200, 0)
bb = Op(gl, 'blur2', 'TOP', 'blur', 400, 0)
go = Op(gl, 'out1', 'TOP', 'out', 600, 0)
W(gi, th); W(th, bb); W(bb, go)
gl.inputConnectors[0].inOP = gi; gl.outputConnectors[0].outOP = go
# operator references across levels
class RefPar:
    isOP = True
    def __init__(s, target): s.target = target
    def eval(s): return s.target
s1 = Op(proj, 'select2', 'TOP', 'select', 1000, -170, nin=0)
s1.pars = lambda: [RefPar(ed)]
s2 = Op(gl, 'select1', 'TOP', 'select', 400, -170, nin=0)
s2.pars = lambda: [RefPar(bl)]

# stand-in operator tree for the cards
class AnyPar:
    def __init__(s): object.__setattr__(s, '_p', {})
    def __getattr__(s, k):
        if k not in s._p: s._p[k] = types.SimpleNamespace(val=None, expr=None)
        return s._p[k]
    def __setattr__(s, k, v): getattr(s, k).val = v
class TOp:
    def __init__(s, kind, name, parent):
        s.kind, s.name, s.parentop, s.par, s.kids = kind, name, parent, AnyPar(), {}
        s.inputConnectors = [types.SimpleNamespace(connect=lambda o: None)]
        s.nodeX = s.nodeY = 0; s.render = s.display = False
    @property
    def children(s): return list(s.kids.values())
    def create(s, kind, name): o = TOp(kind.__name__, name, s); s.kids[name] = o; return o
    def op(s, name): return s.kids.get(name)
    def destroy(s): del s.parentop.kids[s.name]
    def store(s, k, v): s.__dict__.setdefault('_store', {})[k] = v
    def fetch(s, k, d=None): return s.__dict__.get('_store', {}).get(k, d)
for k in ('geometryCOMP', 'selectTOP', 'fitTOP', 'textTOP', 'constantMAT', 'selectSOP', 'opviewerTOP',
          'cropTOP', 'cacheTOP', 'circleTOP', 'constantTOP'):
    setattr(builtins, k, type(k, (), {}))
cards = TOp('geometryCOMP', 'cards', None)
cam = types.SimpleNamespace(par=Par(tx=0.0, ty=0.0, tz=10.0, rx=0, ry=0, rz=0, fov=45))
ops = {'cards': cards, 'cam': cam}
owner = types.SimpleNamespace(path='/project1/net3d', op=lambda n: ops.get(n), parent=lambda: proj,
    par=Par(Target=proj, Recurse=2, Scale=0.01, Layerspacing=8, Frontopacity=0.08, Followeditor=True, Transitiontime=1.2, Previews='all', Tilesource='captured', Uilayer=True, Chrome='editor', Uihold=2.5, Uifade=0.25, Showcursor=True, Showclicks=True, Showkeys=True, Showmouse=True, Uidebug=False, Cursorsize=7, Mousecaloffsetx=0, Mousecaloffsety=0, Mousecalscalex=1, Mousecalscaley=1, Netcaloffsetx=0, Netcaloffsety=0, Netcalscale=1, Res1=1920, Res2=1080, Pathbarheight=28, Windowinsetx=0, Windowinsety=0, Cameramode='mirror', Uidepth=0.03, Annotations='typewriter', Typespeed=30, Approach=0.2, Reveal=1.0, Explode=0.0,
            Depth=0.12, Wirewidth=0.035, Wiresegs=32, Hierlinks=True, References=True, Framelinks=False, Live=False, Livepoll=3, Birthtime=0.6,
            Follow=False, Followoffsetx=0.6, Followoffsety=-0.4, Followoffsetz=3, Followsmooth=0.5,
            Autorebuild=True, Refpulses=True, Paramtags='new', Taghold=3.0, Labelres=3, Viewerres=2, Highlight=True, Layeropacity=0.35, Focuslevel=0))
import NetGraphExt as M
e = M.NetGraphExt(owner)
e.Update(force=True)

class ScriptOp:
    def __init__(s): s.chans = {}; s.numSamples = 0; s.points = []; s.polys = []
    def clear(s): s.chans = {}; s.points = []; s.polys = []
    def appendChan(s, n): c = types.SimpleNamespace(vals=None); s.chans[n] = c; return c
    primAttribs = types.SimpleNamespace(create=lambda *a: None)
    def appendPoint(s):
        p = types.SimpleNamespace(P=None); s.points.append(p); return p
    def appendPoly(s, n, closed, addPoints):
        class Poly(list): pass
        pl = Poly(types.SimpleNamespace(point=None) for _ in range(n)); s.polys.append(pl); return pl

def chop(fn):
    so = ScriptOp(); fn(so)
    return {k: list(c.vals) for k, c in so.chans.items()}

def snapshot(**pars):
    for k, v in pars.items(): setattr(owner.par, k, v)
    wires = ScriptOp(); e.CookWires(wires)
    tris = []
    for pl in wires.polys:
        tris.append({'p': [list(v.point.P) for v in pl], 'c': list(pl.Cd)})
    cardsOut = []
    for key, (cid, content, (src, idx)) in e._cards.items():
        g = cards.op('c{}'.format(cid))
        parts = {}
        for part in ('view', 'name'):
            gg = g.op('g' + part)
            if gg is None: continue
            tex = g.op(part)
            parts[part] = {'rect': [gg.par.tx.val, gg.par.ty.val, gg.par.sx.val, gg.par.sy.val],
                           'kind': tex.kind, 'text': tex.par.text.val,
                           'bg': [tex.par.bgcolorr.val, tex.par.bgcolorg.val, tex.par.bgcolorb.val],
                           'dim': g.op(part + '_mat').par.colorr.val}
        cardsOut.append({'key': key, 'src': src, 'idx': idx, 'parts': parts})
    nodes = [{'name': n['name'], 'family': n['family'], 'label': n['label'], 'level': n['level'],
              'path': n['path']} for n in e.Nodes]
    return {'inst': chop(e.CookInst), 'notes': chop(e.CookNotes), 'conn': chop(e.CookConn),
            'flags': chop(e.CookFlags), 'wires': tris, 'cards': cardsOut, 'nodes': nodes,
            'bg': list(e._cols['bg'])}

shots = {
    'front': snapshot(),
    'layers': snapshot(),
    'focus1': snapshot(Focuslevel=1),
    'reveal': snapshot(Focuslevel=0, Reveal=0.55, Explode=2.0),
}
# live: a new operator appears and grows in
owner.par.Reveal = 1.0; owner.par.Explode = 0.0; owner.par.Live = True
absTime.seconds = 10.0
nw = Op(proj, 'feedback1', 'TOP', 'feedback', 1000, 160, current=True); nl.current = False
W(nl, nw)
e.Update()
e._now = 10.33
shots['live'] = snapshot()
print('focus', e._focus, 'nodes', len(e.Nodes), 'wires', len(e.Wires))
json.dump(shots, open(sys.argv[2], 'w'))
