"""terrain — the semantic world's short-term map of ground and seen things (docs/TERRAIN-MEMORY.md v2): the numpy
REFERENCE, the oracle for the C++ TerrainMemory node's tests (percept, 2026-11-23).

    m = TerrainMemory(rig, Params())
    m.update(frame, pose, t, source="mono")   # one SPR frame (base_link layers) at its capture pose in the odometry frame
    out = m.publish(pose)                     # the fused grid in base_link, the SPR layout + sigma / age; m.objects()

A chair-centred rolling window on the ODOMETRY frame (x, y fixed to the ground), shifted in whole cells, never rotated
or interpolated (§3). Per cell (§4): elevation as an information-form Kalman state (precision, precision x mean) plus a
BIAS FLOOR that averaging cannot remove (§5: a mono range error is systematic per viewpoint); occupancy log-odds per
height band, static and mover apart; Dirichlet class counts; when and at which odometer reading it was last seen.

The update (§5): every measurement cell with direct points (SPR `points` > 0; without that layer: observed) spreads
over a sparse kernel whose support is its pixel's ground footprint (>= 1.5 cells); splat-only cells (points == 0) are
skipped (the kernel does that job). Free space is carved along the camera rays, a mono ray only up to its range minus
(0.3 m + 2 sigma). Forgetting by time AND distance travelled (§6), movers within ~1 s. Edges (§8): a KERB is a step of
the FUSED elevation above max(0.10 m, 2 sigma, the bias floor) with consistent floor on both sides; a floor that sinks
smoothly with range never is. Seen objects (§7): connected patches of fused static obstacle cells.

numpy is the only dependency (the extra `terrain`); the rest of the library does not import this module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# SprClass ids (spr package.art): ground 1-4, movers, the rest obstacles
FLOOR, KERB, DROP, RAMP = 1, 2, 3, 4
MOVERS = (9, 10, 11)                    # person, vehicle, mobility equipment
N_CLASS = 14
# height_band bits (SPR.md: ground, low to 0.4 m, body to 1.2 m, overhang above) -> occupancy bands 0..2 (low, body,
# overhang); the ground bit is the floor itself, not an occupancy
BAND_BITS = (2, 4, 8)
BAND_Z = ((0.05, 0.40), (0.40, 1.20), (1.20, 2.20))


@dataclass
class Params:
    res: float = 0.10
    size: int = 160                     # cells a side (16 m at 0.10 m: the wc SPR grid)
    pix_rad: float = math.radians(100.0) / 96   # the network's pixel angle (100 deg over 96 px: teacher stride 4)
    support_min_cells: float = 1.5
    support_max_m: float = 0.6
    bias_frac: float = 0.05             # mono: the range bias floor (fraction of the range)
    sigma_default: float = 0.05         # m, when the frame has no sigma_z layer
    l_hit: float = 0.85
    l_free: float = -0.4
    l_min: float = -2.0
    l_max: float = 3.5
    occ_thresh: float = 0.6             # log-odds: an occupied band
    alpha0: float = 0.01                # the Dirichlet prior per class
    half_time_s: float = 10.0           # static evidence: half weight after 10 s ...
    half_dist_m: float = 5.0            # ... or 5 m travelled
    mover_half_s: float = 0.25          # movers: gone within ~1 s (4 half-lives)
    drift_frac: float = 0.02            # odometry drift per metre: inflates the elevation variance of old evidence
    carve_margin_m: float = 0.3         # mono carve limit: range - (margin + 2 sigma)
    kerb_min_m: float = 0.10
    kerb_flat_m: float = 0.03           # 'consistent floor': neighbours on one side within this of each other
    seen_weight: float = 0.3            # a cell counts as observed above this much kernel weight (decayed)
    mono_weight: float = 1.0
    truth_weight: float = 1.0


def sparse_kernel(d, r):
    """The sparse kernel of BKI (Melkumyan & Ramos): 1 at d = 0, 0 (with zero slope) at d >= r."""
    x = np.clip(d / np.maximum(r, 1e-6), 0.0, 1.0)
    k = (2 + np.cos(2 * np.pi * x)) / 3 * (1 - x) + np.sin(2 * np.pi * x) / (2 * np.pi)
    return np.where(d < r, k, 0.0)


@dataclass
class Rig:
    """The camera poses in base_link: name -> (x, y, z, yaw_deg, pitch_deg); bit i of SPR `cams` = the i-th camera."""
    cams: list = field(default_factory=lambda: [("fl", (0.36, 0.28, 0.75, 25, -15)), ("fr", (0.36, -0.28, 0.75, -25, -15)),
                                                ("rl", (0.05, 0.24, 0.95, 140, -15)), ("rr", (0.05, -0.24, 0.95, -140, -15))])


class TerrainMemory:
    def __init__(self, rig: Rig | None = None, p: Params | None = None):
        self.rig, self.p = rig or Rig(), p or Params()
        n = self.p.size
        self.org = None                                   # the window's lower-left cell (integers) in the odom frame
        self.prec = np.zeros((n, n))                      # elevation precision (1 / m^2)
        self.pm = np.zeros((n, n))                        # precision x mean
        self.bias2 = np.zeros((n, n))                     # the kernel-weighted bias floor^2 of what was fused
        self.bw = np.zeros((n, n))                        #   its weight
        self.L = np.zeros((3, n, n))                      # static occupancy log-odds, bands low / body / overhang
        self.Lm = np.zeros((3, n, n))                     # movers' occupancy
        self.alpha = np.full((N_CLASS, n, n), self.p.alpha0)
        self.w = np.zeros((n, n))                         # decayed kernel weight seen (observed when > seen_weight)
        self.t_seen = np.full((n, n), -np.inf)
        self.d_seen = np.full((n, n), -np.inf)
        self.t_mover = np.full((n, n), -np.inf)          # the last mover hit (a walker's trail: Lm without a recent hit)
        self.t = None
        self.odo = 0.0                                    # odometer: distance travelled (m)
        self.last_xy = None

    # ---- the window -------------------------------------------------------------------------------------------
    def _shift_to(self, x, y):
        n, r = self.p.size, self.p.res
        want = (int(math.floor(x / r)) - n // 2, int(math.floor(y / r)) - n // 2)
        if self.org is None:
            self.org = want
            return
        dx, dy = want[0] - self.org[0], want[1] - self.org[1]
        if dx == 0 and dy == 0:
            return
        for name in ("prec", "pm", "bias2", "bw", "w", "t_seen", "d_seen", "t_mover", "L", "Lm", "alpha"):
            a = getattr(self, name)
            fill = {"t_seen": -np.inf, "d_seen": -np.inf, "t_mover": -np.inf, "alpha": self.p.alpha0}.get(name, 0.0)
            setattr(self, name, _shift(a, dx, dy, fill))
        self.org = want

    def _cell(self, x, y):
        r = self.p.res
        return (np.floor(x / r).astype(np.int64) - self.org[0], np.floor(y / r).astype(np.int64) - self.org[1])

    # ---- forgetting -------------------------------------------------------------------------------------------
    def _forget(self, dt, dd):
        p = self.p
        lam = 0.5 ** (dt / p.half_time_s + dd / p.half_dist_m)
        lam_m = 0.5 ** (dt / p.mover_half_s)
        self.L *= lam
        self.Lm *= lam_m
        a0 = p.alpha0
        mov = np.zeros(N_CLASS, bool); mov[list(MOVERS)] = True
        self.alpha[~mov] = a0 + (self.alpha[~mov] - a0) * lam
        self.alpha[mov] = a0 + (self.alpha[mov] - a0) * lam_m
        self.w *= lam
        # old evidence: its precision decays, and the odometry drift since adds variance
        self.prec *= lam
        q = (p.drift_frac * dd) ** 2
        if q > 0:
            known = self.prec > 0
            newp = np.where(known, 1.0 / (1.0 / np.where(known, self.prec, 1) + q), 0.0)
            self.pm = np.where(known, self.pm / np.where(known, self.prec, 1) * newp, 0.0)
            self.prec = newp
        else:
            self.pm *= lam

    # ---- the update -------------------------------------------------------------------------------------------
    def update(self, f: dict, pose, t: float, source: str = "mono"):
        """f: one SPR frame's layers in base_link (observed, class, class_conf, height_band, elevation (cm), and
        when present points, sigma_z (cm), cams) + its grid (res, ox, oy: the centre of cell (0, 0)). pose: base_link
        in the odometry frame (x, y, yaw rad) AT THE CAPTURE STAMP. t: that stamp (s)."""
        p = self.p
        x0, y0, yaw = pose
        if self.last_xy is not None:
            self.odo += math.hypot(x0 - self.last_xy[0], y0 - self.last_xy[1])
            dd = math.hypot(x0 - self.last_xy[0], y0 - self.last_xy[1])
        else:
            dd = 0.0
        dt = 0.0 if self.t is None else max(0.0, t - self.t)
        self._shift_to(x0, y0)
        if self.t is not None:
            self._forget(dt, dd)
        self.t, self.last_xy = t, (x0, y0)

        obs = f["observed"] == 0
        sel = obs & (f["points"] > 0) if "points" in f else obs
        iy, ix = np.nonzero(sel)
        if not len(ix):
            return
        res, ox, oy = f["res"], f["ox"], f["oy"]
        bx, by = ox + ix * res, oy + iy * res                       # base_link cell centres
        cls = f["class"][iy, ix].astype(np.int64)
        conf = f["class_conf"][iy, ix] / 255.0
        band = f["height_band"][iy, ix]
        elev_raw = f["elevation"][iy, ix]
        has_e = elev_raw != -32768
        ez = np.where(has_e, elev_raw, 0) * 0.01
        sig = (np.where(f["sigma_z"][iy, ix] == 255, p.sigma_default * 100, f["sigma_z"][iy, ix]) * 0.01
               if "sigma_z" in f else np.full(len(ix), p.sigma_default))
        sig = np.maximum(sig, 0.01)                                  # a 1 cm floor: the producer's 0 cm is a resolution
        # the camera of each measurement: the lowest bit of `cams`, else the nearest camera by bearing
        cams = f["cams"][iy, ix] if "cams" in f else np.zeros(len(ix), np.uint8)
        ci = np.full(len(ix), -1)
        for k in range(len(self.rig.cams) - 1, -1, -1):
            ci = np.where((cams >> k) & 1 == 1, k, ci)
        if (ci < 0).any():
            ang = np.arctan2(by, bx)
            best = np.argmin([np.abs(_wrap(ang - math.radians(c[1][3]))) for c in self.rig.cams], axis=0)
            ci = np.where(ci < 0, best, ci)
        cpos = np.array([c[1][:3] for c in self.rig.cams])
        cx, cy, cz = cpos[ci, 0], cpos[ci, 1], cpos[ci, 2]
        zpt = np.where(has_e, ez, 0.0)
        rng = np.sqrt((bx - cx) ** 2 + (by - cy) ** 2 + (cz - zpt) ** 2)
        sin_dep = np.clip((cz - zpt) / np.maximum(rng, 1e-3), 0.05, 1.0)
        # the bias floor on z: a range error of bias_frac x range moves a downward ray's end by that x sin(depression)
        w0 = p.mono_weight if source == "mono" else p.truth_weight
        bias = (p.bias_frac * rng * sin_dep) if source == "mono" else np.zeros(len(ix))
        # the support: the pixel's ground footprint (along the ray: range x pixel angle / sin(depression))
        R = np.clip(0.5 * rng * p.pix_rad / sin_dep, p.support_min_cells * p.res, p.support_max_m)

        # to the odometry frame
        c, s = math.cos(yaw), math.sin(yaw)
        X, Y = x0 + c * bx - s * by, y0 + s * bx + c * by
        CX, CY = x0 + c * cx - s * cy, y0 + s * cx + c * cy
        gx, gy = self._cell(X, Y)

        ground = (cls >= FLOOR) & (cls <= RAMP)
        mover = np.isin(cls, MOVERS)
        obst = (cls > RAMP) & ~mover
        n = p.size
        rmax = int(math.ceil(p.support_max_m / p.res))
        for oxo in range(-rmax, rmax + 1):
            for oyo in range(-rmax, rmax + 1):
                d = math.hypot(oxo, oyo) * p.res
                k = sparse_kernel(d, R)
                tx, ty = gx + oxo, gy + oyo
                m = (k > 0) & (tx >= 0) & (ty >= 0) & (tx < n) & (ty < n)
                if not m.any():
                    continue
                kk, txm, tym = k[m] * w0, tx[m], ty[m]
                np.add.at(self.w, (tym, txm), kk)
                np.maximum.at(self.t_seen, (tym, txm), t)
                np.maximum.at(self.d_seen, (tym, txm), self.odo)
                # class
                np.add.at(self.alpha, (cls[m], tym, txm), kk * conf[m])
                # elevation: ground cells (and obstacles' ground under them when the producer gave one)
                e_ok = m & has_e
                if e_ok.any():
                    sm = (sig[m] ** 2)[has_e[m]]
                    ke = kk[has_e[m]]
                    pe = ke / sm
                    np.add.at(self.prec, (tym[has_e[m]], txm[has_e[m]]), pe)
                    np.add.at(self.pm, (tym[has_e[m]], txm[has_e[m]]), pe * ez[m][has_e[m]])
                    np.add.at(self.bias2, (tym[has_e[m]], txm[has_e[m]]), ke * bias[m][has_e[m]] ** 2)
                    np.add.at(self.bw, (tym[has_e[m]], txm[has_e[m]]), ke)
                # occupancy: obstacles hit their bands, ground clears low + body above it
                for b, bit in enumerate(BAND_BITS):
                    hit = (band[m] & bit) > 0
                    om, mm, gm = obst[m] & hit, mover[m] & hit, ground[m]
                    if om.any():
                        np.add.at(self.L[b], (tym[om], txm[om]), kk[om] * p.l_hit)
                    if mm.any():
                        np.add.at(self.Lm[b], (tym[mm], txm[mm]), kk[mm] * p.l_hit)
                        np.maximum.at(self.t_mover, (tym[mm], txm[mm]), t)
                    # the floor clears low + body above ITS OWN cell only: spread by the kernel, many floor
                    # neighbours would outvote an obstacle's own hits at its edge
                    if b < 2 and oxo == 0 and oyo == 0 and gm.any():
                        np.add.at(self.L[b], (tym[gm], txm[gm]), kk[gm] * p.l_free)
        # carve: the rays from the camera to each measurement free the bands they pass THROUGH; a mono ray stops
        # (0.3 m + 2 sigma) short of its end. An obstacle's ray ends at the top of its highest occupied band, not on
        # the floor under it (a ray to a box's far cells would otherwise cut through its near cells)
        top = np.where((band & 8) > 0, BAND_Z[2][1], np.where((band & 4) > 0, BAND_Z[1][1], BAND_Z[0][1]))
        zpt = np.where(ground, zpt, np.maximum(zpt, top))
        horiz = np.hypot(X - CX, Y - CY)
        stop = horiz - ((p.carve_margin_m + 2 * np.sqrt(sig ** 2 + bias ** 2)) * (horiz / np.maximum(rng, 1e-3))
                        if source == "mono" else p.res)
        steps = np.arange(0.5 * p.res, horiz.max() + p.res, 0.5 * p.res)
        for sdist in steps:
            m = sdist < stop
            if not m.any():
                break
            fr = sdist / np.maximum(horiz[m], 1e-6)
            zr = cz[m] + fr * (zpt[m] - cz[m])
            rx, ry = CX[m] + fr * (X[m] - CX[m]), CY[m] + fr * (Y[m] - CY[m])
            tx, ty = self._cell(rx, ry)
            for b, (z0, z1) in enumerate(BAND_Z):
                mb = (zr >= z0) & (zr < z1) & (tx >= 0) & (ty >= 0) & (tx < n) & (ty < n)
                if mb.any():
                    np.add.at(self.L[b], (ty[mb], tx[mb]), 0.5 * w0 * p.l_free)
                    np.add.at(self.Lm[b], (ty[mb], tx[mb]), 0.5 * w0 * p.l_free)
        np.clip(self.L, p.l_min, p.l_max, out=self.L)
        np.clip(self.Lm, p.l_min, p.l_max, out=self.Lm)

    # ---- reading ----------------------------------------------------------------------------------------------
    def fused(self):
        """The window's fused layers (odometry-frame cells): observed, elevation (m, NaN unknown), sigma (m), class,
        class_conf, bands occupied (bit set as SPR height_band, the ground bit for ground), kerb mask, age (s)."""
        p = self.p
        seen = self.w > p.seen_weight
        known = self.prec > 0
        elev = np.where(known, self.pm / np.where(known, self.prec, 1), np.nan)
        bias2 = np.where(self.bw > 0, self.bias2 / np.where(self.bw > 0, self.bw, 1), 0.0)
        sigma = np.where(known, np.sqrt(1.0 / np.where(known, self.prec, 1) + bias2), np.nan)
        tot = self.alpha.sum(0)
        cls = self.alpha.argmax(0)
        conf = self.alpha.max(0) / tot
        occ = (self.L > p.occ_thresh) | (self.Lm > p.occ_thresh)
        bands = np.zeros(self.w.shape, np.uint8)
        for b, bit in enumerate(BAND_BITS):
            bands |= np.where(occ[b], bit, 0).astype(np.uint8)
        is_ground = seen & (cls >= FLOOR) & (cls <= RAMP) & ~occ[0] & ~occ[1]
        bands |= np.where(is_ground, 1, 0).astype(np.uint8)
        # a cell the network called KERB but whose fused elevation has no kerb step is FLOOR; KERB comes from geometry
        cls = np.where(is_ground & (cls == KERB), FLOOR, cls)
        kerb = self._kerbs(elev, sigma, is_ground, bias2)
        cls = np.where(kerb, KERB, cls)
        # an occupied static band over a ground-class cell: an obstacle of the class with most evidence after ground
        obst_cls = self.alpha[RAMP + 1:].argmax(0) + RAMP + 1
        cls = np.where(seen & (occ[0] | occ[1]) & (cls <= RAMP), obst_cls, cls)
        age = np.where(np.isfinite(self.t_seen), (self.t or 0.0) - self.t_seen, np.inf)
        return dict(observed=seen, elevation=elev, sigma=sigma, cls=np.where(seen, cls, 0), conf=np.where(seen, conf, 0.0),
                    bands=np.where(seen, bands, 0), kerb=kerb, age=age, weight=self.w,
                    dist_since=np.where(np.isfinite(self.d_seen), self.odo - self.d_seen, np.inf))

    def _kerbs(self, elev, sigma, ground, bias2):
        """A KERB step: between two ground cells along x or y, |step| >= max(kerb_min, 2 sigma of the step, the bias
        floor), and on EACH side two more ground cells consistent with it (within kerb_flat_m): two plateaus."""
        p = self.p
        kerb = np.zeros(elev.shape, bool)
        e = np.where(ground, elev, np.nan)
        for axis in (0, 1):
            def sh(a, k):
                return np.roll(a, -k, axis=axis)
            step = sh(e, 1) - e
            s2 = np.sqrt(sh(sigma, 1) ** 2 + sigma ** 2)
            thr = np.maximum(p.kerb_min_m, np.maximum(2 * s2, np.sqrt(np.maximum(bias2, sh(bias2, 1)))))
            low_side = (np.abs(e - sh(e, -1)) < p.kerb_flat_m) & (np.abs(sh(e, -1) - sh(e, -2)) < p.kerb_flat_m)
            high_side = (np.abs(sh(e, 2) - sh(e, 1)) < p.kerb_flat_m) & (np.abs(sh(e, 3) - sh(e, 2)) < p.kerb_flat_m)
            edge = (np.abs(step) >= thr) & low_side & high_side
            edge &= np.isfinite(step)
            kerb |= edge | sh(edge, -1)            # both cells at the step
        return kerb

    def objects(self, min_cells: int = 4):
        """Seen static objects: 8-connected patches of fused STATIC obstacle cells (low or body band occupied), as
        (cx, cy, half_x, half_y, cells) in the odometry frame."""
        p = self.p
        occ = ((self.L[0] > p.occ_thresh) | (self.L[1] > p.occ_thresh)) & (self.w > p.seen_weight)
        lab, nlab = _label(occ)
        out = []
        for i in range(1, nlab + 1):
            ys, xs = np.nonzero(lab == i)
            if len(xs) < min_cells:
                continue
            X = (self.org[0] + xs + 0.5) * p.res
            Y = (self.org[1] + ys + 0.5) * p.res
            out.append((X.mean(), Y.mean(), (X.max() - X.min()) / 2 + p.res / 2, (Y.max() - Y.min()) / 2 + p.res / 2, len(xs)))
        return out

    def publish(self, pose, res=None, size=None):
        """The fused grid in base_link at `pose` (nearest cell): the SPR wc layout (cell (0, 0) centre at -size/2 res +
        res/2) with observed (0 seen / 255), class, class_conf (u8), height_band, elevation (cm, -32768), step (cm),
        sigma (cm, 255 unknown), age (0.1 s, 255 = 25.5 s or more / unknown)."""
        p = self.p
        res, size = res or p.res, size or p.size
        F = self.fused()
        x0, y0, yaw = pose
        o = -0.5 * size * res + 0.5 * res
        bx, by = np.meshgrid(o + np.arange(size) * res, o + np.arange(size) * res)
        c, s = math.cos(yaw), math.sin(yaw)
        tx, ty = self._cell(x0 + c * bx - s * by, y0 + s * bx + c * by)
        n = p.size
        ok = (tx >= 0) & (ty >= 0) & (tx < n) & (ty < n)
        txc, tyc = np.clip(tx, 0, n - 1), np.clip(ty, 0, n - 1)
        g = lambda a, fill: np.where(ok, a[tyc, txc], fill)
        seen = g(F["observed"], False)
        elev = g(F["elevation"], np.nan)
        e_cm = np.where(seen & np.isfinite(elev), np.round(elev * 100), -32768).astype(np.int16)
        sig = g(F["sigma"], np.nan)
        age = g(F["age"], np.inf)
        out = dict(observed=np.where(seen, 0, 255).astype(np.uint8),
                   **{"class": np.where(seen, g(F["cls"], 0), 0).astype(np.uint8)},
                   class_conf=np.where(seen, np.round(255 * g(F["conf"], 0.0)), 0).astype(np.uint8),
                   height_band=np.where(seen, g(F["bands"], 0), 0).astype(np.uint8),
                   elevation=e_cm,
                   sigma=np.where(seen & np.isfinite(sig), np.clip(np.round(sig * 100), 0, 254), 255).astype(np.uint8),
                   age=np.where(seen & np.isfinite(age), np.clip(np.round(age * 10), 0, 255), 255).astype(np.uint8))
        e = np.where(e_cm == -32768, np.nan, e_cm.astype(float))
        st = np.full(e.shape, np.nan)
        for d in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nb = np.roll(e, d, axis=(0, 1))
            dd = nb - e
            st = np.where(np.isnan(st) | (np.abs(dd) > np.abs(st)), dd, st)
        out["step"] = np.where(np.isfinite(st), np.clip(st, -127, 127), -128).astype(np.int8)
        return out


def _shift(a, dx, dy, fill):
    """Shift a window (..., y, x) by whole cells: the new origin is (dx, dy) cells further; what enters is `fill`."""
    out = np.full_like(a, fill)
    H, W = a.shape[-2], a.shape[-1]
    if abs(dx) >= W or abs(dy) >= H:
        return out
    src_x = slice(max(dx, 0), W + min(dx, 0)); dst_x = slice(max(-dx, 0), W + min(-dx, 0))
    src_y = slice(max(dy, 0), H + min(dy, 0)); dst_y = slice(max(-dy, 0), H + min(-dy, 0))
    out[..., dst_y, dst_x] = a[..., src_y, src_x]
    return out


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def _label(mask):
    """8-connected component labels of a boolean grid (no scipy)."""
    lab = np.zeros(mask.shape, np.int32)
    H, W = mask.shape
    n = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        n += 1
        stack = [(y0, x0)]
        lab[y0, x0] = n
        while stack:
            y, x = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = n
                        stack.append((yy, xx))
    return lab, n
