# Simulates the network editor entering and leaving components, frame by frame.
import sys, types, builtins, json, math
src = open('export_scene.py').read().split("shots = {")[0]
exec(src)
pane = types.SimpleNamespace(type='NE', id=1, owner=proj)
builtins.PaneType = types.SimpleNamespace(NETWORKEDITOR='NE')
class Panes(list):
    current = pane
builtins.ui = types.SimpleNamespace(panes=Panes([pane]))
ops['render'] = types.SimpleNamespace(width=1600, height=900)
owner.ext = types.SimpleNamespace(NetGraphExt=e)
owner.par.Cameramode = 'follow'   # this test is about dives, not the mirror camera
owner.par.Live = True; owner.par.Follow = True
def run(seconds, label, every=0.2):
    t0 = absTime.seconds
    f = absTime.frame
    f0 = f
    while absTime.seconds < t0 + seconds - 1e-9:
        f += 1; absTime.frame = f; absTime.seconds = round(absTime.seconds + 1 / 60, 6)
        e.Tick()
        if (f - f0) % 12 == 0:
            c = cam.par
            print(f"{label:7} t={absTime.seconds - t0:4.2f} cam=({c.tx.eval():6.2f},{c.ty.eval():5.2f},{c.tz.eval():6.2f}) "
                  f"rx={c.rx.eval():6.1f} ry={c.ry.eval():6.1f} focus={owner.par.Focuslevel.eval():.2f} "
                  f"alpha L0={e.LayerAlpha(0):.2f} L1={e.LayerAlpha(1):.2f} L2={e.LayerAlpha(2):.2f}")
owner.par.Recurse = 0   # deeper levels only along the edited chain
e.Update(force=True); run(0.2, 'start')
print('networks', sorted(e.Networks))
pane.owner = fx; run(1.4, 'enter')
print('networks', sorted(e.Networks))
pane.owner = gl; run(1.4, 'enter2')
pane.owner = proj; run(2.6, 'out2')
print('owner seen', e._editorOwner(), 'ownerPath', e._ownerPath, 'live', owner.par.Live.eval(), 'trans', e._trans)
