# net3d: handoff to a desktop session

net3d was designed and written in a cloud session **without TouchDesigner**. Everything that doesn't touch TD
was tested against mocks (`dev/`). **Nothing has run inside TouchDesigner yet.** This file is the plan for the
first session on a machine with TD and the TD MCP server (`tdmcp`).

Branch: `ccr-a3c631ab-y6pch6`.

## Goal (from the user)

A TD component that rebuilds any TD network in 3D, looking as close as possible to TD's own UI, so complete
tutorials can be recorded as 3D visualisations: live while editing, with dives into components, annotations
typing on, and a UI layer (TD's panes, menus, popups, mouse, clicks, keys) on top. Read
[README.md](README.md) for the component and [UI_LAYER.md](UI_LAYER.md) for the UI layer design.

## Status (2026-10-26, TD 2025.33230, TDMCP 1.1.49)

- Steps 1 to 3 done. Dev patch: `net3d/net3d_dev.toe` (git-ignored), made from a patch holding only TDMCP.
- `build()` runs with zero operator errors and zero script errors (check `scriptErrors(recurse=True)` too: `errors()` does not include them).
- Fixed from step 3: Render TOP `bgcolora` (no `bgalpha`), `transparency` = `orderind`, `antialias` = `aa16`;
  Fit TOP `fit` = `fitbest`; Mouse In CHOP button channels must be named (`lbuttonname` etc.); Keyboard In DAT
  calls `onKey(dat, keyInfo)`; Screen Grab TOP `source` set to the display holding the TD window; grab crops
  inside cards go through a Select TOP (wires can't cross COMPs).
- Confirmed as written: `opviewerTOP`/`opviewer`, crop/cache/transform/text/circle parameter names,
  `instancer/g/b/a`, Camera `viewanglemethod` = `horzfov`, `ui.panes` attributes (`bottomLeft`/`topRight` are
  `Coords` with pixels and UV), `ui.windowX/Y/Width/Height`, `monitors`, `currentChild`, `Par.isOP`, annotate
  `Titletext`/`Bodytext`/`Backcolorr`.
- Step 4 partly done (1920x1080 maximised window, three monitors):
  - Network mapping matches the real tiles to about 1 px at two zoom levels, with Network Offset 0 and Zoom
    Scale 1. Two structural fixes did it: **Window Inset** (pane coordinates start 8 px inside the window, the
    Windows frame) and `ViewRect()` (the view centre is the editor pane minus the 23 px path bar).
  - Mouse In CHOP: `output` must be `normal` (the default `aspect` scales y by the width). Then -1..1 covers the
    primary monitor and the window UV matches to 1 px. It only updates while TD has focus.
  - Screen Grab numbers displays in `monitors` order, not by Windows name (`DISPLAY1` was Display 2 here).
  - `regions` table measured: timeline and menu bar + toolbar.
  - UI cards had no material (`./mat`, the MAT is inside the COMP); chrome now shows TD's pixels.
  - Captured tile faces only record while the editor shows that network (`_editorOwner()`).
  - Colours: `build()` fills `colors` from the user's `ui.colors` (family colours at 0.85 of the table value,
    as the editor draws them); the rest measured from the screen. TD 2025's default `op.color` is 0.67, not 0.55.
  - Live with the user: hover, left/middle/right buttons, right-click context popup, Tab create popup,
    middle-click info popup, Keyboard In DAT (Tab, Esc) all work. `popups` measured: context 246 x 609,
    create 784 x 633 (centred on the cursor), info 307 x 233. When polling from outside, keep the result
    string short: TDMCP truncates `execute_code` results at about 200 characters.
- Step 5 (in progress):
  - Mirror camera: the 3D tiles sit within 2.5 px of the editor's tiles. Live add, move, rewire, delete: all
    picked up within a second, new nodes grow in, no errors.
  - Examine viewport built in: `examine_cam` (TD's palette `cameraViewport`, loaded from `app.samplesFolder`),
    `render_examine`, `examine` panel; pulses Open Examine Viewer and Home Examine Camera. The main camera stays
    untouched. cameraViewport homes on the constant value of the Render TOP's geometry parameter, so that is a
    string, not an expression.
  - Tile faces are snapshots now (user's decision): live capture recorded other windows covering TD. Capture
    Tile Faces locks each visible tile's crop as a texture and only runs while TD is the foreground window.
    Snapshots live in `net3d/snapshots` (one locked Crop TOP per operator path), not in the cards, so they
    survive card rebuilds, extension restarts (file open) and `build()`. Verified with a real capture: 12 clean
    tiles.
  - Examine panel: all three mouse buttons and the wheel on (cameraViewport needs them; rule for every
    cameraViewport panel). Examine camera near plane 0.5.
  - Z-fighting in the examiner fixed: card 6 mm over the slab, snapshot 4 mm over the drawn parts
    (`CARD_LIFT`, `FACE_LIFT`); drawn parts hidden under a snapshot, empty faces not rendered.
  - Still to test: dives, annotations, UI layer (ripples, keys, UI Rotate), performance, and a real Capture Tile
    Faces run with TD in front.
- Still open:
  - Drawn tiles use a simpler model than TD 2025 (family border all round vs. TD's family column with flag
    icons and a grey frame; live viewers vs. type labels; current operator filled vs. outlined; COMPs flat grey).
  - Then step 5.

## Step 1: set up TouchDesigner (the original first task)

1. Ask the user for the path of their existing patch that contains the **tdmcp** component. Don't guess.
2. Start TouchDesigner with that patch, with the TD MCP server running.
3. In that patch, delete everything except the tdmcp component, and **save it under a new name** (e.g.
   `net3d_dev.toe` next to this repo). Never overwrite the original. `.toe` files are git-ignored here.
4. Confirm the MCP connection works (e.g. list `/project1` children).

## Step 2: build net3d inside TD

Run through the MCP python tool (or the Textport):

```python
exec(open(r'<repo>/net3d/build_net3d.py').read())
build(op('/project1'), r'<repo>/net3d/scripts')
```

Expect errors on the first run: parameter and operator names below were written from memory. Fix each in the
scripts (not only in TD), re-run `build()`, and repeat until it builds without errors. Check the Textport and each
operator's error/warning state.

## Step 3: verify the API assumptions (most likely to be wrong first)

| Assumption | Where | How to check |
| --- | --- | --- |
| OP Viewer TOP class `opviewerTOP`, parameter `opviewer` | `NetGraphExt._makeCard` | Create one by hand |
| Fit TOP parameter `fit` with value `best` | `_makeCard` | Parameter menu names |
| Geometry COMP instance colour/alpha parameters `instancer/g/b/a` (or `instancecolorr...`) | `build_net3d._instancedGeo` | Instance 2 page names |
| MAT `blending`, Render TOP order-independent transparency (`orderindtrans` / `transparency`) | build, `_makeCard` | Parameter names |
| Camera `fov` is horizontal unless `viewanglemethod` says vertical | `NetGraphExt.TanHalfV` | Camera View page |
| `ui.panes`, `PaneType.NETWORKEDITOR`, `PaneType.PARAMETERS`, `pane.owner`, `pane.id`, `pane.x/.y/.zoom`, `pane.bottomLeft/.topRight` (UV or pixels) | `UILayerExt`, `NetGraphExt._editorOwner` | Print them in the Textport while panning/zooming |
| `ui.windowX/Y/Width/Height`, `monitors.primary` | `UILayerExt.WindowSize`, `_readMouse` | Textport |
| Mouse In CHOP channels `tx ty lselect mselect rselect`, range -1..1 over the screen | `_readMouse` | Watch the CHOP |
| Keyboard In DAT callback signature `onKey(dat, key, character, alt, lAlt, rAlt, ctrl, lCtrl, rCtrl, shift, lShift, rShift, state, time, ...)` | `scripts/keys_cb.py` | Default callbacks DAT of a new Keyboard In DAT |
| Screen Grab TOP class `screengrabTOP` and how to grab just the TD window | `build_net3d._buildUILayer` | Create one; licence availability |
| Crop TOP `cropleft/right/bottom/top` in 0..1; Cache TOP `active`, `cachesize` | `_makeCard`, `UILayerExt._style` | Parameter names |
| Transform TOP `tx ty sx sy`, `tunit` fraction, `extend` zero | `_buildUILayer` (`world_place`) | Parameter names |
| Annotate COMP parameters `Titletext`, `Bodytext`, `Backcolorr/g/b` | `NetGraphExt._scanNetwork` | Parameters of an annotation |
| `OP.errors()`, `OP.warnings()`, `COMP.currentChild`, `op('/').time.frame/.play`, `Par.isOP` | scan, `UILayerExt` | Textport |

## Step 4: calibrate and match the look

1. UI Layer page → **Calibration Overlay** on. Adjust Network Offset / Zoom Scale until the pink rectangles sit
   on the real tiles. Then Mouse Offset / Scale until hover and the cursor dot match. Details in UI_LAYER.md.
2. Fill the `regions` table (timeline, menu bar) and the `popups` table (menu sizes) from a screenshot.
3. With Tile Source = Drawn, compare against a screenshot at 100% zoom and set the `tile` and `colors` tables
   (the defaults are guesses). Wires are always drawn: match their colour and curve.

## Step 5: test the features in TD

- Camera Mode Mirror: straight on, the 3D network lines up with the editor.
- Live: add, move, delete and rewire operators; new ones grow in.
- Enter and leave components (editor `i`/`u`, path bar): dives, layer fades, deep components below Recurse
  Depth.
- Annotations type on the first approach.
- UI layer: chrome, right-click menu, Tab menu, middle-click info, cursor, ripples, keys; UI Rotate for the 3D
  plane.
- Performance on a big network: live viewers, reference wires, poll interval.

## Step 6: export like cam_nav

Save `net3d.tox` (scripts synced to `scripts/`) and `net3d_standalone.tox` (scripts embedded), as described in
`../cam_nav/README.md`. Update README.md: remove "untested", state the TD build it was tested on, and list
anything that turned out different.

## Working conventions

- Edit the files in `scripts/` and re-run `build()`; the built DATs hold copies of the scripts.
- After any change to `scripts/`, run `dev/run_all.sh` (mock tests + offline previews) before committing.
- Preview images from `dev/` are mockups, never present them as TD renders.
- Don't commit `.toe` files or anything from the user's original patch.
