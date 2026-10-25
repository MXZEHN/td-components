# net3d

Rebuilds a TouchDesigner network in 3D, laid out like the network editor: same node positions and sizes, family
colours, connectors, curved wires and annotations, and the image of TOPs with their viewer flag on. Everything
is driven by parameters, so you can animate it: reveal the network from its sources to its outputs, explode it in
depth, or fly a camera through it (for example with [`cam_nav`](../cam_nav/)).

> **Status: untested in TouchDesigner.** This was written without a TouchDesigner session, so there is no `.tox`
> yet. The scan, layout, reveal and wire geometry were exercised against a mocked network in plain Python. The
> operator wiring and parameter names in `build_net3d.py` still need a first run in TD.

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
| Auto Rebuild | on | Rescan every 30 frames when nodes move, appear, rewire or change flags |
| Recurse Depth | 0 | Also rebuild networks inside COMPs, one Layer Spacing behind their COMP node per level |
| Scale | 0.01 | World units per network-editor unit (a default node is about 1.3 x 0.9) |
| Node Depth | 0.12 | Thickness of the node slabs |
| Border | 0.04 | Family-coloured edge around each tile |
| Connector Size | 0.08 | Size of the input/output tabs |
| Wire Width / Segments | 0.035 / 32 | Wire ribbon width and smoothness |
| Layer Spacing | 6 | Z distance between nested network levels |
| TOP Previews | Viewer Flag | Show TOP images on tiles: viewer flag on, all TOPs, or none |
| Label Resolution | 2 | Pixels per network unit for the tile textures |

**Animate**

| Parameter | Default | Meaning |
| --- | --- | --- |
| Reveal | 1 | 0..1. Nodes grow in by rank (longest path from a source), wires grow from output to input |
| Explode | 0 | Pushes each node back by `Explode x rank` in Z |

**Render**: `Camera` (empty uses the internal `cam`), `Frame All` (points `cam` at the whole network), `Resolution`.

Colours live in the `colors` table (`bg`, one row per family, `tile`, `text`, `bypass`, `annotate`). They are
approximations of the editor theme; calibrate them against a screenshot of your editor.

## How it works

| Operator | Role |
| --- | --- |
| `NetGraphExt` | Extension: scans the network, ranks nodes, computes the animated layout and cooks the script ops |
| `nodes` | Table of the last scan (path, family, rank, position, size), useful for your own animation |
| `inst` / `conn` / `notes` | Script CHOPs: per-node slab, connector and annotation transforms and colours |
| `geo_slabs`, `geo_conn` | Instanced boxes from `inst` and `conn` |
| `wires` -> `geo_wires` | Script SOP of bezier ribbons, coloured by the source node's family |
| `cards` | One Geometry COMP per node and annotation with a Text TOP face (over the node's image for previews); its transform follows `inst` |
| `render` -> `out1` | Flat, unlit render on the editor background colour |

Network-editor coordinates map straight to world X/Y, centred on the network. Inputs sit on the left edge, outputs
on the right, COMP connectors on the top and bottom, spaced like the editor.

## Known gaps

- No grid, flag buttons (bypass/lock/display/render), or operator-type icons yet; bypassed nodes are greyed.
- Wires leaving the scanned network (to a parent or sibling COMP) are not drawn.
- Each node is a few operators (`cards`), so rebuilding very large networks (hundreds of nodes) is slow.
