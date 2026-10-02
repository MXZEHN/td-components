"""
CamNavExt - gamepad navigation for a camera rig.

Reads raw controller channels from the CHOP 'ctrl', maps them to roles via
the Table DAT 'map', shapes them (radial dead zone, response curve,
smoothing) and integrates position/orientation once per frame.

Coordinate convention: camera looks down -Z, +Y is up.
Yaw lives on the Null COMP 'rig' (ry), pitch on the Camera COMP 'cam' (rx).
"""

import math
import time

ROLES = ('move_x', 'move_z', 'look_x', 'look_y',
         'up', 'down', 'boost', 'slow', 'reset')

SMOOTHED = ('move_x', 'move_y', 'move_z', 'look_x', 'look_y')


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class CamNavExt:

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self._lastTime = None
        self._resetHeld = False
        self._s = dict.fromkeys(SMOOTHED, 0.0)
        # Pick up the current rig state so a script reload does not
        # snap the camera back to the home position.
        rig, cam = self._rig(), self._cam()
        if rig is not None and cam is not None:
            self.pos = [rig.par.tx.eval(), rig.par.ty.eval(), rig.par.tz.eval()]
            self.yaw = rig.par.ry.eval()
            self.pitch = cam.par.rx.eval()
        else:
            self.pos = [0.0, 0.0, 5.0]
            self.yaw = 0.0
            self.pitch = 0.0

    # ---- operators -------------------------------------------------

    def _rig(self):
        return self.ownerComp.op('rig')

    def _cam(self):
        return self.ownerComp.op('cam')

    # ---- public ----------------------------------------------------

    def Reset(self):
        """Jump to the stored home position and orientation."""
        p = self.ownerComp.par
        self.pos = [p.Homeposx.eval(), p.Homeposy.eval(), p.Homeposz.eval()]
        self.yaw = p.Homeyaw.eval()
        self.pitch = p.Homepitch.eval()
        self._s = dict.fromkeys(SMOOTHED, 0.0)
        self._write()

    def SetHome(self):
        """Store the current position and orientation as home."""
        p = self.ownerComp.par
        p.Homeposx, p.Homeposy, p.Homeposz = self.pos
        p.Homeyaw = self.yaw
        p.Homepitch = self.pitch

    def Step(self):
        """Advance the navigation by one frame. Call once per frame."""
        # Wall-clock delta; only differences are used, so no precision drift.
        now = time.perf_counter()
        last, self._lastTime = self._lastTime, now
        if last is None:
            return
        dt = _clamp(now - last, 0.0, 0.1)
        p = self.ownerComp.par
        if dt <= 0.0 or not p.Active.eval():
            return

        raw = self._read()

        # Reset on button press (rising edge only).
        resetDown = raw['reset'] > 0.5
        if resetDown and not self._resetHeld:
            self.Reset()
        self._resetHeld = resetDown

        dz = _clamp(p.Deadzone.eval(), 0.0, 0.9)
        expo = max(p.Expo.eval(), 0.1)
        mx, mz = self._shape(raw['move_x'], raw['move_z'], dz, expo)
        lx, ly = self._shape(raw['look_x'], raw['look_y'], dz, expo)
        if p.Inverty.eval():
            ly = -ly

        target = {
            'move_x': mx,
            'move_z': mz,
            'move_y': max(raw['up'], 0.0) - max(raw['down'], 0.0),
            'look_x': lx,
            'look_y': ly,
        }

        # Frame-rate independent exponential smoothing.
        smooth = p.Smooth.eval()
        a = 1.0 if smooth <= 0.0 else 1.0 - math.exp(-dt / smooth)
        s = self._s
        for k in SMOOTHED:
            s[k] += (target[k] - s[k]) * a

        boost = _clamp(raw['boost'], 0.0, 1.0)
        slow = _clamp(raw['slow'], 0.0, 1.0)
        # Boost and slow scale both movement and rotation.
        mult = (1.0 + (p.Boostmult.eval() - 1.0) * boost)              * (1.0 + (p.Slowmult.eval() - 1.0) * slow)
        speed = p.Speed.eval() * mult

        # Orientation. Stick right -> look right -> ry decreases.
        turn = p.Turnspeed.eval() * mult
        lim = _clamp(p.Pitchlimit.eval(), 0.0, 89.9)
        self.yaw -= s['look_x'] * turn * dt
        self.yaw = (self.yaw + 180.0) % 360.0 - 180.0
        self.pitch = _clamp(self.pitch + s['look_y'] * turn * dt, -lim, lim)

        # Movement relative to the current heading.
        yr = math.radians(self.yaw)
        sy, cy = math.sin(yr), math.cos(yr)
        right = (cy, 0.0, -sy)
        if p.Fly.eval():
            pr = math.radians(self.pitch)
            sp, cp = math.sin(pr), math.cos(pr)
            fwd = (-sy * cp, sp, -cy * cp)
        else:
            fwd = (-sy, 0.0, -cy)

        step = speed * dt
        self.pos[0] += (right[0] * s['move_x'] + fwd[0] * s['move_z']) * step
        self.pos[1] += (fwd[1] * s['move_z'] + s['move_y']) * step
        self.pos[2] += (right[2] * s['move_x'] + fwd[2] * s['move_z']) * step

        self._write()

    # ---- internals -------------------------------------------------

    def _read(self):
        """Return {role: normalized value} from the controller CHOP."""
        out = dict.fromkeys(ROLES, 0.0)
        src = self.ownerComp.op('ctrl')
        table = self.ownerComp.op('map')
        if src is None or table is None:
            return out
        conn = src.chan('connected')
        if conn is not None and conn.eval() < 0.5:
            return out
        for r in range(1, table.numRows):
            role = table[r, 'role'].val
            name = table[r, 'chan'].val
            if role not in out or not name:
                continue
            ch = src.chan(name)
            if ch is None:
                continue
            try:
                rest = float(table[r, 'rest'].val)
                full = float(table[r, 'full'].val)
            except ValueError:
                continue
            span = full - rest
            if abs(span) < 1e-6:
                continue
            out[role] = _clamp((ch.eval() - rest) / span, -1.0, 1.0)
        return out

    @staticmethod
    def _shape(x, y, dz, expo):
        """Radial dead zone plus response curve for one stick."""
        m = math.hypot(x, y)
        if m <= dz or m <= 0.0:
            return 0.0, 0.0
        m2 = min(1.0, (m - dz) / (1.0 - dz)) ** expo
        return x / m * m2, y / m * m2

    def _write(self):
        rig, cam = self._rig(), self._cam()
        if rig is None or cam is None:
            return
        rig.par.tx, rig.par.ty, rig.par.tz = self.pos
        rig.par.ry = self.yaw
        cam.par.rx = self.pitch
