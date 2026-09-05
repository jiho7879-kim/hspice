# manuscript/ — 본논문 작업 폴더

**여기부터 읽으세요.** 오랜만에 돌아왔다면 이 파일 → `DECISIONS.md` → `LEDGER.md` 순서.

---

## 이 폴더가 존재하는 이유

`papers/paper_kr_v3_verified.md`는 결과가 나올 때마다 갖다 붙여서 흐름이 끊겼다.
이 폴더는 **논문에 실제로 들어가는 것만** 모아 하나의 서사로 다시 쓰는 공간이다.

원칙 3가지:

1. **숫자는 반드시 출처가 있다.** 논문의 모든 수치는 `LEDGER.md`에서
   `스크립트 → 데이터 → 출력파일` 로 추적된다. 추적 안 되는 숫자는 논문에 못 들어간다.
2. **한 결과 = 한 스크립트.** 재유도할 때마다 `code/`에 스크립트 하나가 들어오고,
   `LEDGER.md`에 줄 하나가 추가된다. 점진적으로 채운다.
3. **`python/`은 아카이브다.** 여기서 `python/src`를 임포트하고 `python/data`를
   읽지만, 새 코드는 전부 `manuscript/code/`에 쓴다. 복사본을 만들지 않는다.

---

## 서사 축 (2026-08-30 확정)

**"9차원 공정 윈도우 전 구간에서의 순·역방향 SRAM Vmin 추정"** — surrogate 방법론이 축.
IEEE 9장 구조 유지. tail 보정은 §II-D(문제 제기) / §V-F(측정)에 배치하되
헤드라인이 아니라 *방법의 정확도를 담보하는 근거*로 쓴다.

```
I.   서론              — 코너 sign-off의 한계
II.  문제 정식화        — Vmin 정의, 양측 censoring, D: z-score 편향
III. 실험 설계          — 9D 입력, common-skew, quadrant 가중, mirror-twin
IV.  Surrogate 모델     — GP + 미분가능 physics layer + noise-aware
V.   검증              — B 순방향 Vmin / D 코너검증 / E 역추정 / F lobe / G 외부검증
VI.  비용 절감          — 전압레벨 × 조건수 × MC표본
VII. 민감도            — ARD / Sobol / skew 허용폭
VIII.논의와 한계
IX.  결론
```

### 대안 구조 B (2026-09-05) — `paper_*_B.md`

같은 근거를 **순방향·역방향 두 산출물**을 축으로 재배치한 판. 중심 메시지는 초록논문과
같다 — surrogate가 시뮬레이션 수준으로 정확하고, 역방향 추정까지 된다. 나머지(민감도,
지표 편향, 예산)는 그게 되기 때문에 얻어지는 것으로 배치한다. v4.0(`paper_kr.md`·
`paper_en.md`)은 그대로 둔다. 수치는 한 개도 다르지 않고 장 구성만 다르다.

```
I.   서론 — MC 비용 / 코너 한계 → 대체 수단의 3요건(정확도·커버리지·가역성)
II.  문제 정식화 — Vmin 정의(= physics layer 전부) + 지표 편향 문제 제기
III. Surrogate 파이프라인 — 데이터·설계·GP·physics layer·축별 역해
IV.  순방향 정확도 — 3층위(8.35 / 9.3 / 4.26 mV) + 2차식 대조 + σ 병목
V.   역방향 질의와 설계 경계 — 좌표 복원 2.6/3.2 mV, 경계 858 vs 격자 4,900회
VI.  전 구간 민감도 — NMOS local-σ > PMOS Vth, 코너 밖 39 %+
VII. Min-statistics 편향과 저비용 진단 — ρ_LR = −0.371 → 70 mV
VIII.시뮬레이션 예산 — 53배 절감의 대가 +2.6 mV
IX.  논의와 한계
X.   결론
```

v4.0 대비 핵심 차이: 역방향이 §V-E 소절 하나에서 **독립 장(V)**으로 올라왔고, §V(검증)에
7개 소절로 뭉쳐 있던 것을 순방향(IV)·역방향(V)·민감도(VI)·지표 편향(VII)으로 갈랐다.
§I-B에 "대체 수단이 갖춰야 할 3요건"을 넣어 physics layer가 학습되지 않는 이유를 가역성에서
끌어냈다. 표 20개(v4.0은 19개), 그림 1~5는 번호 유지·6~9만 순서 교체(매핑은 파일 머리말).

**제출한 초록과 어긋나는 지점 3건** (본문은 근거 추적되는 현재 값을 씀):

| 초록 | 현재 원고 | 사유 |
|---|---|---|
| Vmin RMSE 9.14 mV | 8.35 mV(전체) / 7.67 mV(사양 밴드) | 9.14는 v3 초고의 QC 이전 사양구간 값 |
| R² > 0.98 | μ 0.9965/0.9989, σ 0.9798/**0.7318** | 쓰기 σ는 0.73이라 일괄 주장 불가 |
| gradient descent로 경계 식별 | 축별 1차원 이분 탐색 | D-06에서 gradient 주장 폐기 |

세 번째는 *실질*은 살아 있다 — 격자 탐색을 우회해 경계를 직접 얻는다는 주장은 그대로이고,
858 vs 4,900회로 정량화된다. 기법만 bisection이다.

QC는 두 스크립트에 `QC_KR`/`QC_EN` 환경변수로 대상을 지정한다:

```bash
QC_KR=paper_kr_B.md QC_EN=paper_en_B.md .venv/bin/python manuscript/code/qc_numbers.py
QC_KR=paper_kr_B.md QC_EN=paper_en_B.md .venv/bin/python manuscript/code/qc_parity.py
```

둘 다 통과 확인 (수치 68개 · 15개 장, 실패 0). 미지정 시 기본값은 v4.0이다.

---

## 진행 현황판

| 단계 | 상태 | 산출물 |
|---|---|---|
| 환경 재구축 | ✅ 2026-08-30 | `.venv` (py3.11.15, torch 2.13.0+cpu, gpytorch 1.15.2) |
| 저장소 PRIVATE 전환 | ✅ 2026-08-30 | fork 0건 확인 |
| Z_target 확정 | ✅ 2026-08-30 | 6.398 — `DECISIONS.md` D-01 |
| zbias @ Z=6.398 재산출 | ✅ 2026-08-30 | ρ_LR = −0.371 → zbias **+1.054** (단일 스칼라) — D-07 |
| 실측 QC 단조성 감사 | ✅ 2026-08-30 | 읽기 31건 + 쓰기 12건 정정, 잔여 위반 0 — `src/final_data.py` |
| §V-B 순방향 정확도 (읽기·쓰기) | ✅ 2026-08-30 | `results/forward[_write].json` · 초안 `draft/v_b.md` |
| §V-D 코너 검증 (읽기·쓰기) | ✅ 2026-08-30 | `results/corner[_write].json` · 초안 `draft/v_d.md` (D-05) |
| §V-E 역추정 | ✅ 2026-08-30 | `results/inverse.json` · 초안 `draft/v_e.md` |
| §IV-F 역추정 해법 (축소) | ✅ 2026-08-30 | 초안 `draft/iv_f.md` — D-06, gradient 주장 폐기 |
| §V-F lobe 측정 | ✅ 2026-08-30 | `results/lobe.json` · 초안 `draft/v_f.md` — D-07, D-08 |
| §V-G 외부검증 (읽기·쓰기) | ✅ 2026-08-30 | `results/external[_write].json` · 초안 `draft/v_g.md` — D-09, D-10 |
| §VI 비용 절감 | ✅ 2026-08-30 | `results/cost_*.json` · 초안 `draft/vi.md` |
| §VII 민감도 | ✅ 2026-09-05 | `results/sensitivity[_write].json` — N070–N072 |
| Fig. 1–9 | ✅ 2026-09-05 | `code/gen_figures.py` → `figures/fig1–9` |
| 본문 조립 (KR·EN) | ✅ 2026-09-05 | `paper_kr.md` · `paper_en.md` — 9장 전부 |
| QC 라운드 1 (수치 정합) | ✅ 2026-09-05 | `code/qc_numbers.py` — 50개 수치, 실패 0 |
| QC 라운드 2 (한/영 대조) | ✅ 2026-09-05 | `code/qc_parity.py` — 14개 장, 실패 0 |
| QC 라운드 3 (원고 규범·인용) | ✅ 2026-09-05 | 반영 내역 `DECISIONS.md` D-11 · 형식 D-12 · 어휘 D-13 |
| QC 라운드 4 (논리·서사) | ✅ 2026-09-05 | 반영 내역 `DECISIONS.md` D-11, 잔여 실험은 O-09 |
| 참고문헌 검증·재번호 | ✅ 2026-09-05 | Crossref 대조 (O-02·O-03 종결) + 인용 순서로 재번호 — `code/renumber_refs.py`에 구↔신 매핑 |
| 제목·저자·소속·투고처 | ⬜ | O-01 · O-05 — **사용자 결정 필요** |
| IEEE 형식 일괄 정리 | ✅ 2026-09-05 | `DECISIONS.md` D-12 — 참고문헌 재번호·표/그림 인용·초록 247단어·기호 충돌 해소 |
| 참조 시뮬레이션 어휘 통일 | ✅ 2026-09-05 | `DECISIONS.md` D-13 — 실리콘이 없으므로 "measured/실측"을 기준값에 쓰지 않는다 |
| 추가 실험 (O-09) | 🔄 2026-09-05 | (a) 복원 라벨 ✅ (b) 2차식 기준선 ✅ — D-14 · (c) §VI-B draw 2·3 실행 중 |

---

## `draft/`는 §VI에서 멈춘다

§VII부터는 초안 파일을 만들지 않고 `paper_kr.md`·`paper_en.md`에 직접 쓴다. 본문이
조립된 뒤로는 초안이 사본일 뿐이고, 사본은 어긋난다. `draft/*.md`는 조립 이전 기록으로
남겨 둔다.

## QC — 고치면 반드시 다시 돌린다

```bash
.venv/bin/python manuscript/code/qc_numbers.py   # 논문 수치 ↔ results/*.json
.venv/bin/python manuscript/code/qc_parity.py    # 국문판 ↔ 영문판
```

`qc_numbers`는 헤드라인 수치가 (a) `results/`의 값과 자릿수까지 맞는지 (b) 두 언어판에
모두 나오는지를 본다. `qc_parity`는 장별로 숫자 집합·표·그림·인용·인용블록 수를 맞춘다.
둘 다 실패하면 0이 아닌 코드로 죽는다. 논문을 고쳤으면 커밋 전에 둘 다 통과시킨다.

## 실행 방법

```bash
cd /home/jiho7879-kim/hspice
.venv/bin/python manuscript/code/<script>.py
```

모든 `code/` 스크립트는 첫 줄에서 `_paths.py`를 임포트해 `python/`을 경로에 넣는다.
데이터·라이브러리 위치를 스크립트마다 다시 쓰지 않는다.

---

## 데이터 파일

`final*` 이름의 파일이 **최종 raw**이고 나머지는 전부 과정 파일이다. 측정값이 실제로
들어 있는 파일은 6개뿐이며 목록과 지위는 `DECISIONS.md` **D-10**에 있다.
`final_2000_seed2026.xlsx` 등은 값이 0건인 빈 요청 시트다 — 데이터로 착각하지 말 것.

---

## 절대 하면 안 되는 것

- `python/data/*.xlsx`를 이 폴더로 복사하기 — 사내 실측 데이터, 사본을 늘리지 않는다.
- 저장소를 다시 public으로 돌리기 — `.gitignore`가 실측 데이터를 배제하지 못한다.
- `LEDGER.md`에 없는 숫자를 논문에 쓰기.
