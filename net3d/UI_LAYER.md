# net3d UI layer: design

Goal: record complete TouchDesigner tutorials as a 3D visualisation that looks as close as possible to TD's own 2D
UI.

## The principle: re-use TD's pixels

TouchDesigner already renders every piece of its UI exactly, and it can grab its own window (Screen Grab TOP).
So net3d **re-places TD's pixels instead of imitating them**:

- **Looks** come from the grab, so they are exact by definition.
- **Structure and timing** come from TD's Python API: which pane is where, which network is shown, the editor's
  pan and zoom, the mouse, the keys, the current operator, its parameters, the time.
- **Overlays** are drawn by net3d only where TD shows nothing that a viewer could see: the cursor, clicks, held
  mouse buttons, pressed keys.

Only one thing is genuinely 3D: the network itself. Everything else stays 2D, on a layer on top.

## Layers

```
out1 = over( UI layer , 3D world placed in the window )
```

| Layer | Space | Contents |
| --- | --- | --- |
| **World** (`render`) | 3D | Node slabs with their **real tiles** (cropped from the grab), bezier wires (also across levels and for references), annotations, frames, hover/current border, error and warning badges (drawn fallback). |
| **UI** (`render_ui`) | 2D, window UV, always on top | TD chrome as crops of the grab (panes, timeline, menu bar, path bar), popups as crops at the point they open, overlays (cursor, ripples, mouse buttons, keys). |

The UI layer works in window coordinates (u, v in 0..1, origin bottom left), so a crop of the grab lands exactly
where TD drew it. An orthographic 1 x 1 camera (`cam_ui`) renders it.

## Camera modes

| Mode | What it does |
| --- | --- |
| **Mirror Editor View** (default) | The 3D camera sits so the edited network lines up with the editor pixel for pixel: same centre, same zoom. Straight on, the output *is* TD. The 3D shows when you dive into or out of components, use Explode, or move the camera away. |
| **Follow New Operators** | The camera flies to the newest or last-moved operator (the earlier behaviour). |

Dives (entering or leaving components) run in both modes. In Mirror mode a dive ends on the editor's view of the
new network.

## Chrome modes

| Mode | Output |
| --- | --- |
| **Around the Editor** (default) | Like TD: all panes, timeline and menu bar where they are, the 3D network inside the network editor's rectangle. |
| **Fade In When Used** | The 3D network fills the frame. Each piece of chrome fades in while it is used (mouse over it, clicked, parameters changed, time jumped) and fades out after Hold. |
| **Off** | 3D only, plus the overlays. |

## Inventory: every visual element that can come up while editing

| Element | Source of truth | Layer | Representation | When shown |
| --- | --- | --- | --- | --- |
| Node tiles (viewer, name, flags, colour, error/warning badge) | grab, cropped at the tile's editor rect | World | Real pixels on the 3D slab; a Cache TOP keeps the last frame it was fully on screen | Always; drawn tile until first seen |
| Live viewers in tiles | grab (inside tile) | World | Live while visible, last frame when not | Always |
| Wires | API (connectors) | World | 3D bezier ribbons, family colour | Always |
| Wires to In/Out OPs across levels, references (Select OPs, ...) | API | World | Same bezier ribbons, easing between depths | Toggle |
| Annotations, network boxes | API | World | Panels | Always |
| Hover highlight | API + mouse mapping | World | Border colour (`hover`) | Mouse over a tile |
| Current / selected | API | World | Border colour; also in the tile pixels | Always |
| Errors / warnings | API `errors()` / `warnings()` | World | Badge (drawn tiles); real badge in captured tiles | While present |
| Path bar | grab (top strip of the editor pane) | UI | Crop | Like TD / when diving |
| Parameter pane, incl. tooltips, sliders, ladders, field editing | grab (pane rect) | UI | Crop | Like TD / on parameter change or mouse over |
| Timeline / transport | grab (`regions` table) | UI | Crop | Like TD / on play, pause or jump |
| Menu bar | grab (`regions`) | UI | Crop | Always / when used |
| Other docked panes (textport, palette, OP snippets, geometry/panel viewers, ...) | grab (pane rect) | UI | Crop | Like TD / mouse over |
| Right-click menu | grab around the click (`popups`) | UI | Crop | Right press in the editor until the next left click or Esc |
| OP Create dialog | grab around the cursor (`popups`) | UI | Crop | Tab in the editor until Enter, Esc or a click |
| Middle-click info popup | grab next to the click (`popups`) | UI | Crop | While the middle button is held on a node |
| Mouse cursor | Mouse In CHOP | UI | Dot; over the editor it is projected onto the 3D network plane it points at | Always (toggle) |
| Mouse buttons | Mouse In CHOP | UI | Ripples at the click (L yellow, M blue, R red); button display bottom right | On press |
| Hotkeys | Keyboard In DAT | UI | Key display (`Ctrl+C   Tab`), bottom centre | On press, fades after Hold |
| Entering/leaving components | API (editor owner) | World + UI | Dive animation; path bar fades in | On change |
| Node dragging, new operators | API (positions, new paths) | World | Tiles move; new operators grow in | Live |

### Not represented (yet), and why

| Element | Why | Possible approach |
| --- | --- | --- |
| Floating windows (floating parameter dialogs, Textport, dialogs, file browsers, error windows) | TD reports no rectangles for them | Dock them in a pane for recording, or add them as rows in `regions` |
| Wire being dragged, box selection rectangle | Drawn by the editor, which the 3D view replaces | Optional "editor lens": a crop of the editor around the cursor while dragging. It may look busy |
| Exact size of menus | Not reported | Calibrate the `popups` table once; a crop larger than the menu shows editor pixels around it |
| Editor grid | Background of the editor | Draw it on the layer plane if wanted |

## Calibration (once per machine and layout)

TD reports pane rectangles, the editor's centre and zoom, the window position and the mouse. How those numbers
are scaled differs between builds and displays (UV or pixels, monitor offsets, HiDPI). So the mapping has
calibration parameters, and an overlay to check it:

1. Turn on **Calibration Overlay**. It draws each node's predicted rectangle (pink) over the grab.
2. Adjust **Network Offset** / **Network Zoom Scale** until the pink rectangles sit on the real tiles.
3. Move the mouse over a node. It should light up (hover) and the cursor dot should sit on it. Otherwise adjust
   **Mouse Offset** / **Mouse Scale**.
4. Fill `regions` (timeline, menu bar, ...) and `popups` (menu sizes) from a screenshot.

## Signals that drive fading

| Signal | Source |
| --- | --- |
| mouse | position change or button press |
| keys | Keyboard In DAT |
| params | the current operator changed, or one of its parameter values or modes did |
| time | play/pause toggled, or the frame jumped by more than 3 |
| dive | the editor's network changed |
| `pane:<id>` / `region:<name>` | the mouse is over it, or its signal fired |

Every element fades in over **Fade Time** and holds for **Hold** seconds after its last signal.

## Recording workflow

1. Lay out TD as you want to see it: network editor, docked parameter pane, timeline.
2. Build net3d inside the project (or point **Target** at it). Turn on Live and the UI layer.
3. Calibrate (above).
4. Record `out1` (e.g. Movie File Out TOP) while you work. Use Explode, Layer Opacity or your own camera
   (Render → Camera) for 3D moments.

## Open questions to settle in TD

- Units of `pane.bottomLeft` / `topRight` (UV or pixels: both are handled) and whether `x`, `y`, `zoom` of the
  network editor mean view centre and pixels per unit. Calibration covers small differences, not a different
  meaning.
- Screen Grab TOP parameters for grabbing just the TD window, and its licence availability.
- Mouse In CHOP coordinate space (screen vs window) and channel names.
- Whether the Keyboard In DAT sees keys while the network editor has focus.
