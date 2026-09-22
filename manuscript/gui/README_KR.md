# SRAM Vmin Inverse Studio — Windows 발표용 로컬 도구

이 폴더는 논문에서 학습한 read/SNMR·write/Vtrip GP surrogate를 사용하여
**순방향 Vmin 예측, one-axis inverse, `cn × pu` 조건부 단면**을 시연하는
Windows 발표용 도구입니다.

## 발표자가 먼저 알아야 할 한 문장

이 도구의 inverse 결과는 **나머지 8개 축을 고정했을 때 선택한 한 축이
목표 Vmin 경계를 만나는 위치**입니다. 9개 물리 원인을 유일하게 추정하거나
final sign-off를 수행하는 기능은 아닙니다.

## 보안·오프라인 동작

- 서버는 `127.0.0.1` / `localhost`에만 bind한다. 외부 IP bind는 코드가 거부한다.
- UI, 모델 bundle, query 결과는 PC 밖으로 전송되지 않는다. CDN·telemetry·cloud API도 없다.
- `demo_bundle/`에는 GP weight뿐 아니라 ExactGP 복원용 학습 좌표/target이 들어갈 수 있다.
  따라서 **PDK/모델 기밀과 동일하게 취급**하고 공유·Git commit·공개 업로드하지 않는다.
- `manuscript/gui/demo_bundle/`, `dist/`, `build/`은 root `.gitignore`에 이미 제외되어 있다.

## 최종 발표 PC에서 실행하기

빌드가 끝난 폴더 전체를 발표 PC로 복사한 뒤 아래 파일을 실행합니다.

```text
SRAM-Vmin-Inverse-Studio/
├─ SRAM-Vmin-Inverse-Studio.exe
├─ static/
├─ demo_bundle/
│  ├─ read_inference_bundle.pt
│  ├─ write_inference_bundle.pt
│  └─ bundle_metadata.json
└─ ... PyTorch/Python runtime files ...
```

1. `SRAM-Vmin-Inverse-Studio.exe`를 더블 클릭한다.
2. 콘솔에 출력되는 `http://127.0.0.1:<port>/`가 기본 브라우저에서 자동으로 열린다.
3. 발표 후 콘솔 창에서 `Ctrl+C`를 눌러 종료한다.

`launch_windows.bat`는 위 실행 파일을 먼저 찾고, 없으면 개발용 Python 실행을 시도하는 편의 launcher다.

## 발표 직전 60초 확인

1. Wi‑Fi를 꺼도 실행되는지 확인한다. (의도적으로 오프라인 동작)
2. `Vmin 예측`을 눌러 read/write 카드가 보이는지 확인한다.
3. read에서 target `0.625 V`, axis `cn`으로 `선택 축 inverse`를 한 번 실행한다.
4. `2D 단면 계산`을 한 번 눌러 warm-up한다.
5. 결과의 `censored`, `no root`, `multiple root`, `외삽` 상태는 오류를 숨긴 것이 아니라
   모델이 보장하지 않는 수치 표시를 피하는 안전 상태임을 확인한다.

## Windows에서 standalone 폴더 만들기

### 준비물

- Windows 10/11 x64
- **빌드용 PC에만** Python 3.11 x64와 인터넷/PyPI 접근 필요
- 이 repository의 `python/requirements.txt`를 설치할 수 있는 환경
- `demo_bundle/` (아래의 trusted bundle 단계에서 준비)

> PyInstaller는 cross-compile을 지원하지 않으므로, Windows 실행 파일은 **Windows에서** build한다.
> Linux에서 만든 PyInstaller 산출물을 Windows PC에 복사하면 안 됩니다.

### 1) 빌드 환경 생성

명령 프롬프트에서 이 폴더(`manuscript\gui`)로 이동합니다.

```bat
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-windows.txt
```

### 2) trusted local inference bundle 준비

이미 `demo_bundle\`이 있다면 이 단계는 건너뜁니다. 원본 protected XLSX와 현재 checkpoint가
동일한 안전한 환경에 있을 때만 실행합니다.

```bat
.venv\Scripts\python prepare_bundle.py --output demo_bundle
```

이 명령은 checkpoint를 바꾸지 않습니다. checkpoint와 원본 training split의 일치를 검증한 뒤,
로컬 실행용 inference bundle을 만듭니다.

### 3) standalone 폴더 build

```bat
build_windows.bat
```

성공하면 `dist\SRAM-Vmin-Inverse-Studio\`를 **폴더 전체로** 발표 PC에 복사합니다.
`--onedir` 방식은 large PyTorch 모델에서 single-exe 압축/임시해제보다 시작과 오류 진단이 안정적입니다.

### 4) build 검증

인터넷을 끈 상태에서:

```bat
dist\SRAM-Vmin-Inverse-Studio\SRAM-Vmin-Inverse-Studio.exe --no-browser
```

출력된 URL을 브라우저에서 열고 다음을 확인합니다.

- Vmin prediction: read/write 카드 둘 다 응답
- inverse: root가 있으면 root+residual, 없으면 `no root` 상태
- plane: `cn × pu` heatmap와 conditional-slice 설명
- sensitivity/scenario: 논문 저장 결과를 설명용으로 표시

## 개발 모드 실행

현재 repository에서 source와 bundle이 준비되어 있다면:

```bat
.venv\Scripts\python demo_server.py
```

기본은 bundle-only이며 protected XLSX를 읽지 않습니다. `--source`는 development-only 옵션입니다.

```bat
.venv\Scripts\python demo_server.py --source
```

## API/모델 동작 개요

| 화면 기능 | 내부 동작 | 발표 시 정확한 해석 |
|---|---|---|
| Vmin 예측 | 9 process 축과 Vop grid에 대해 μ·σ GP를 질의 → `z=μ/σ` → `Vmin` | Gaussian μ/σ 정의의 surrogate point estimate |
| one-axis inverse | selected axis를 scan하여 bracket/monotonicity를 검사한 뒤 bisection | 다른 8축을 고정한 조건부 경계 |
| 2D plane | `cn × pu` grid를 계산 | 나머지 7축이 고정된 2D slice |
| Sobol | 저장된 논문 분석 결과 표시 | uniform training box에서 `z(0.625 V)`의 total-order ST |
| scenario | 저장된 0.575 V 후보값 표시 | DTCO candidate; process cost 최소해/실리콘 증명 아님 |

## 제한사항

- read와 write는 서로 다른 온도·batch에서 학습됐기 때문에 combined 비교는 **설계 탐색용**이다.
- Vmin이 voltage grid 아래/위이면 수치를 꾸며내지 않고 censoring/outside-grid 상태로 표시한다.
- 입력이 training box 밖이면 외삽 warning을 표시한다.
- real PDK compact model, Monte-Carlo, silicon correlation을 대체하지 않는다.
- Windows `.exe` build와 presentation-PC smoke test는 반드시 target Windows 환경에서 수행해야 한다.

## 관련 자료

- 그림별 해설·대본·Q&A: `../presentation/PRESENTATION_GUIDE_KR.md`
- GUI 설계 결정: `../../docs/decisions/2026-09-22_windows_inverse_gui_design.md`
- 논문/결과 해석 및 정정: `../../docs/decisions/2026-09-22_manuscript_explanation_and_demo.md`
