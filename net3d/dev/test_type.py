# UI plane exactness and annotation typewriter, against the same stand-ins.
import sys, types, builtins, math
src = open('test_ui.py').read().split("e.Update(force=True); tick(5)")[0]
exec(src)
ops['cam_ui'] = types.SimpleNamespace(par=Par(fov=45))
# 1) UI plane: pinhole projection of each element through cam_ui == its window rect
D = u.UICamDistance(); w, h = 1920, 1080; aspect = w / h
tv = math.tan(math.radians(45) / 2) / aspect
u.Elements = [{'key': 'a', 'rect': (0.1, 0.2, 0.4, 0.5), 'alpha': 1, 'layer': 0},
              {'key': 'b', 'rect': (0.6, 0.7, 0.9, 0.95), 'alpha': 1, 'layer': 3}]
owner.par.Uidepth = 0.2
so = ScriptOp(); u.CookUI(so); c = {k: v.vals for k, v in so.chans.items()}
for i, el in enumerate(u.Elements):
    z = c['tz'][i]
    def proj(x, y):   # camera at (0, 0, D) looking down -Z
        d = D - z
        return (x / (d * tv * aspect) * 0.5 + 0.5, y / (d * tv) * 0.5 + 0.5)
    a = proj(c['tx'][i] - c['sx'][i] / 2, c['ty'][i] - c['sy'][i] / 2)
    b = proj(c['tx'][i] + c['sx'][i] / 2, c['ty'][i] + c['sy'][i] / 2)
    err = max(abs(a[0] - el['rect'][0]) * w, abs(a[1] - el['rect'][1]) * h, abs(b[0] - el['rect'][2]) * w, abs(b[1] - el['rect'][3]) * h)
    print(f"UI plane element {el['key']} at z={z:.2f}: max error {err:.6f} px")
# 2) typewriter
owner.par.Cameramode = 'follow'; owner.par.Follow = False; owner.par.Followeditor = False
e.Update(force=True)
pl = next(p_ for p_ in e.Panels if p_['kind'] == 'annotate')
e._setCam((pl['x'], pl['y'], 60.0), (pl['x'], pl['y'], 0.0)); tick(3)
def show(label):
    st = e._typed.get(pl['key'])
    print(f"{label:28} triggered={st['t0'] is not None!s:5} shown={st['shown']!r}")
e._setCam((pl['x'], pl['y'], 60.0), (pl['x'], pl['y'], 0.0)); tick(30); show('far away (60 units)')
e._setCam((pl['x'] + 1, pl['y'] + 0.5, 6.0), (pl['x'], pl['y'], 0.0)); tick(1); show('approached')
tick(20); show('+0.33 s')
tick(60); show('+1.33 s')
tick(240); show('+5.3 s (done)')
e._setCam((pl['x'], pl['y'], 60.0), (pl['x'], pl['y'], 0.0)); tick(30)
e._setCam((pl['x'] + 1, pl['y'] + 0.5, 6.0), (pl['x'], pl['y'], 0.0)); tick(2); show('second approach')
note.par.Bodytext = P(note.par.Bodytext.eval() + ' Edited live.'); e.Update(); tick(20); show('text appended while editing')
