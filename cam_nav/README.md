# cam_nav

Gamepad camera navigation for TouchDesigner. Drop it into a project, point a Render TOP at `cam_nav/cam`,
and fly through the scene with an Xbox controller.

Tested with an Xbox controller on Windows, TouchDesigner 2025.32820.

## Install

1. Copy [`scripts/`](scripts/) to `<your project folder>/scripts/cam_nav/`. The three script DATs inside the
   component sync to those relative paths.
2. Drag [`cam_nav.tox`](cam_nav.tox) into your network.
3. Set your Render TOP's **Camera** parameter to `cam_nav/cam` (adjust the path to wherever you placed it).
4. **Click the TouchDesigner window** and move a stick. TouchDesigner only reads the controller while its window
   has focus.

## Controls

The sticks are swapped relative to the usual "left stick moves" convention: **right stick moves, left stick looks**.

| Input | Action |
| --- | --- |
| Right stick | Move (forward/back, strafe) |
| Left stick | Look (turn, pitch) |
| RB / LB | Up / down |
| RT | Boost (multiplies movement **and** turning) |
| LT | Slow (multiplies movement **and** turning) |
| A | Reset to the stored home pose |

## `Nav` parameters

| Parameter | Default | Meaning |
| --- | --- | --- |
| Active | on | Master enable |
| Speed | 2 | Movement speed, units per second |
| Turn Speed | 10 | Turning speed, degrees per second |
| Boost Mult | 4 | Speed factor at full boost |
| Slow Mult | 0.25 | Speed factor at full slow |
| Dead Zone | 0.15 | Radial stick dead zone (shared by both sticks) |
| Expo | 2 | Response curve exponent; higher is gentler near the centre |
| Smooth | 0.08 | Smoothing time in seconds |
| Invert Y | off | Invert look up/down |
| Fly | on | Forward follows pitch; off keeps movement level |
| Pitch Limit | 89 | Maximum pitch in degrees |
| Home Pos / Yaw / Pitch | 0, 0, 5 / 0 / 0 | Pose that Reset returns to |
| Reset | pulse | Jump to home |
| Set Home | pulse | **Store the current pose as home** (it overwrites the previous home) |

## How it works

| Operator | Role |
| --- | --- |
| `joystick1` (Joystick CHOP) | Reads the controller; axis range -1..1, its own dead zone is 0, `connected` channel enabled |
| `ctrl` (Null CHOP) | Raw controller channels |
| `map` (Table DAT) | Maps controller channels to roles (see below) |
| `CamNavExt` (Text DAT) | Python extension: dead zone, response curve, smoothing and per-frame integration |
| `frame_exec` (Execute DAT) | Calls `Step()` once per frame |
| `par_exec` (Parameter Execute DAT) | Handles the Reset and Set Home pulses |
| `rig` (Null COMP) | Carries position and yaw |
| `cam` (Camera COMP) | Parented to `rig` via Parent Transform Source = Specify; carries pitch |

The camera looks down -Z with +Y up. Per-frame cost of `Step()` is about 0.08 ms.

### Channel map

Edit the `map` table to change which controller channel drives which role. `full` is the channel value at full
deflection in the positive direction (a reversed axis uses `-1`).

| role | chan | rest | full | Input |
| --- | --- | --- | --- | --- |
| move_x | xrot | 0 | 1 | right stick, left/right |
| move_z | yrot | 0 | 1 | right stick, up/down |
| look_x | xaxis | 0 | 1 | left stick, left/right |
| look_y | yaxis | 0 | 1 | left stick, up/down |
| up | b6 | 0 | 1 | RB |
| down | b5 | 0 | 1 | LB |
| boost | zaxis | 0 | -1 | RT |
| slow | zaxis | 0 | 1 | LT |
| reset | b1 | 0 | 1 | A |

The triggers share one axis: RT goes negative and LT goes positive. These channel names were measured on one
Xbox controller; other controllers or drivers may differ. To recalibrate, watch the `ctrl` CHOP while pressing
inputs and update `map`.

## Notes

- The Null COMP `rig` contains a default `primitivePOP` child (TouchDesigner's default for new Null COMPs). It is
  not rendered unless a Render TOP's Geometry parameter includes it.
- A newly created Camera COMP starts at tz=5; `cam` is set to 0 here so the rig position is the camera position.
- Edit the scripts in `scripts/`, not inside the DATs. They are file-synced and reload on save.
