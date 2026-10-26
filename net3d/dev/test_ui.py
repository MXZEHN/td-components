# Exercises UILayerExt against stand-ins for TD's UI: panes, monitors, mouse, keys.
import sys, types, builtins, math
src = open('export_scene.py').read().split("shots = {")[0]
src = src.replace("e = M.NetGraphExt(owner)", "e = M.NetGraphExt(owner)\nimport UILayerExt as U")
for k in ('cropTOP', 'cacheTOP', 'circleTOP', 'constantTOP', 'overTOP'):
    setattr(builtins, k, type(k, (), {}))
exec(src)
Pos = lambda x, y: types.SimpleNamespace(x=x, y=y)
# TD window 1920x1080 at screen origin; editor on the left 70%, parameters on the right
editor = types.SimpleNamespace(type='NE', id=1, owner=proj, bottomLeft=Pos(0, 0.045), topRight=Pos(0.7, 0.97),
                               x=500.0, y=-80.0, zoom=1.2)
params = types.SimpleNamespace(type='PAR', id=2, bottomLeft=Pos(0.7, 0.045), topRight=Pos(1.0, 0.97))
class Panes(list):
    current = editor
builtins.ui = types.SimpleNamespace(panes=Panes([editor, params]), windowWidth=1920, windowHeight=1080, windowX=0, windowY=0)
builtins.PaneType = types.SimpleNamespace(NETWORKEDITOR='NE', PARAMETERS='PAR')
builtins.monitors = types.SimpleNamespace(primary=types.SimpleNamespace(left=0, bottom=0, width=1920, height=1080))
mouse = {'tx': 0.0, 'ty': 0.0, 'lselect': 0, 'mselect': 0, 'rselect': 0}
mchop = types.SimpleNamespace(chan=lambda n: types.SimpleNamespace(eval=lambda: mouse[n]) if n in mouse else None)
uicards = TOp('geometryCOMP', 'ui_cards', None)
ops.update({'mouse': mchop, 'ui_cards': uicards, 'render': types.SimpleNamespace(width=1344, height=891)})
owner.ext = types.SimpleNamespace(NetGraphExt=e)
owner.par.Livepoll = 3; owner.par.Live = True; owner.par.Followeditor = True; owner.par.Recurse = 0
u = U.UILayerExt(owner); owner.ext.UILayerExt = u
def tick(n=1):
    for _ in range(n):
        absTime.frame += 1; absTime.seconds = round(absTime.seconds + 1 / 60, 6); e.Tick(); u.Tick()
def put_mouse_uv(uv):
    mouse['tx'], mouse['ty'] = uv[0] * 2 - 1, uv[1] * 2 - 1
e.Update(force=True); tick(5)
e.Frame()
print('world rect', [round(v, 3) for v in u.WorldRect()], 'world res', u.WorldRes())
# mapping round trip
w = u.NetToWindow(830, 40); back = u.WindowToNet(*w)
print('net->win->net', [round(v, 3) for v in back])
# hover a node: centre of comp1 tile in the editor
n = next(n for n in e.Nodes if n['name'] == 'comp1')
c = u.NetToWindow(n['nx'] + n['netw'] / 2, n['ny'] + n['neth'] / 2)
put_mouse_uv(c); tick(2)
proj3d = u.ProjectWorld((n['x'], n['y'], 0.0))
print('hover', u.Hover, '| cursor on output', [round(v, 3) for v in u._cursorUV()], '| comp1 tile projected', [round(v, 3) for v in proj3d])
print('elements', sorted(el['key'] for el in u.Elements))
# right click opens the context menu crop
mouse['rselect'] = 1; tick(1); mouse['rselect'] = 0; tick(40)
print('popup', u._popup and u._popup['kind'], [el['key'] for el in u.Elements if el['key'] in ('popup', 'ripple0')])
print('tiles vis while menu open', sum(1 for i in range(len(e.Nodes)) if False))
so = ScriptOp(); u.CookTiles(so); print('tiles vis (menu open)', int(sum(so.chans['vis'].vals)))
mouse['lselect'] = 1; tick(1); mouse['lselect'] = 0; tick(2)
so = ScriptOp(); u.CookTiles(so); print('after pick: popup', u._popup, 'tiles vis', int(sum(so.chans['vis'].vals)), 'of', len(e.Nodes))
u.OnKey('c', 'c', ctrl=True); u.OnKey('lshift', ''); u.OnKey('tab', '\t'); tick(2)
print('keys', [k for k, t in u._keys], 'popup', u._popup and u._popup['kind'])
k = next(el for el in u.Elements if el['key'] == 'keys'); print('keys element text:', k['text'])
so = ScriptOp(); u.CookUI(so); print('ui samples', so.numSamples, 'alpha', [round(a, 2) for a in so.chans['a'].vals][:6])
print('ui cards', len(uicards.kids), 'kinds', sorted({c.op('tex').kind for c in uicards.kids.values()}))
print('hover colour', e._cols['hover'], 'node card face', sorted(cards.op('c0').kids)[:4])
# mirror: straight-on camera must put every visible node where the editor draws it
tick(2)
errs = []
for n in e.Nodes:
    if n['path'].rsplit('/', 1)[0] != '/project1':
        continue
    ed = u.NetToWindow(n['nx'] + n['netw'] / 2, n['ny'] + n['neth'] / 2)
    pr = u.ProjectWorld((n['x'], n['y'], 0.0))
    errs.append(max(abs(ed[0] - pr[0]) * 1920, abs(ed[1] - pr[1]) * 1080))
print('mirror: max offset editor vs 3D projection, pixels:', round(max(errs), 4), 'over', len(errs), 'nodes')
