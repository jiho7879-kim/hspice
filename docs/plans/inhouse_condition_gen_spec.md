# In-house Condition Generation — Porting Spec

> 목적: 사내에서 deck을 생성하는 python 스크립트에 **조건 생성 로직**을
> 이식하기 위한 명세. 사내 code assist에게 이 문서 + `src/condition_gen.py`를
> 주면 됨.
> 핵심 목표: 사내 deck 생성이 만드는 조건 = 우리 로컬 재생성 조건이 **완전히
> 동일**하도록 만들기 → 사용자는 조건을 손 전사할 필요 없이 **결과만** 적어옴.

---

## 0. 왜 이게 필요한가

- deck(.in)·결과(.mt0) 모두 사내 반출 불가.
- 조건(cn, pu, skew, loc, mom)은 사내 deck 생성 시 python이 뽑는데, Sobol/
  random이면 값이 매번 달라 보임 → 우리가 미리 알 수 없다고 착각하기 쉬움.
- **그러나 seed를 고정하면 조건은 deterministic**(재현 가능). 사내와 우리가
  **같은 로직·같은 seed**를 쓰면 조건이 byte-identical → 조건 전사 불필요.
- 그래서 우리 전체 `gen_hspice.py`를 사내에서 돌릴 필요 없이(경로·파일명·
  flow 차이로 디버깅 과다), **조건 생성 핵심 함수만** 사내 deck 스크립트에
  이식하면 된다.

## 1. 이식할 것: `src/inhouse_deck_gen.py` 하나 (통짜)

사내에는 **`src/inhouse_deck_gen.py`를 통째로** 준다. 이 파일은:
- **FROZEN CORE** 섹션 (조건 생성 + deck 넘버링): **절대 수정 금지**.
  numpy만 의존 (method="sobol"일 때만 scipy).
- **SITE ADAPTER** 섹션 (deck 템플릿·파일명·경로·시뮬 호출): **환경에 맞게
  자유 수정**.

사내 assist에게 요청할 문장(그대로 써도 됨):
> "이 파일의 FROZEN CORE 함수들(generate_conditions, _unit_samples,
> _quadrant_cnpu, deck_number, iter_decks)은 **한 글자도 바꾸지 말고** 그대로
> 두세요. 파일명·경로·deck 템플릿 렌더링·시뮬레이터 호출만 SITE ADAPTER
> 섹션에서 우리 환경에 맞게 붙이면 됩니다."

핵심 진입점 `iter_decks`가 (Vop, 조건) 순서·넘버링을 고정한다:
```python
for rec in iter_decks(stage="D", n_cond=500, vops=[0.4,0.5,0.6,0.7,0.8],
                      seed=42, metric="snmr", method="rng",
                      deck_prefix="TT", start=1):
    # rec = {deck_no, deck_id:"TT-<no>", vop, cn, sk, pu, lpu..mpd}
    make_deck(rec)   # ← SITE: 여기만 사내 파일명/경로/템플릿으로 구현
```

(참고: `condition_gen.py`는 우리 로컬에서 시트 생성에 쓰는 동일 코어의 별도
사본. 두 파일의 FROZEN CORE는 byte-identical해야 하며, 교차검증 테스트로
보장한다 — `tests/test_condition_gen.py`.)

## 2. 재현성 계약 (양쪽이 반드시 일치)

조건이 동일하려면 아래가 **모두** 같아야 함:

| 항목 | 값 | 비고 |
|------|-----|------|
| `condition_gen.py` 버전 | `CONDITION_GEN_VERSION` (현재 1.0) | 파일 변경 시 버전 올릴 것 |
| `stage` | A / B / D | |
| `n_cond` | 정수 | |
| `seed` | 정수 | **가장 중요 — 반드시 공유** |
| `metric` | snmr / vtrip | quadrant weight 결정 |
| `method` | **rng** (권장) | rng=numpy PCG64, 버전 간 안정(numpy 문서 보장) |
| numpy 버전 | method=rng이면 사실상 무관 | PCG64 스트림은 numpy가 안정성 보장 |

> **method 선택**: `rng`(numpy PCG64)를 강력 권장. numpy는 PCG64 난수
> 스트림의 버전 간 안정성을 문서로 보장하므로, 사내/우리 numpy 버전이
> 달라도 조건이 동일. `sobol`(scipy)은 space-filling이 약간 낫지만
> scipy 버전에 민감 → 양쪽이 scipy를 pin해야만 안전.

## 3. Deck 넘버링 (TT-N) — 결과 매칭의 핵심

reference deck이 `TT-1`, `TT-2`, ... 처럼 번호를 갖고, **각 Vop마다 TT-1부터
다시 시작**해서 조건 순서대로 1씩 증가한다 (사용자 확정):

```
Vop 0.4V:  TT-1=조건1, TT-2=조건2, ..., TT-N=조건N
Vop 0.5V:  TT-1=조건1, TT-2=조건2, ..., TT-N=조건N   ← 번호 재시작, 같은 조건순서
...
```

`iter_decks`가 정확히 이 순서(outer=Vop, inner=조건index)로 record를 내며
`deck_no = start + 조건index`, `deck_id = f"{prefix}-{deck_no}"`를 부여한다.
따라서 **결과를 (vop, deck_no) 두 값으로만 라벨해도** 조건이 유일하게 역매칭
된다 — 조건 전사 불필요.

> ⚠ 사내 deck 루프도 반드시 `iter_decks` 순서를 그대로 따라야 함
> (outer Vop → inner 조건). SITE ADAPTER의 `make_deck(rec)`가 `rec['deck_id']`
> 로 파일명을 만들면 자동 일치. 순서를 바꾸면 번호↔조건 대응이 깨짐.

**template 파라미터 매핑** (`condition_to_deck_params`가 이미 계산):
```
VTMSKEW_PG1 = VTMSKEW_PG2 = cn + sk      # PG = common_N + skew
VTMSKEW_PD1 = VTMSKEW_PD2 = cn - sk      # PD = common_N - skew
VTMSKEW_PU1 = VTMSKEW_PU2 = pu
VTSLSKEW_PU1/2 = lpu ;  VTSLSKEW_PG1/2 = lpg ;  VTSLSKEW_PD1/2 = lpd
MOMSKEW_PU1/2  = mpu ;  MOMSKEW_PG1/2  = mpg ;  MOMSKEW_PD1/2  = mpd
```
(Stage A: sk=loc=mom 없음, PG=PD=cn. Stage B: loc=mom 없음.)

## 4. 결과 전사 (사용자)

1. 우리가 로컬에서 동일 `generate_conditions(...)` + `gen_condition_sheet.py`로
   **조건이 미리 채워진 xlsx**를 만들어 사용자에게 전달
   (`row_id, cn, sk, pu, lpu..mpd, vop` + 빈 `snmr_avg, snmr_std, n_mc`).
2. 사내에서 **같은 seed로** deck 생성·HSPICE 실행 → .mt0 (반출 불가).
3. 사용자는 그 xlsx의 각 행에 **결과값만** 기입: `snmr_avg`(mV),
   `snmr_std`(mV), `n_mc`(정수).
4. 우리가 `parse_manual_xlsx`로 로드 → 학습. 조건은 이미 채워져 있어 검증만.

> **매칭 안전장치**: `row_id`가 조건표와 deck 루프의 순서를 고정. 사내
> deck 루프도 `conditions_to_records` 순서(조건 i의 Vop 순회)를 따르면
> row_id가 자동 일치. 순서가 다르면 (cn,pu,vop)로 join 가능.

## 5. 정밀도 (condition_gen이 자동 적용)

| 입력 | 정밀도 | 이유 |
|------|--------|------|
| cn, pu, skew | 정수 mV | 반올림 Vmin 오차 ≤0.7mV, 무시 가능 |
| loc, mom | 소수 2자리 | Sobol/rng 해상도와 균형 (0.1 거침, 0.001 과잉) |

deck 생성 시 이 값 그대로 사용(추가 반올림 금지 — 양쪽 불일치 유발).

## 6. 검증 방법 (이식 후 1회)

`condition_gen.py`를 그대로 실행하면 self-test(결정성·정밀도)가 돌고
**고정 기준값**(stage D, **n_cond=16**, seed=42)이 출력됨:
```
$ python condition_gen.py
condition_gen v1.0: self-test OK (deterministic, seed-sensitive, precision correct)
D columns: ['cn', 'sk', 'pu', 'lpu', 'lpg', 'lpd', 'mpu', 'mpg', 'mpd']
D[0]: [-43.  -19.   17.   0.76  1.09  1.28  1.16  1.24  0.84]
```
사내에서 이식한 파일을 같은 방식으로 실행해 **D[0]가 정확히
`[-43, -19, 17, 0.76, 1.09, 1.28, 1.16, 1.24, 0.84]`이면 이식 성공.**

> ⚠ **n_cond도 재현성 계약 항목**: quadrant 분배가 n_cond에 따라 달라져,
> **n_cond가 다르면 조건 배열 전체가 달라진다** (예: n=16의 첫 행과 n=500의
> 첫 행은 무관). 실제 배치의 n_cond(예: 500)를 양쪽이 동일하게 써야 함.
> self-test의 n=16은 이식 검증용 고정 기준값일 뿐, 실제 배치 값이 아님.
