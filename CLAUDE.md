# td-components

Reusable TouchDesigner components, one folder each (`README.md`, exported `.tox`, `scripts/`). See README.md.

## Current work: net3d

`net3d/` rebuilds a TD network in 3D for recording tutorials. It runs in TouchDesigner 2025.33230; steps 1 to 6
of [net3d/HANDOFF.md](net3d/HANDOFF.md) are done, and its status section lists what was verified and what is still
open. Exported as `net3d.tox` (scripts synced) and `net3d_standalone.tox`.

- When driving TD through TDMCP: save the .toe after every step; check that the timeline plays before relying on
  delayed `run()` calls; `execute_code` results are cut at about 200 characters, so write longer output to a file.

- `net3d/scripts/NetGraphExt.py`: the 3D network (scan, layout, wires, cards, live updates, dives, typewriter
  annotations).
- `net3d/scripts/UILayerExt.py`: the UI layer (screen grab crops, mouse/keys, popups, mirror camera, UI plane).
- `net3d/build_net3d.py`: builds the component inside TD (`build(op('/project1'), '<repo>/net3d/scripts')`).
- `net3d/dev/run_all.sh`: mock tests and offline previews. Run after every script change.
- `net3d/tools/capture_tile_library.py`, `net3d/assets/tiles`: the tile library (one template per family).
- `net3d/demo/build_demo.py`: the step-by-step demo animation (renders to `net3d/renders/`, git-ignored).

## Conventions

- Match the style of the existing code: short docstrings, sparse comments, `_setpar` for parameter names that
  may differ between builds.
- READMEs: tables for parameters, plain sentences, no marketing.
- Never present `net3d/dev` renders as TouchDesigner output.
- Never commit `.toe` files (git-ignored) or the user's original patches.
