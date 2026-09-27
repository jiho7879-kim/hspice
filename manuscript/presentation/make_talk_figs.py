"""5분 발표용 그림 생성 -> presentation/talk_figs/*.png

실측 데이터 그림: 썸네일 4종(정확도·민감도·역산·비용), Vmin 목표 비교, cost 막대, process plane의 corner 좌표.
개념도(데이터 아님, 그림 안에 '개념도' 표기): 6T 셀 knob 위치, MC vs corner 표본, margin tail, μ·σ → Vmin.
수치 출처: results/*.json, results/*.npz (SRAM_Vmin_IEEE_KR.docx와 같은 값).

usage: .venv/bin/python manuscript/presentation/make_talk_figs.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results"
OUT = HERE / "talk_figs"
OUT.mkdir(exist_ok=True)

NAVY, STEEL, BLUE, BLACK, GRAY, LGRAY = "#1428A0", "#5B728D", "#3E7EDE", "#000000", "#A6A6A6", "#D9D9D9"
WRITE = "#D9772B"

for f in ("/mnt/c/Windows/Fonts/malgun.ttf", "/mnt/c/Windows/Fonts/malgunbd.ttf"):
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams.update({
    "font.family": ["Malgun Gothic", "DejaVu Sans"],
    "axes.unicode_minus": False, "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#7F7F7F", "axes.labelcolor": "#404040", "xtick.color": "#404040", "ytick.color": "#404040",
})
J = lambda name: json.loads((RES / name).read_text())


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=220, bbox_inches="tight", pad_inches=0.04, transparent=False, facecolor="white")
    plt.close(fig)


def concept(ax):
    ax.text(0.99, 0.99, "개념도", transform=ax.transAxes, ha="right", va="top", fontsize=9, color=GRAY)


# ---------------------------------------------------------------- slide 2
def vmin_target():
    sc = J("scenario.json")
    r, w = sc["baseline_vmin"]["read"], sc["baseline_vmin"]["write"]
    fig, ax = plt.subplots(figsize=(5.6, 3.9))
    ax.axhline(0.625, color=GRAY, ls="--", lw=1.4)
    ax.axhline(0.575, color=BLUE, lw=2.4)
    ax.text(3.35, 0.6262, "지금 spec 0.625 V", color="#7F7F7F", fontsize=11, va="bottom", ha="right")
    ax.text(3.35, 0.5738, "새 목표 0.575 V", color=BLUE, fontsize=12, va="top", ha="right", weight="bold")
    for x, v, lab, c in ((0.7, r, "read 한계\n(FSG corner)", NAVY), (1.95, w, "write 한계\n(SFG corner)", WRITE)):
        ax.bar(x, v - 0.55, bottom=0.55, width=0.55, color=c, alpha=0.9)
        ax.annotate("", xy=(x + 0.4, 0.575), xytext=(x + 0.4, v), arrowprops=dict(arrowstyle="<->", color=BLACK, lw=1.3))
        ax.text(x + 0.5, (v + 0.575) / 2, f"+{(v - 0.575) * 1e3:.1f} mV", fontsize=13, weight="bold", va="center")
        ax.text(x, 0.552, lab, ha="center", va="bottom", color="white", fontsize=9.5, weight="bold")
    ax.set_xlim(0.3, 3.4)
    ax.set_ylim(0.55, 0.635)
    ax.set_xticks([])
    ax.set_ylabel("Vmin (V)")
    ax.spines["bottom"].set_visible(False)
    save(fig, "s2_vmin_target")


def cell_6t():
    fig, ax = plt.subplots(figsize=(6.2, 4.3))
    ax.set_xlim(0, 10); ax.set_ylim(0, 7.6); ax.axis("off")
    line = dict(color="#404040", lw=1.6)

    def fet(x, y, name, pmos, w=1.0, h=0.8):
        ec, fc = (BLUE, "#E3ECFB") if pmos else (NAVY, "#E4E7F6")
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.04,rounding_size=0.12",
                                    ec=ec, fc=fc, lw=2))
        ax.text(x, y, name, ha="center", va="center", fontsize=12, weight="bold", color=ec)

    ax.plot([2.9, 7.1], [6.2, 6.2], **line); ax.text(5, 6.35, "VDD", ha="center", fontsize=10, color="#404040")
    ax.plot([2.9, 7.1], [0.8, 0.8], **line); ax.text(5, 0.45, "GND", ha="center", fontsize=10, color="#404040")
    ax.plot([1.0, 9.0], [7.2, 7.2], color=GRAY, lw=1.6); ax.text(9.1, 7.2, "WL", va="center", fontsize=10, color="#7F7F7F")
    for x, lab in ((1.0, "BL"), (9.0, "BLB")):
        ax.plot([x, x], [1.2, 7.2], color=GRAY, lw=1.6); ax.text(x, 0.9, lab, ha="center", fontsize=10, color="#7F7F7F")
    for x in (3.8, 6.2):
        ax.plot([x, x], [6.2, 5.2], **line); ax.plot([x, x], [4.4, 2.6], **line); ax.plot([x, x], [1.8, 0.8], **line)
    fet(3.8, 4.8, "PU", True); fet(6.2, 4.8, "PU", True)
    fet(3.8, 2.2, "PD", False); fet(6.2, 2.2, "PD", False)
    # cross-coupled gates (bus in the middle; crossings without dots are not connected)
    ax.plot([4.55, 4.55], [2.2, 4.8], **line); ax.plot([4.3, 4.55], [4.8, 4.8], **line); ax.plot([4.3, 4.55], [2.2, 2.2], **line)
    ax.plot([5.45, 5.45], [2.2, 4.8], **line); ax.plot([5.45, 5.7], [4.8, 4.8], **line); ax.plot([5.45, 5.7], [2.2, 2.2], **line)
    ax.plot([3.8, 5.45], [3.65, 3.65], **line); ax.plot(3.8, 3.65, "o", color="#404040", ms=5); ax.plot(5.45, 3.65, "o", color="#404040", ms=5)
    ax.plot([4.55, 6.2], [3.35, 3.35], **line); ax.plot(6.2, 3.35, "o", color="#404040", ms=5); ax.plot(4.55, 3.35, "o", color="#404040", ms=5)
    ax.text(3.65, 3.85, "Q", ha="right", fontsize=10); ax.text(6.35, 3.05, "QB", ha="left", fontsize=10)
    # pass gates
    ax.plot([1.0, 1.9], [3.65, 3.65], **line); ax.plot([2.9, 3.8], [3.65, 3.65], **line)
    fet(2.4, 3.65, "PG", False); ax.plot([2.4, 2.4], [4.05, 7.2], color=GRAY, lw=1.4)
    ax.plot([6.2, 7.1], [3.35, 3.35], **line); ax.plot([8.1, 9.0], [3.35, 3.35], **line)
    fet(7.6, 3.35, "PG", False); ax.plot([7.6, 7.6], [3.75, 7.2], color=GRAY, lw=1.4)
    save(fig, "s2_cell6t")


# ---------------------------------------------------------------- slide 3
def mc_vs_corner():
    rng = np.random.default_rng(3)
    fig, ax = plt.subplots(figsize=(5.4, 4.4))
    pts = rng.uniform(-60, 60, size=(1700, 2))
    ax.scatter(pts[:, 0], pts[:, 1], s=4, color=LGRAY, lw=0, label="MC 학습 조건 1,700개 (조건마다 MC 5,000번)")
    for name, (cn, pu) in J("scenario.json")["corner_shifts"].items():
        ax.plot(cn, pu, marker="*", ms=17, color=BLACK)
        ax.text(cn + 4, pu + 3, name, fontsize=11, weight="bold")
    ax.plot([], [], marker="*", ls="", ms=12, color=BLACK, label="PDK corner 4점")
    ax.set_xlim(-65, 65); ax.set_ylim(-65, 72)
    ax.set_xlabel("ΔVth,N  NMOS Vth shift (mV)"); ax.set_ylabel("ΔVth,P  PMOS Vth shift (mV)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), frameon=False, fontsize=10, ncol=1)
    ax.text(0, 64, "9개 축 중 2개만 그림 — 나머지 7개 축은 corner에 없다", ha="center", fontsize=10, color=STEEL)
    save(fig, "s3_plane")


def margin_tail():
    x = np.linspace(-0.08, 0.26, 700)
    pdf = lambda m, s: np.exp(-0.5 * ((x - m) / s) ** 2) / (s * np.sqrt(2 * np.pi))
    m, s1, s2 = 0.12, 0.02, 0.058
    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    ax.plot(x, pdf(m, s1), color=GRAY, lw=2.4, label="corner가 보는 분포 (σ 작음)")
    y2 = pdf(m, s2)
    ax.plot(x, y2, color=NAVY, lw=2.4, label="local mismatch를 더한 분포 (σ 큼)")
    fail = x <= 0
    ax.fill_between(x[fail], 0, y2[fail], color="#C0392B", alpha=0.45)
    ax.axvline(0, color=BLACK, lw=1.2)
    ax.text(-0.004, 21, "fail ←", ha="right", fontsize=11, color="#C0392B", weight="bold")
    ax.text(0.004, 21, "→ pass", ha="left", fontsize=11, color="#404040")
    ax.annotate("평균 μ는 같다", xy=(m, 20.2), xytext=(m + 0.035, 19), fontsize=11,
                arrowprops=dict(arrowstyle="->", color="#404040"))
    ax.annotate("σ가 커지면\ntail이 0을 넘는다\n→ Vmin ↑", xy=(-0.02, 0.5), xytext=(0.006, 11.5),
                fontsize=11, color="#C0392B", weight="bold", arrowprops=dict(arrowstyle="->", color="#C0392B"))
    ax.set_yticks([]); ax.set_ylim(0, 22.5); ax.set_xlim(-0.08, 0.24)
    ax.set_xlabel("noise margin (V)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False, fontsize=10)
    concept(ax)
    save(fig, "s3_tail")


# ---------------------------------------------------------------- slide 5
def mu_sigma_to_vmin():
    v = np.linspace(0.4, 0.8, 200)
    mu = 0.26 * (v - 0.33)
    sig = 0.012 + 0.004 * (v - 0.4)
    k = 6.4
    vmin = v[np.argmin(np.abs(mu - k * sig))]
    fig, ax = plt.subplots(figsize=(6.2, 3.9))
    ax.fill_between(v, mu - k * sig, mu + k * sig, color=BLUE, alpha=0.13, label="μ ± k·σ  (GP ②: σ)")
    ax.plot(v, mu, color=NAVY, lw=2.6, label="margin 평균 μ  (GP ①)")
    ax.plot(v, mu - k * sig, color=BLUE, lw=2, ls="--", label="μ − k·σ  (tail)")
    ax.axhline(0, color=BLACK, lw=1)
    ax.axvline(vmin, color="#C0392B", lw=1.6)
    ax.plot(vmin, 0, "o", color="#C0392B", ms=8)
    ax.annotate(f"Vmin\nμ − k·σ = 0이 되는\n가장 낮은 VDD", xy=(vmin, 0), xytext=(vmin + 0.07, -0.045),
                fontsize=11, color="#C0392B", weight="bold", arrowprops=dict(arrowstyle="->", color="#C0392B"))
    ax.set_xlabel("공급 전압 VDD (V)"); ax.set_ylabel("noise margin (V)")
    ax.set_xticks([0.4, 0.5, 0.6, 0.7, 0.8]); ax.set_yticks([0])
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    concept(ax)
    save(fig, "s5_mu_sigma")


# ---------------------------------------------------------------- thumbnails (slides 4 & 10)
def thumbs():
    kw = dict(figsize=(3.6, 2.5))
    d = np.load(RES / "forward_vmin.npz"); ok = ~d["censored"].astype(bool)
    fig, ax = plt.subplots(**kw)
    ax.plot([0.4, 0.8], [0.4, 0.8], color=BLACK, lw=1)
    ax.scatter(d["vmin_true"][ok], d["vmin_pred"][ok], s=7, color=NAVY, alpha=0.7, lw=0)
    ax.set_xlabel("HSPICE MC Vmin (V)", fontsize=9); ax.set_ylabel("surrogate (V)", fontsize=9)
    ax.tick_params(labelsize=8); ax.set_xticks([0.4, 0.6, 0.8]); ax.set_yticks([0.4, 0.6, 0.8])
    save(fig, "t1_accuracy")

    st = J("sensitivity.json")["sobol"]["ST"]["z(0.625V)"]
    names = [("cn", "ΔVth,N", True), ("l_com", "kσN", False), ("pu", "ΔVth,P", True), ("sk", "skew", False), ("lpu", "kσP", False)]
    fig, ax = plt.subplots(**kw)
    vals = [st[k] for k, _, _ in names]
    ax.barh(range(5)[::-1], vals, color=[GRAY if c else STEEL for *_, c in names], height=0.65)
    ax.set_yticks(range(5)[::-1], [n for _, n, _ in names], fontsize=9); ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    for i, val in zip(range(5)[::-1], vals):
        ax.text(val + 0.01, i, f"{val:.2f}", va="center", fontsize=8.5)
    ax.set_xlim(0, 0.5)
    save(fig, "t2_sobol")

    b = np.load(RES / "inverse_boundary.npz")
    fig, ax = plt.subplots(**kw)
    vm = np.ma.masked_invalid(np.ma.masked_where(b["censored"].astype(bool), b["vmin"]))  # vmin[pu, cn]
    cs = ax.contourf(b["cn"], b["pu"], vm, levels=14, cmap="RdYlBu_r")
    ax.contour(b["cn"], b["pu"], vm, levels=[float(b["v_t0"])], colors=BLACK, linewidths=1.8)
    ax.set_xlabel("ΔVth,N (mV)", fontsize=9); ax.set_ylabel("ΔVth,P (mV)", fontsize=9); ax.tick_params(labelsize=8)
    ax.text(-55, 45, "목표 경계", fontsize=9, weight="bold")
    save(fig, "t3_inverse")

    fig, ax = plt.subplots(**kw)
    ax.bar([0, 1], [42.5, 0.8], color=[GRAY, BLACK], width=0.55)
    ax.set_xticks([0, 1], ["기준 학습", "줄인 학습"], fontsize=9); ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.text(0, 43.5, "4,250만", ha="center", fontsize=9); ax.text(1, 2.0, "80만", ha="center", fontsize=9)
    ax.set_ylabel("총 MC 표본", fontsize=9); ax.set_ylim(0, 50)
    save(fig, "t4_cost")


# ---------------------------------------------------------------- slide 9
def cost_bars():
    r, w = J("cost_combined_c400_mc500.json"), J("cost_combined_write_c400_mc500.json")
    fr, fw = J("forward.json"), J("forward_write.json")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 4.0), gridspec_kw=dict(width_ratios=[1, 1.25], wspace=0.35))
    a1.bar([0, 1], [1700 * 5 * 5000 / 1e4, 400 * 4 * 500 / 1e4], color=[GRAY, BLACK], width=0.55)
    a1.set_xticks([0, 1], ["기준 학습\n1,700 × 5 × 5,000", "줄인 학습\n400 × 4 × 500"], fontsize=10)
    a1.set_yticks([]); a1.spines["left"].set_visible(False)
    a1.text(0, 4400, "4,250만", ha="center", fontsize=12, weight="bold"); a1.text(1, 260, "80만", ha="center", fontsize=12, weight="bold")
    a1.set_title("총 MC 표본 (조건 × VDD × MC)", fontsize=12, loc="left")
    a1.annotate(f"{r['speedup']:.0f}× ↓", xy=(1, 400), xytext=(0.55, 2600), fontsize=18, weight="bold",
                arrowprops=dict(arrowstyle="->", color=BLACK, lw=1.5))
    a1.set_ylim(0, 4900)
    base = [fr["vmin_rmse_mV_holdout"], fw["vmin_rmse_mV_holdout"]]
    red = [r["combined_on_full"]["vmin_rmse_mV"], w["combined_on_full"]["vmin_rmse_mV"]]
    x = np.array([0, 1.1])
    a2.bar(x - 0.2, base, width=0.38, color=GRAY, label="기준 학습")
    a2.bar(x + 0.2, red, width=0.38, color=BLACK, label="줄인 학습")
    for xi, b0, b1 in zip(x, base, red):
        a2.text(xi - 0.2, b0 + 0.15, f"{b0:.2f}", ha="center", fontsize=10)
        a2.text(xi + 0.2, b1 + 0.15, f"{b1:.2f}", ha="center", fontsize=10, weight="bold")
        a2.text(xi, max(b0, b1) + 1.3, f"+{b1 - b0:.1f} mV", ha="center", fontsize=12, weight="bold", color="#C0392B")
    a2.set_xticks(x, [f"read ({r['speedup']:.0f}× 절감)", f"write ({w['speedup']:.1f}× 절감)"], fontsize=10)
    a2.set_yticks([]); a2.spines["left"].set_visible(False); a2.set_ylim(0, 12)
    a2.set_title("hold-out Vmin RMSE (mV)", fontsize=12, loc="left")
    a2.legend(frameon=False, fontsize=10, loc="upper left")
    save(fig, "s9_cost")


if __name__ == "__main__":
    vmin_target(); cell_6t(); mc_vs_corner(); margin_tail(); mu_sigma_to_vmin(); thumbs(); cost_bars()
    print("figures ->", OUT)
