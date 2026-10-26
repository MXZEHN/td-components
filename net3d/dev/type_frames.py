# Camera flies up to the 'Control' annotation; captures the typewriter as it types.
import sys, types, builtins, json, math
src = open('test_type.py').read().split("# 1) UI plane")[0]
exec(src)
owner.par.Cameramode = 'follow'; owner.par.Follow = False; owner.par.Followeditor = False; owner.par.Approach = 0.5
e.Update(force=True)
pl = next(p_ for p_ in e.Panels if p_['kind'] == 'annotate')
far, near = (5.0, -0.5, 13.0), (pl['x'], pl['y'] + 0.2, 6.6)
lfar, lnear = (5.0, -0.5, 0.0), (pl['x'], pl['y'] + 0.2, 0.0)
frames = []
def look(c):
    rx, ry = math.radians(c.rx.eval()), math.radians(c.ry.eval())
    pos = [c.tx.eval(), c.ty.eval(), c.tz.eval()]
    d = (-math.sin(ry) * math.cos(rx), math.sin(rx), -math.cos(ry) * math.cos(rx))
    return pos, [p_ + v * 5 for p_, v in zip(pos, d)]
total = 300
for f in range(total + 1):
    k = min(1.0, f / 90.0); k = k * k * (3 - 2 * k)
    e._setCam(tuple(a + (b - a) * k for a, b in zip(far, near)), tuple(a + (b - a) * k for a, b in zip(lfar, lnear)))
    tick(1)
    if f in (0, 60, 100, 140, 190, 300):
        pos, lk = look(cam.par)
        st = e._typed.get(pl['key'])
        label = 'approaching' if not st or st['t0'] is None else ('typing' if '_' in (st['shown'] or '') or len(st['shown'] or '') < len(st['text']) else 'done, stays')
        frames.append({'label': '%.1fs  %s' % (f / 60, label), 'scene': snapshot(), 'pos': pos, 'look': lk})
json.dump(frames, open('dive.json', 'w'))
print([f['label'] for f in frames])
