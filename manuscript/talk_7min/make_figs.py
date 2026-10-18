"""7분 발표용 그림 -> talk_7min/figs/*.png

5분 발표 그림 함수(presentation/make_talk_figs.py)를 그대로 쓰고 출력 폴더만 바꾼다.
개념도 두 장은 "tail" 표현을 뺀 판으로 여기서 다시 그린다.
시나리오 그림(lab_*.png)은 lab/scenario_lab.py --defaults가 만든다.

usage: .venv/bin/python manuscript/talk_7min/make_figs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "presentation"))
import make_talk_figs as tf  # noqa: E402
from make_talk_figs import BLACK, BLUE, GRAY, NAVY, concept, plt  # noqa: E402

tf.OUT = HERE / "figs"
tf.OUT.mkdir(exist_ok=True)
RED = "#C0392B"


def margin_sigma():
    x = np.linspace(-0.08, 0.26, 700)
    pdf = lambda m, s: np.exp(-0.5 * ((x - m) / s) ** 2) / (s * np.sqrt(2 * np.pi))
    m, s1, s2 = 0.12, 0.02, 0.058
    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    ax.plot(x, pdf(m, s1), color=GRAY, lw=2.4, label="corner가 보는 분포 (σ 작음)")
    y2 = pdf(m, s2)
    ax.plot(x, y2, color=NAVY, lw=2.4, label="local mismatch를 더한 분포 (σ 큼)")
    fail = x <= 0
    ax.fill_between(x[fail], 0, y2[fail], color=RED, alpha=0.45)
    ax.axvline(0, color=BLACK, lw=1.2)
    ax.text(-0.004, 21, "fail ←", ha="right", fontsize=11, color=RED, weight="bold")
    ax.text(0.004, 21, "→ pass", ha="left", fontsize=11, color="#404040")
    ax.annotate("평균 μ는 같다", xy=(m, 20.2), xytext=(m + 0.035, 19), fontsize=11,
                arrowprops=dict(arrowstyle="->", color="#404040"))
    ax.annotate("σ가 커지면\nfail cell이 생긴다\n→ Vmin ↑", xy=(-0.02, 0.5), xytext=(0.006, 11.5),
                fontsize=11, color=RED, weight="bold", arrowprops=dict(arrowstyle="->", color=RED))
    ax.set_yticks([]); ax.set_ylim(0, 22.5); ax.set_xlim(-0.08, 0.24)
    ax.set_xlabel("noise margin (V)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False, fontsize=10)
    concept(ax)
    tf.save(fig, "s3_sigma")


def mu_sigma_to_vmin():
    v = np.linspace(0.4, 0.8, 200)
    mu = 0.26 * (v - 0.33)
    sig = 0.012 + 0.004 * (v - 0.4)
    k = 6.4
    vmin = v[np.argmin(np.abs(mu - k * sig))]
    fig, ax = plt.subplots(figsize=(6.2, 3.9))
    ax.fill_between(v, mu - k * sig, mu + k * sig, color=BLUE, alpha=0.13, label="μ ± k·σ  (GP ②: σ)")
    ax.plot(v, mu, color=NAVY, lw=2.6, label="margin 평균 μ  (GP ①)")
    ax.plot(v, mu - k * sig, color=BLUE, lw=2, ls="--", label="μ − k·σ")
    ax.axhline(0, color=BLACK, lw=1)
    ax.axvline(vmin, color=RED, lw=1.6)
    ax.plot(vmin, 0, "o", color=RED, ms=8)
    ax.annotate("Vmin\nμ − k·σ = 0이 되는\n가장 낮은 VDD", xy=(vmin, 0), xytext=(vmin + 0.07, -0.045),
                fontsize=11, color=RED, weight="bold", arrowprops=dict(arrowstyle="->", color=RED))
    ax.set_xlabel("공급 전압 VDD (V)"); ax.set_ylabel("noise margin (V)")
    ax.set_xticks([0.4, 0.5, 0.6, 0.7, 0.8]); ax.set_yticks([0])
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    concept(ax)
    tf.save(fig, "s5_mu_sigma")


def gp_concept():
    """GP: 수행한 조건(점) 사이를 매끄럽게 메우고, 점에서 멀수록 덜 확실하다 (개념도)."""
    x = np.linspace(0, 10, 300)
    xs = np.array([0.6, 2.2, 3.4, 6.8, 8.1, 9.5])
    f = lambda t: 0.55 + 0.04 * np.sin(t / 1.6) + 0.004 * t
    d = np.min(np.abs(x[:, None] - xs[None, :]), axis=1)
    band = 0.004 + 0.012 * (1 - np.exp(-(d / 1.1) ** 2))
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    ax.fill_between(x, f(x) - band, f(x) + band, color="#E3E3E3", lw=0)
    ax.plot(x, f(x), color=NAVY, lw=2.4)
    ax.plot(xs, f(xs), "o", color="#404040", ms=8, zorder=3)
    ax.annotate("Monte Carlo로\n수행한 조건", xy=(xs[1], f(xs[1])), xytext=(2.6, 0.506),
                fontsize=10, color="#404040", arrowprops=dict(arrowstyle="->", color="#404040"))
    ax.annotate("수행하지 않은 조건도\n추정 (멀수록 덜 확실)", xy=(5.1, f(5.1) + 0.013), xytext=(4.3, 0.616),
                fontsize=10, color=NAVY, arrowprops=dict(arrowstyle="->", color=NAVY))
    ax.set_xticks([]); ax.set_yticks([]); ax.set_ylim(0.49, 0.64)
    ax.set_xlabel("공정 조건"); ax.set_ylabel("중심치 · 산포")
    concept(ax)
    tf.save(fig, "s6_gp")


def ard_concept():
    """ARD: knob마다 민감도를 따로 학습한다 — 민감한 knob과 둔한 knob (개념도)."""
    x = np.linspace(-1, 1, 200)
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    ax.plot(x, 0.6 + 0.08 * x, color=NAVY, lw=2.6, label="민감한 knob: 조금만 바꿔도 크게 변함")
    ax.plot(x, 0.6 + 0.01 * x, color=GRAY, lw=2.6, label="둔한 knob: 많이 바꿔도 거의 그대로")
    ax.set_xticks([]); ax.set_yticks([]); ax.set_ylim(0.5, 0.7)
    ax.set_xlabel("knob 변화"); ax.set_ylabel("중심치 · 산포")
    ax.legend(loc="upper left", frameon=False, fontsize=9.5)
    concept(ax)
    tf.save(fig, "s6_ard")


def voc_target():
    """VOC: Vmin spec 0.625 V → 목표(논문 시나리오). 막대는 model이 계산한 현재 Read worst · Write worst Vmin."""
    import json
    sm = json.loads((tf.OUT / "lab_summary.json").read_text(encoding="utf-8"))
    t, r, w = sm["target"], sm["baseline"]["read"], sm["baseline"]["write"]
    fig, ax = plt.subplots(figsize=(5.6, 3.9))
    ax.axhline(0.625, color=GRAY, ls="--", lw=1.4)
    ax.axhline(t, color=NAVY, lw=2.4)
    ax.text(3.95, 0.626, "지금 spec 0.625 V", color="#7F7F7F", fontsize=11, va="bottom", ha="right")
    ax.text(3.95, t - 0.001, f"목표 {t:.3f} V\n(−50 mV)", color=NAVY, fontsize=12, va="top", ha="right", weight="bold")
    for x, v, lab, c in ((0.7, r, "Read worst\n(FSG)", NAVY), (1.95, w, "Write worst\n(SFG)", "#8C8C8C")):
        ax.bar(x, v - 0.55, bottom=0.55, width=0.55, color=c, alpha=0.9)
        ax.annotate("", xy=(x + 0.4, t), xytext=(x + 0.4, v), arrowprops=dict(arrowstyle="<->", color=BLACK, lw=1.3))
        ax.text(x + 0.48, (v + t) / 2, f"+{(v - t) * 1e3:.1f}\nmV", fontsize=12, weight="bold", va="center")
    ax.set_xlim(0.2, 4.0); ax.set_ylim(0.55, 0.635)
    ax.set_xticks([0.7, 1.95], ["Read worst\n(FSG)", "Write worst\n(SFG)"], fontsize=11)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Vmin (V)")
    tf.save(fig, "voc_target")

def forward_accuracy():
    """논문 Fig. 3의 발표판: 학습에 없던 조건의 Vmin, model vs Monte Carlo. 판정 가능한 조건만 그린다."""
    fig, axs = plt.subplots(1, 2, figsize=(9.6, 4.6))
    for ax, (f, lab, col) in zip(axs, (("forward_vmin.npz", "read (SNMR, 125 °C)", NAVY),
                                       ("forward_vmin_write.npz", "write (Vtrip, −40 °C)", "#6E6E6E"))):
        z = np.load(HERE.parent / "results" / f)
        t, p = z["vmin_true"], z["vmin_pred"]
        m = np.isfinite(t) & np.isfinite(p) & ~z["censored"]
        rmse = np.sqrt(np.mean((t[m] - p[m]) ** 2)) * 1e3
        lim = (0.38, 0.82)
        ax.fill_between(lim, [lim[0] - 0.01, lim[1] - 0.01], [lim[0] + 0.01, lim[1] + 0.01], color="#E6E6E6", lw=0)
        ax.plot(lim, lim, color="#404040", lw=1)
        ax.plot(t[m], p[m], "o", ms=3.5, color=col, alpha=0.75)
        ax.set_xlim(lim); ax.set_ylim(lim); ax.set_aspect("equal")
        ax.set_title(lab, fontsize=13, weight="bold", color="#1A1A1A")
        ax.text(0.04, 0.95, f"오차 {rmse:.2f} mV\n조건 {m.sum()}개", transform=ax.transAxes, va="top", fontsize=12)
        ax.set_xlabel("기존 Monte Carlo simulation Vmin (V)")
    axs[0].set_ylabel("제안 model Vmin (V)")
    fig.tight_layout()
    tf.save(fig, "forward_accuracy")


if __name__ == "__main__":
    tf.vmin_target(); tf.cell_6t(); tf.mc_vs_corner(); tf.thumbs(); tf.cost_bars()
    margin_sigma(); mu_sigma_to_vmin(); gp_concept(); ard_concept(); forward_accuracy(); voc_target()
    print("saved", tf.OUT)
