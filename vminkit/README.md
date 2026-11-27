# vminkit — 범용 SRAM Vmin 예측 툴

논문에서 검증한 구조(9D 입력 + Vop, exact GP + physics layer)를 노드에 상관없이 쓰도록 만든 툴이다.
설치 없이 `.py` 를 직접 실행한다. Python 3.8 기준.

단계는 자동으로 이어지지 않는다. 각 스크립트가 `work_dir/<단계>/` 에 결과와 리포트를 남기고 멈추면,
리포트를 보고 다음 스크립트를 직접 실행한다.

| 단계 | 스크립트 | 상태 |
| --- | --- | --- |
| 0. 덱 생성 | `00_gen_decks.py` | 완료 |
| 1. 데이터 추출 | `01_extract.py` | 완료 |
| 2. 학습 | `02_train.py` | 예정 |
| 3. 평가 | `03_evaluate.py` | 예정 |
| 4. 활용 (GUI) | `04_studio.py` | 예정 |

## 준비

```bash
python3.8 -m venv .venv && . .venv/bin/activate
pip install -r vminkit/requirements-py38.txt
```

노드마다 `configs/example_node.json` 을 복사해서 `sim_dirs`, 온도, 결과 파일 패턴을 맞춘다.

## 0단계: 시뮬레이션 덱 생성

```bash
python vminkit/00_gen_decks.py --config vminkit/configs/my_node.json --preview   # 바뀌는 줄만 확인
python vminkit/00_gen_decks.py --config vminkit/configs/my_node.json --limit 3   # Vop당 3개 스모크
python vminkit/00_gen_decks.py --config vminkit/configs/my_node.json             # 전체
```

- `template_dir` 에 Vop별 template 덱(예: `02-sp-bc-snmr-TT-1_0.4V-125C.in`)을 둔다.
  `template_glob` 에 `{vop}` 이 없으면 template 하나에서 `.param VOP` 값도 바꾼다.
- 조건은 논문과 같은 방식이다: 9D, 2000 조건, numpy PCG64, (cn, pu) 사분면 가중
  (read 는 FSG, write 는 SFG 쪽을 촘촘히), read seed 2027 / write seed 2028.
  기본값으로 돌리면 논문 조건과 숫자 하나까지 같다. 범위·개수·Vop 는 설정의 `doe` 에서 바꾼다.
  `"method": "sobol"` 로 Sobol 도 쓸 수 있다.
- template 의 `.param VTMSKEW_PU1 = '( A ) + B'` 에서 A 만 바꾸고, 한 파라미터가 정확히 2번
  (인스턴스 1/2) 나오지 않으면 멈춘다.
- 덱 이름은 template 의 `TT-1` 을 `TT-<번호>` 로 바꾼 것. 번호는 Vop 마다 1부터.
- 출력: `deck_out_dir/*.in`, `deck_out_dir/conditions_<mode>.csv`(덱 ↔ 조건표),
  `work/<노드>/00_gen_decks/gen_<mode>.md`(범위, 사분면 비율, 조건 checksum).

덱을 PrimeSim 으로 돌린 뒤, 결과가 있는 폴더를 `sim_dirs` 에 적고 1단계로 간다.

## 1단계: 데이터 추출

```bash
python vminkit/01_extract.py --config vminkit/configs/my_node.json --workers 8
```

- 덱(`*.in`)의 `.param` 에서 VTMSKEW / VTSLSKEW / MOMSKEW (PG·PD·PU), VOP, `.temp` 를 읽어
  논문 9D 축(cn, sk, pu, lpu, l_com, l_sk, mpu, m_com, m_sk)으로 바꾼다.
- read: `{stem}.mt0` 의 MC 표본에서 mu / sigma / median / n.
- write: `{stem}*a0*.mt0` 의 `bwrm_1`(left) 과 `{stem}*a1*.mt0` 의 `bwrm_2`(right) 를 MC index 로 맞춰
  min 을 먼저 취한 뒤 통계를 낸다.
- 줄바꿈된 `.mt0` 도 읽는다 (`core/primesim.py`, 기존 `python/src/primesim_io.py` 와 같은 코드).

결과 (`work/<노드>/01_extract/`):

| 파일 | 내용 |
| --- | --- |
| `dataset_<mode>.csv` | 조건 x Vop 당 한 행, 값은 mV. 2단계 입력 |
| `qc_<mode>.md` | Vop별 요약과 문제 목록. 이걸 보고 다음 단계로 갈지 판단 |
| `qc_issues_<mode>.csv` | 문제 행 전체 (결과 누락, Vop 역전, 온도 불일치, 표본 수 부족 등) |
| `qc_<mode>.png` | mu / sigma / z 분포, Vop 곡선 |
| `samples_<mode>.npz` | `--save-samples` 일 때 덱별 원시 MC 표본 |

QC 는 문제를 표시만 하고 자동으로 고치지 않는다. 이미 결과가 있으면 멈추고, `--force` 를 줘야 덮어쓴다.

## 시험

```bash
python vminkit/tests/test_gen_decks.py  # 논문 조건과 일치, 덱 생성 → 추출까지 이어지는지
python vminkit/tests/test_extract.py    # 가짜 PrimeSim 덱 60개로 끝까지 실행
```
