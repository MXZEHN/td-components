# net3d

Rebuilds a TouchDesigner network in 3D, laid out like the network editor. Each node is built like an editor tile
and keeps its position and size:

- a live viewer showing what the operator shows in the editor: the TOP's image, the CHOP's channels, the SOP's
  geometry, the DAT's text
- a name strip along the bottom
- a family-coloured border, with the current and selected operators highlighted
- its lit flags: bypass, lock, display, render, viewer active Connectors and
curved wires are drawn like the editor's, and annotations appear as panels. Nested networks are stacked in depth:
each sits behind its COMP node in its own titled frame, linked back to the COMP.

Everything is driven by parameters, so you can animate it:

- reveal the network from its sources to its outputs
- explode it in depth
- fly a camera through it (for example with [`cam_nav`](../cam_nav/))
- watch a patch in **Live** mode while you build it: new operators grow in and the camera follows them

All operators of one component sit at the same depth. Only the contents of another component sit at another
depth.

**Built for recording tutorials.** By default, net3d re-uses TouchDesigner's own pixels:

- Node tiles are cropped from a screen grab of the network editor.
- The panes, timeline, menus and popups are crops of the same grab, on a 2D UI layer on top.
- The 3D camera mirrors the editor's view pixel for pixel.

So straight on, the output looks like TD, and it turns 3D when you dive into components, explode the hierarchy
or move the camera. Mouse, clicks and keys are shown on the UI layer. See [UI_LAYER.md](UI_LAYER.md) for the
design and calibration.

> **Status: untested in TouchDesigner.** This was written without a TouchDesigner session, so there is no `.tox`
> yet. The scan, layout, reveal and wire geometry were exercised against a mocked network in plain Python. The
> operator wiring and parameter names in `build_net3d.py` still need a first run in TD. The scan, hierarchy
> layout, live updates, camera follow and tile building were also exercised against that mocked network. The OP
> Viewer TOP parameter (`opviewer`) and the Fit TOP mode (`best`) are from memory, not checked against TD.

## Build

1. In TouchDesigner, open the Textport (Alt+T) and run:

   ```python
   exec(open('C:/path/to/td-components/net3d/build_net3d.py').read())
   build(op('/project1'), 'C:/path/to/td-components/net3d/scripts')
   ```

   This creates `/project1/net3d` with the scripts copied into its DATs.
2. Check `net3d/render`, then save it: `op('/project1/net3d').save('net3d.tox')`.

## Parameters

**Net3D**

| Parameter | Default | Meaning |
| --- | --- | --- |
| Target | empty | COMP whose network is rebuilt; empty means the network `net3d` sits in |
| Rebuild | pulse | Rescan the network |
| Auto Rebuild | on | Check for changes every 30 frames when Live is off |
| Recurse Depth | 0 | Also rebuild networks inside COMPs, this many levels deep (see Hierarchy) |
| Scale | 0.01 | World units per network-editor unit (a default node is about 1.3 x 0.9) |
| Node Depth | 0.12 | Thickness of the node slabs |
| Wire Width / Segments | 0.035 / 32 | Wire ribbon width and smoothness |
| Layer Spacing | 8 | Z distance from a COMP node back to its network. Inside a component the camera stays within this gap, so larger values show more of the network |
| Hierarchy Wires | on | Wires through the hierarchy: COMP input -> In OP, Out OP -> COMP output |
| Reference Wires | on | Wires for operator references (a Select TOP's TOP, a Geometry COMP's material, ...), on any level |
| Frame Guides | off | Thin dashed lines from a COMP tile's corners to its network's frame |
| Tile Source | Captured from Editor | Real tiles cropped from the screen grab (drawn tile until a node has been on screen once), or Drawn |
| TOP Previews | All Operators | What fills each tile's viewer area: live viewers for all operators, TOPs only, only operators with Viewer Active on, or none (operator type labels) |
| Viewer Resolution | 2 | Pixels per network unit for the live viewers |
| Label Resolution | 3 | Pixels per network unit for the name strips |
| Highlight Current | on | Border colour marks the current (`current`) and selected (`selected`) operators |

**Animate**

| Parameter | Default | Meaning |
| --- | --- | --- |
| Reveal | 1 | 0..1. Nodes grow in by rank (longest path from a source), wires grow from output to input |
| Explode | 0 | Pushes the hierarchy levels further apart: `Explode x level` extra in Z |
| Layer Opacity | 0.35 | Opacity per level *behind* Focus Level (`0.35^distance`) |
| Annotations | Type On First Approach | Annotations type out their title and body, typewriter style, the first time the camera comes close (then stay), or are always shown in full |
| Type Speed | 30 | Characters per second; punctuation and line breaks pause a little longer |
| Approach | 0.2 | How close counts as an approach: the annotation's centre is in view and it is at least this fraction of the frame high |
| Retype Annotations | pulse | Forget which annotations have been typed |
| Front Opacity | 0.08 | Opacity per level *in front of* Focus Level, i.e. the parents when you are inside a component |
| Focus Level | 0 | Hierarchy level drawn solid. Live mode animates it while diving; you can also animate it yourself |

**Live**

| Parameter | Default | Meaning |
| --- | --- | --- |
| Live | off | Poll the network while you build it and update in place |
| Poll Every N Frames | 3 | How often Live checks for changes |
| Birth Time | 0.6 | Seconds a new operator takes to grow in; its wires grow with it |
| Camera Follows | on | The internal `cam` flies to the newest operator, or the one you last moved |
| Follow Offset | 0.6, -0.4, 3 | Camera position relative to that operator; it keeps looking at the operator |
| Follow Smooth | 0.5 | Camera smoothing time in seconds |
| Follow Editor | on | Dive into or out of components when the network editor enters or leaves them |
| Dive Time | 1.2 | Seconds per dive; a jump across several levels adds half a Dive Time per extra level |

In Live mode, a change only touches the tiles of operators that were added, removed or restyled. Moving an operator
just moves its tile. `op('net3d').Focus('/project1/noise1')` sends the camera to a specific operator. Camera
follow drives the internal `cam` only, so leave the Render page's Camera empty to use it.

### Diving in and out of components

With Live and Follow Editor on, net3d watches which component the network editor shows (the current pane if
it's a network editor, otherwise the first one). When that changes, the camera animates there.

- **Entering a component:** the camera dollies straight into the COMP's tile. The tile fills the view at the
  moment you "go in". The camera then carries on through it and settles inside the component: behind the parent
  layer, framing the component's network. Focus Level moves from the parent's level to the child's at the same
  time, so the parent fades to Front Opacity and the child becomes solid.
- **Leaving a component:** the reverse. The camera pulls back out through the COMP's tile and the parent comes
  back.
- **Jumping across the tree** (path bar, a sibling, several levels at once): the camera goes up to the common
  parent and back down, one hop per level, through each COMP's tile on the way.
- **Below Recurse Depth:** the network you're editing is always built, even deeper than Recurse Depth. Only the
  chain of components leading to it is added, not their siblings. The chain you're leaving stays built until the
  camera is out of it.
- **After arriving:** the camera follows new operators again (Camera Follows).

Call `op('net3d').Dive('/project1/fx')` to run the same move from a script, for a scripted fly-through.
`Dive(path, duration)` overrides Dive Time. Frame All frames the component you're in.

**UI Layer** (see [UI_LAYER.md](UI_LAYER.md))

| Parameter | Default | Meaning |
| --- | --- | --- |
| UI Layer | on | 2D layer on top: TD chrome, popups, cursor, clicks, keys |
| TD Chrome | Around the Editor | Panes and regions around the 3D network like TD, fading in when used, or off |
| Hold / Fade Time | 2.5 / 0.25 | Seconds an element stays after its last signal / fade duration |
| Cursor, Click Ripples, Keys, Mouse Buttons | on | Overlays |
| Calibration Overlay | off | Predicted tile rectangles over the grab, for calibrating |
| Cursor Size, Path Bar Height | 7, 28 | Pixels |
| UI Translate / Rotate / Scale | 0 / 0 / 1 | Moves the UI layer's plane in 3D; at the defaults it fills the frame exactly |
| UI Depth | 0.03 | Z gap between the UI's sublayers (chrome, popups, overlays, calibration); they separate with parallax when the plane turns |
| Mouse Offset / Scale, Network Offset / Zoom Scale | 0 / 1 | Calibration of the screen <-> network mapping |

Tables: `regions` (timeline, menu bar, ... in window UV) and `popups` (menu sizes in pixels).

**Render**

| Parameter | Default | Meaning |
| --- | --- | --- |
| Camera Mode | Mirror Editor View | Line the edited network up with the editor pixel for pixel, or follow new operators |
| Camera | empty | Your own camera instead of the internal `cam` |
| Frame All | pulse | Frame the current component |
| Resolution | 1920 x 1080 | Output size when the UI layer is off (with it on, the output is the TD window's size) |

### Matching the editor

The tile look is driven by two tables. Change them, then pulse **Rebuild**.

- `colors`: `bg`, one row per family (border and wires), `strip` (name strip), `tile` (viewer area without a
  viewer), `text`, `type`, `bypass`, `current`, `selected`, `flag_*`, `annotate`, `frame`, `hier`.
- `tile`, in network-editor units: `border`, `namestrip` (name strip height), `namesize`, `typesize`, `titlesize`,
  `flagw`, `flagh`, `conn` (connector tab size).

The defaults are from memory of the editor, not measured. To calibrate:

1. Set the network editor to 100% zoom so 1 pixel = 1 network unit.
2. Take a screenshot of a few nodes of each family with flags on.
3. Read the sizes and colours off the screenshot into the tables.
4. Compare `out1` side by side with the screenshot.

Operators that get a custom colour in the editor use it for their name strip.

## How it works

| Operator | Role |
| --- | --- |
| `NetGraphExt` | Extension: scans the network, ranks nodes, computes the animated layout and cooks the script ops |
| `nodes` | Table of the last scan (path, family, rank, position, size), useful for your own animation |
| `inst` / `conn` / `notes` | Script CHOPs: per-node slab, connector and panel (frame, annotation) transforms, colours and opacity (`a` slab, `ca` card) |
| `geo_slabs`, `geo_conn` | Instanced boxes from `inst` and `conn` |
| `wires` -> `geo_wires` | Script SOP of bezier ribbons coloured by the source node's family, plus dashed hierarchy links |
| `flags` -> `geo_flags` | Script CHOP of lit flags, instanced as tabs |
| `cards` | One Geometry COMP per node (live viewer quad + name strip quad) and per panel; transforms follow `inst` / `notes` |
| `colors`, `tile` | Look of the tiles, see Matching the editor |
| `render` | Flat, unlit 3D render; with the UI layer it covers the network editor's rectangle |
| `UILayerExt` | Extension: sensors (mouse, keys, panes, editor view, parameters, time), screen <-> network mapping, UI elements |
| `grab`, `mouse`, `keys` | Screen Grab TOP of the TD window, Mouse In CHOP, Keyboard In DAT (-> `keys_cb`) |
| `ui` -> `ui_cards` -> `render_ui` | Script CHOP of UI element placement and opacity, one card per element, orthographic render |
| `tiles` | Script CHOP: each node's tile rectangle in the grab, visible now / seen before |
| `world_place`, `over_ui` -> `out1` | 3D render placed in the window, UI layer on top |

Inputs sit on the left edge, outputs on the right, COMP connectors on the top and bottom, spaced like the editor.

Each card in `cards` is a Geometry COMP holding two quads. The viewer quad uses a Select TOP and a Fit TOP for TOPs,
so the image keeps its aspect ratio. For every other family it uses an OP Viewer TOP, which renders the operator's
own viewer live. Tiles without a viewer show the operator type (`noiseTOP` -> `Noise`) where the editor draws its
icon. The name strip is a Text TOP. Flags are instanced tabs on the tile edges:

- left: bypass and lock
- right: display and render
- bottom right: viewer active

Bypassed tiles are dimmed.

### Hierarchy

The target network keeps its own editor coordinates at z = 0, so editing it live doesn't shift what is already
there. With Recurse Depth above 0, each nested network sits Layer Spacing further back than its COMP node,
centred behind it and drawn inside a frame titled with its path. Two levels down is 2 x Layer Spacing back, and
so on. Every operator of a component shares that one depth. Connections between levels are drawn as the same
bezier wires as inside a network, coloured by the source's family, easing from one depth to the other:

- COMP input *i* -> the In OP behind it (leaves the COMP's input to the left, enters the In OP from the left)
- Out OP -> COMP output *i* (leaves the Out OP to the right, enters the COMP's output from the right)
- operator references: a parameter that points at another scanned operator (Select OPs, materials, ...) gets a
  wire from the referenced operator to the one referencing it

Frame Guides adds thin dashed lines from a COMP tile's corners to its network's frame.

Reveal treats a nested network as coming after its COMP, so it grows in after it.

Deeper layers are semi-transparent: each level away from **Focus Level** multiplies its opacity by **Layer
Opacity**. A tile's slab fades faster than its viewer (opacity squared), so a faded tile still reads as its
image. Frames (0.5) and annotations (0.6) are always see-through, so they never hide nodes that Explode pushes
behind them. The top network has no frame. Blending is on for all MATs, and the Render TOP's order-independent
transparency is switched on when the build exposes it.

## Known gaps

- No grid. The operator type is text, not the editor's icon glyph. Flags are drawn only when lit.
- A live viewer for every operator costs one OP Viewer TOP each. On big networks use TOPs Only, or lower the
  Viewer Resolution.
- COMPs show their panel through the OP Viewer TOP, which is empty for a Base COMP.
- Sibling COMPs that sit close together have networks that overlap in X/Y on the same layer. Spread the COMPs
  apart in the editor, or increase Explode.
- Seen straight on from the front, the deeper layers are hidden behind the top network. Orbit the camera or use
  Explode to see them.
- Reference wires come from OP-type parameters only. A reference written into an expression (`op('foo')` in a
  parameter) isn't found. Every operator's parameters are read on every scan, so in Live mode with big networks,
  turn Reference Wires off or raise Poll Every N Frames.
- Wires that leave the scanned networks (to a COMP outside the target) are not drawn.
- Each node is a few operators (`cards`), so rebuilding very large networks (hundreds of nodes) is slow.
