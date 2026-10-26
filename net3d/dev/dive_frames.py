# Captures scene + camera at moments of a dive into fx and back out of glow.
import sys, types, builtins, json, math
src = open('test_dive.py').read().split("owner.par.Recurse = 0")[0]
exec(src)
owner.par.Recurse = 0
def look(c):
    rx, ry = math.radians(c.rx.eval()), math.radians(c.ry.eval())
    pos = [c.tx.eval(), c.ty.eval(), c.tz.eval()]
    d = (-math.sin(ry) * math.cos(rx), math.sin(rx), -math.cos(ry) * math.cos(rx))
    return pos, [p + v * 5 for p, v in zip(pos, d)]
frames = []
def tick(n):
    for _ in range(n):
        absTime.frame += 1; absTime.seconds = round(absTime.seconds + 1 / 60, 6); e.Tick()
def grab(label):
    pos, lk = look(cam.par)
    snap = snapshot()
    frames.append({'label': label, 'scene': snap, 'pos': pos, 'look': lk})
e.Update(force=True); tick(3); grab('editor at /project1')
pane.owner = fx; tick(1)
for i, n in enumerate((17, 18, 18, 20)):
    tick(n); grab('entering fx  %.1fs' % ((absTime.seconds - e._trans['start']) if e._trans else 1.2))
pane.owner = gl; tick(80); grab('inside glow')
pane.owner = proj; tick(1)
for n in (25, 25, 25):
    tick(n); grab('back to /project1')
tick(60); grab('back at /project1')
print([f['label'] for f in frames])
json.dump(frames, open('dive.json', 'w'))
