# net3d dev tools

Offline checks for net3d **without TouchDesigner**. These run the real `../scripts/NetGraphExt.py` and
`../scripts/UILayerExt.py` against stand-ins for TD's objects (operators, panes, mouse, camera), then render what
the component would produce with three.js.

**These are not TouchDesigner renders.** Layout, colours, wires, opacity, camera paths, dives and typewriter
timing come from the component's code. Viewer images are drawn stand-ins. Once net3d runs in TD, compare there.

| File | What it does |
| --- | --- |
| `export_scene.py` | Sample network (nested `fx` / `fx/glow`, flags, annotation, references) + mocks; dumps the CHOP/SOP/card data for several states to `scene.json` |
| `test_dive.py` | Simulates the network editor entering `fx`, `glow` and jumping back; prints camera and layer opacity per frame |
| `test_ui.py` | UI layer: screen <-> network mapping, hover, cursor projected onto the 3D tile, right-click popup, keys, mirror camera alignment |
| `test_type.py` | UI plane pixel exactness at any UI Depth; typewriter annotations on approach |
| `index.html` | three.js renderer of the exported data |
| `shoot.js`, `shoot_dive.js`, `shoot_type.js`, `dive_frames.py`, `type_frames.py` | Still images and filmstrips |
| `run_all.sh` | All of the above |

```bash
./run_all.sh
```

Needs Python 3, Node, and Playwright with Chromium available as `require('playwright')`. `three@0.160.0` is
installed into `node_modules` on first run.
