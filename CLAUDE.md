# td-components

Reusable TouchDesigner components, one folder each (`README.md`, exported `.tox`, `scripts/`). See README.md.

## Current work: net3d

`net3d/` rebuilds a TD network in 3D for recording tutorials. It was written without TouchDesigner and **has not
run in TD yet**. When asked to continue, follow [net3d/HANDOFF.md](net3d/HANDOFF.md) step by step, starting
with step 1 (asking the user for the tdmcp patch path).

- `net3d/scripts/NetGraphExt.py`: the 3D network (scan, layout, wires, cards, live updates, dives, typewriter
  annotations).
- `net3d/scripts/UILayerExt.py`: the UI layer (screen grab crops, mouse/keys, popups, mirror camera, UI plane).
- `net3d/build_net3d.py`: builds the component inside TD (`build(op('/project1'), '<repo>/net3d/scripts')`).
- `net3d/dev/run_all.sh`: mock tests and offline previews. Run after every script change.

## Conventions

- Match the style of the existing code: short docstrings, sparse comments, `_setpar` for parameter names that
  may differ between builds.
- READMEs: tables for parameters, plain sentences, no marketing.
- Never present `net3d/dev` renders as TouchDesigner output.
- Never commit `.toe` files (git-ignored) or the user's original patches.
