# Session Summary — 2026-07-01

## 진행 내용

### 1. 현황 리뷰
- **Toy project**: GP surrogate + additive kernel (Vop⊕cn,pu) + differentiable physics layer → Vmin estimation
  - Vmin RMSE ≈ 5.7mV (toy analytic model)
  - Standard GP 대비 sigma error variance 8x 개선
  - Contour extraction (Vmin=0.6V boundary), diagnostic plots, gradient check 모두 정상 동작
- **SKY130 PDK**: real silicon parameter로 calibration 완료, contour plot 생성
- **현재 상태**: Method validation은 완료, real HSPICE data만 있으면 바로 적용 가능

### 2. 논문 가능성 검토
| 요소 | 판단 |
|------|------|
| Additive kernel for sigma | ⭐⭐⭐ — SRAM context에서 Vop-corner separability를 kernel로 encode |
| Differentiable physics layer | ⭐⭐⭐ — z-score → Vmin 미분가능 → gradient-based inverse design 가능 |
| Pred-true gap 진단 framework | ⭐⭐ — mu vs sigma, Vop별, quadrant별 error 추적 |
| Inverse Vmin contour extraction | ⭐⭐⭐⭐ — "Vmin=0.6V를 만족하는 margin" industry 문제 직접 해결 |

**Critical path**: HSPICE real data 없이는 논문 판단 불가. Real data 확보 후 baseline 대비 우위 증명 필수.

### 3. 현업 PDK Data Extraction 준비
생성된 파일: **`toy_project/HSPICE_Data_Extraction_Spec.xlsx`** (29.7KB)

| Sheet | 내용 |
|-------|------|
| 개요 및 지침 | 프로젝트 목적, data format, 주의사항 |
| 고정 파라미터 | PDK 설정 13개 항목 (필수/권장 구분) |
| Simulation Matrix | common_N(9)×PU(9)×Vop(6) = 486개 조건, P1/P2/P3 priority |
| 출력 데이터 형식 | Raw + Aggregated format 상세 정의 |
| Hold-out Validation | 16개 holdout 조건 목록 |
| 확장 (선택사항) | Temperature, corner, Read SNM 등 |
| HSPICE Netlist Template | Netlist 구조 예시 |
| 체크리스트 | 추출 전/후 12개 확인 항목 |

## 다음 Step
1. **(User)** 사내망에서 PDK data 추출 (486 conditions × 3,000 MC)
2. **(User)** CSV 결과물을 이 repo로 가져오기
3. **(Sisyphus)** Python loading script → surrogate training on real data → validation → baseline 비교
4. Data가 유의미하면 논문 방향 구체화

## Artifacts Created
- `toy_project/HSPICE_Data_Extraction_Spec.xlsx` — HSPICE data extraction specification
- `toy_project/create_hspice_spec.py` — Excel generation script
