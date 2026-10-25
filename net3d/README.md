# net3d

Rebuilds a TouchDesigner network in 3D, laid out like the network editor. Nodes keep their positions and sizes,
show their family colour, operator type and name, and TOPs with the viewer flag on show their image. Connectors and
curved wires are drawn like the editor's, and annotations appear as panels. Nested networks are stacked along X,
each in its own titled frame and linked back to its COMP.

Everything is driven by parameters, so you can animate it:

- reveal the network from its sources to its outputs
- explode it in depth
- fly a camera through it (for example with [`cam_nav`](../cam_nav/))
- watch a patch in **Live** mode while you build it: new operators grow in and the camera follows them

> **Status: untested in TouchDesigner.** This was written without a TouchDesigner session, so there is no `.tox`
> yet. The scan, layout, reveal and wire geometry were exercised against a mocked network in plain Python. The
> operator wiring and parameter names in `build_net3d.py` still need a first run in TD. The scan, hierarchy
> layout, live updates and camera follow were also exercised against that mocked network.

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
| Border | 0.04 | Family-coloured edge around each tile |
| Connector Size | 0.08 | Size of the input/output tabs |
| Wire Width / Segments | 0.035 / 32 | Wire ribbon width and smoothness |
| Network Gap | 2 | X gap between stacked networks |
| Hierarchy Links | on | Draw the dashed links between a COMP and its network |
| TOP Previews | Viewer Flag | Show TOP images on tiles: viewer flag on, all TOPs, or none |
| Label Resolution | 2 | Pixels per network unit for the tile textures |

**Animate**

| Parameter | Default | Meaning |
| --- | --- | --- |
| Reveal | 1 | 0..1. Nodes grow in by rank (longest path from a source), wires grow from output to input |
| Explode | 0 | Pushes each node back by `Explode x rank` in Z |

**Live**

| Parameter | Default | Meaning |
| --- | --- | --- |
| Live | off | Poll the network while you build it and update in place |
| Poll Every N Frames | 3 | How often Live checks for changes |
| Birth Time | 0.6 | Seconds a new operator takes to grow in; its wires grow with it |
| Camera Follows | on | The internal `cam` flies to the newest operator, or the one you last moved |
| Follow Offset | 0.6, -0.4, 3 | Camera position relative to that operator; it keeps looking at the operator |
| Follow Smooth | 0.5 | Camera smoothing time in seconds |

In Live mode, a change only touches the tiles of operators that were added, removed or restyled. Moving an operator
just moves its tile. `op('net3d').Focus('/project1/noise1')` sends the camera to a specific operator. Camera
follow drives the internal `cam` only, so leave the Render page's Camera empty to use it.

**Render**: `Camera` (empty uses the internal `cam`), `Frame All` (points `cam` at the whole network), `Resolution`.

Colours live in the `colors` table (`bg`, one row per family, `tile`, `text`, `type`, `bypass`, `annotate`,
`frame`, `hier`). They are
approximations of the editor theme; calibrate them against a screenshot of your editor.

## How it works

| Operator | Role |
| --- | --- |
| `NetGraphExt` | Extension: scans the network, ranks nodes, computes the animated layout and cooks the script ops |
| `nodes` | Table of the last scan (path, family, rank, position, size), useful for your own animation |
| `inst` / `conn` / `notes` | Script CHOPs: per-node slab, connector and panel (frame, annotation) transforms and colours |
| `geo_slabs`, `geo_conn` | Instanced boxes from `inst` and `conn` |
| `wires` -> `geo_wires` | Script SOP of bezier ribbons coloured by the source node's family, plus dashed hierarchy links |
| `cards` | One Geometry COMP per node and panel with Text TOP faces (type and name, or name over the node's image); transforms follow `inst` / `notes` |
| `render` -> `out1` | Flat, unlit render on the editor background colour |

Inputs sit on the left edge, outputs on the right, COMP connectors on the top and bottom, spaced like the editor.
The operator type (`noiseTOP` -> `Noise`) is drawn where the editor draws its icon.

### Hierarchy

The target network keeps its own editor coordinates, so editing it live doesn't shift what is already there.
With Recurse Depth above 0, each nested network, depth first, takes the next slot to the right. Each one is
vertically centred on its COMP node and drawn inside a frame titled with its path. Dashed links connect the
hierarchy:

- COMP node -> its frame
- COMP input *i* -> the In OP behind it
- Out OP -> COMP output *i*

Reveal treats a nested network as coming after its COMP, so it grows in after it.

## Known gaps

- No grid or flag buttons (bypass/lock/display/render) yet; bypassed nodes are greyed. The type is text, not the
  editor's icon glyph.
- A nested network's slot moves when an earlier network grows, so in Live mode with recursion, frames to the
  right can shift.
- Wires that leave the scanned networks (to a COMP outside the target) are not drawn.
- Each node is a few operators (`cards`), so rebuilding very large networks (hundreds of nodes) is slow.
