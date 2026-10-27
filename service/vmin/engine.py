"""Model loading and batched Vmin evaluation -- the only module that touches the GP.

Vmin is computed exactly as in the paper: posterior means of mu and sigma on the
supply grid -> z = mu / sigma -> compute_vmin_from_z (python/src/physics_layer).
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from functools import lru_cache

import gpytorch
import numpy as np
import torch

from .config import AXIS_KEYS, CFG, DEFAULTS, MODES, RESULTS, ROOT, path

sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "python" / "scripts"))
from src.physics_layer import compute_vmin_from_z  # noqa: E402
from src.surrogate import Surrogate  # noqa: E402
from src.utils import derive_z_target  # noqa: E402

CHUNK = 4000            # GP query rows per call; one 50k-row call got the process OOM-killed
OK, BELOW, ABOVE = 0, -1, 1   # Vmin inside the supply grid / below it (censored) / above it
D = len(AXIS_KEYS)


@dataclass
class ModeModel:
    name: str
    surr: Surrogate
    vops: np.ndarray
    nominal: np.ndarray      # training-batch median per axis (the paper's reference point)
    box: np.ndarray          # (D, 2) training range per axis
    source: str
    checkpoint_sha: str


def _sha(p) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _load_source(name: str, mc: dict) -> ModeModel:
    import src.final_data as fd
    from src.data import grouped_train_test_split

    df = getattr(fd, mc["loader"])()
    avg, std = mc["avg_col"], mc["std_col"]
    df = df[df[avg].notna() & df[std].notna() & df["n_mc"].notna()].copy()
    X = df[AXIS_KEYS + ["vop"]].to_numpy(float)
    y = df[[avg, std]].to_numpy(float) * 1e-3
    _, cond = np.unique(X[:, :D], axis=0, return_inverse=True)
    X_tr, _, y_tr, _ = grouped_train_test_split(
        X, y, cond, CFG["model"]["holdout_fraction"], CFG["model"]["seed"])
    ckpt = RESULTS / mc["checkpoint"]
    saved = torch.load(ckpt, map_location="cpu", weights_only=False).get("x_train")
    if saved is not None and (np.shape(saved) != X_tr.shape or not np.allclose(saved, X_tr)):
        raise RuntimeError(f"{ckpt.name}: the split rebuilt from python/data does not match "
                           "the checkpoint -- axis order or data changed")
    return ModeModel(
        name, Surrogate.load(ckpt, X_tr, y_tr, n_device=D),
        np.array(sorted(df["vop"].unique()), float),
        np.array([float(np.median(df[c])) for c in AXIS_KEYS]),
        np.array([[X[:, i].min(), X[:, i].max()] for i in range(D)]),
        "checkpoint + canonical training split", _sha(ckpt))


def _load_bundle(name: str, mc: dict) -> ModeModel:
    p = path(CFG["model"]["bundle_dir"]) / mc["bundle"]
    meta = torch.load(p, map_location="cpu", weights_only=False).get("demo_bundle") or {}
    if meta.get("mode") != name or list(meta.get("device_cols", [])) != AXIS_KEYS:
        raise RuntimeError(f"{p.name} is not a {name} bundle with axis order {AXIS_KEYS}")
    return ModeModel(
        name, Surrogate.load(p, n_device=D), np.array(meta["vops"], float),
        np.array([meta["nominal"][k] for k in AXIS_KEYS], float),
        np.array([meta["bounds"][k] for k in AXIS_KEYS], float),
        "trusted inference bundle", meta.get("source_checkpoint_sha256", "")[:12])


def vmin_from_z(zg: np.ndarray, z: float, vops: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vmin and status per row. BELOW rows carry the library's placeholder vops[0]-0.05."""
    v, cen = compute_vmin_from_z(zg, z, vops=vops, return_censored=True)
    return v, np.where(cen, BELOW, np.where(np.isnan(v), ABOVE, OK))


def resolve_z(zs: dict) -> tuple[float, str]:
    """Z threshold from the spec: direct value, or array size and yield (D-01)."""
    if zs.get("value") not in (None, ""):
        z, text = float(zs["value"]), "직접 입력"
    else:
        mb, yt = float(zs["array_mb"]), float(zs["yield"])
        z, text = derive_z_target(mb=mb, y_target=yt), f"{mb:g} Mb @ {yt * 100:g} % yield"
    if zs.get("lobe"):
        b = lobe_bias(round(z, 4))
        z, text = z + b, text + f" + lobe 보정 {b:+.3f}"
    return z, text


@lru_cache(maxsize=64)
def lobe_bias(z: float) -> float:
    """D-07 min-of-two correction at this Z (same rng seed as _paths.selfcheck)."""
    from infab_snmr_tail_diag import bias_at_target
    return float(bias_at_target(DEFAULTS["lobe_rho"], z, np.random.default_rng(12345))[1])


def _sqrt_psd(c: np.ndarray) -> np.ndarray:
    w, v = np.linalg.eigh(0.5 * (c + c.T))
    return v * np.sqrt(np.clip(w, 0.0, None))


class Engine:
    def __init__(self, modes: dict[str, ModeModel]):
        self.modes = modes
        self._chol: dict[tuple[str, str], tuple[torch.Tensor, torch.Tensor]] = {}
        self.reference: dict[tuple[str, str], dict] = {}   # (mode, corner) -> saved §V-D values

    @classmethod
    def load(cls, source: str | None = None) -> "Engine":
        source = source or CFG["model"]["source"]
        if source == "auto":
            source = "source" if any((ROOT / "python" / "data").glob("final*.xlsx")) else "bundle"
        loader = _load_source if source == "source" else _load_bundle
        return cls({name: loader(name, mc) for name, mc in MODES.items()})

    def predict(self, mode: str, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Posterior means of mu and sigma, (n, n_vop) each."""
        m = self.modes[mode]
        rows = np.atleast_2d(rows)
        nv = len(m.vops)
        X = np.column_stack([np.repeat(rows, nv, axis=0), np.tile(m.vops, len(rows))])
        mu, sg = np.empty(len(X)), np.empty(len(X))
        for i in range(0, len(X), CHUNK):
            mu[i:i + CHUNK], sg[i:i + CHUNK] = m.surr.predict_mean(X[i:i + CHUNK])
        return mu.reshape(-1, nv), sg.reshape(-1, nv)

    def zgrid(self, mode: str, rows: np.ndarray) -> np.ndarray:
        mu, sg = self.predict(mode, rows)
        return mu / (sg + 1e-12)

    def vmin(self, mode: str, rows: np.ndarray, z: float) -> tuple[np.ndarray, np.ndarray]:
        return vmin_from_z(self.zgrid(mode, rows), z, self.modes[mode].vops)

    def _posterior(self, mode: str, which: str, xt: torch.Tensor) -> tuple[np.ndarray, np.ndarray]:
        """Exact latent posterior mean and covariance at xt.

        gpytorch's default covariance path on these 8,500-point models is CG (sigma
        sd ~34 % too wide) or LOVE (up to ~80 % too wide); its exact Cholesky path
        refactors on every call (~3 s). So the training Cholesky is factored once per
        GP here (~6 s, ~0.6 GB) and reused -- only robust analyses ever pay for it.
        """
        gp = getattr(self.modes[mode].surr, f"{which}_gp")
        key = (mode, which)
        with torch.no_grad(), gpytorch.settings.skip_posterior_variances(True):
            mean = gp(xt).mean.double()               # also builds prediction_strategy
            if key not in self._chol:
                ps = gp.prediction_strategy
                K = ps.lik_train_train_covar.to_dense().double()
                jitter = 1e-10 * float(K.diagonal().mean())
                while True:
                    L, info = torch.linalg.cholesky_ex(K + jitter * torch.eye(len(K), dtype=K.dtype))
                    if int(info) == 0:
                        break
                    jitter *= 10.0
                self._chol[key] = (L, ps.train_inputs[0])
                del K
            L, tx = self._chol[key]
            kst = gp.covar_module(xt, tx).to_dense().double()
            kss = gp.covar_module(xt).to_dense().double()
            v = torch.linalg.solve_triangular(L, kst.T, upper=False)
            cov = kss - v.T @ v
        return mean.numpy(), cov.numpy()

    def posterior_vmin(self, mode: str, rows: np.ndarray, z: float, n: int, seed: int) -> np.ndarray:
        """(n, rows) Vmin draws from the joint latent posterior of mu and log sigma
        over all supplies of the given rows. ABOVE -> +inf. A fixed seed gives
        common random numbers, so the draws move smoothly with the rows."""
        m = self.modes[mode]
        s = m.surr
        rows = np.atleast_2d(rows)
        nv = len(m.vops)
        X = np.column_stack([np.repeat(rows, nv, axis=0), np.tile(m.vops, len(rows))])
        xt = s._to_tensor(s._x_scaler.transform(X))   # same transform predict_mean uses
        mm, cm = self._posterior(mode, "mu", xt)
        ms, cs = self._posterior(mode, "sigma", xt)
        rng = np.random.default_rng(seed)
        mu = mm[:, None] + _sqrt_psd(cm) @ rng.standard_normal((len(X), n))
        sg = np.exp(ms[:, None] + _sqrt_psd(cs) @ rng.standard_normal((len(X), n)))
        zz = (mu / sg).reshape(len(rows), nv, n).transpose(2, 0, 1).reshape(-1, nv)
        v, st = vmin_from_z(zz, z, m.vops)
        return np.where(st == ABOVE, np.inf, v).reshape(n, len(rows))

    def info(self) -> dict:
        return {name: dict(label=MODES[name]["label"], metric=MODES[name]["metric"],
                           temperature_C=MODES[name]["temperature_C"], vops=m.vops.tolist(),
                           nominal=dict(zip(AXIS_KEYS, m.nominal.tolist())),
                           box={k: m.box[i].tolist() for i, k in enumerate(AXIS_KEYS)},
                           source=m.source, checkpoint=m.checkpoint_sha)
                for name, m in self.modes.items()}

    def selfcheck(self) -> list[dict]:
        """Re-predict the saved §V-D corners; any drift means stale models or config."""
        out = []
        ic, ip = AXIS_KEYS.index("cn"), AXIS_KEYS.index("pu")
        for name, mc in MODES.items():
            ref = RESULTS / mc["reference"]
            if name not in self.modes or not ref.is_file():
                continue
            saved = json.loads(ref.read_text())
            m = self.modes[name]
            rows = np.tile(m.nominal, (len(saved["corners"]), 1))
            rows[:, ic] = [c["cn"] for c in saved["corners"]]
            rows[:, ip] = [c["pu"] for c in saved["corners"]]
            v, _ = self.vmin(name, rows, saved["z_target"])
            for c, now in zip(saved["corners"], v):
                out.append(dict(mode=name, corner=c["corner"], saved=c["vmin_pred"],
                                now=float(now), hspice=c["vmin_meas"],
                                hspice_censored=c["censored_meas"],
                                ok=bool(abs(now - c["vmin_pred"]) < 1e-4)))
                self.reference[(name, c["corner"])] = out[-1]
        return out
