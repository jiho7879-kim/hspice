# Windows 독립 실행 SRAM inverse 시연 GUI — 설계 검토안

## 목표와 상태

2026-09-22 사용자 요청: 현재 논문의 모델로 Windows 발표용 PC에서 독립 실행하는 inverse 중심 GUI와 시나리오 화면/영상 자료. 이 문서는 **2026-09-22 설계 검토 기록**이다. 2026-09-23에 local GUI source, trusted bundle creator, PPTX, Windows PyInstaller build script가 구현되었다. 최신 delivery/검증 상태는 `2026-09-23_presentation_delivery_checkpoint.md`를 기준으로 한다. Windows EXE 생성·실기기 검증은 여전히 target Windows 환경에서 수행해야 한다.

## 접근법 비교

1. **권장: Windows 로컬 계산 엔진 + 브라우저 UI + 사전 계산 재생 모드.** 실제 GP 질의와 발표 안정성을 함께 제공한다. 실행기가 loopback 주소에만 서버를 열고 브라우저를 띄운다. 외부 서비스/CDN·Linux/WSL 서버에 의존하지 않는다.
2. 네이티브 데스크톱 GUI: 서버 없이 가능하지만 발표 그래프·레이아웃·내보내기 작업이 증가한다.
3. 정적 시나리오 viewer: Python 없는 PC에도 간단하게 배포할 수 있으나 임의 inverse를 실시간 계산하지 못한다.

권장안은 1을 주 도구로, 3을 장애 대비 자료로 제공한다. Windows 패키징은 모델·PyTorch 런타임이 커서 단일 EXE보다 실행기와 의존 파일을 포함한 폴더 배포를 우선 검토한다. 현재 Linux 환경에서 Windows 바이너리를 검증했다고 주장하지 않는다. Windows 빌드·실행 검증 전에는 Python 기반 소스 실행과 배포 스크립트만 검증된 상태로 구별한다.

## 화면

- 좌측: 9축(설명·단위·범위), read/write/combined 선택, 모드별 온도, target Vmin, 역산할 축.
- 중앙: 선택 축 sweep, 목표선, 교차점 및 통과 구간. 2D 경계는 명시적 계산 버튼으로 갱신해 슬라이더마다 무거운 GP를 실행하지 않는다.
- 우측: 현재/목표/필요 변화량, binding mode, baseline과 시나리오 비교.
- 하단: 계산 진행·오류·유효범위·Gaussian 가정·모델 버전. 전체화면 발표 모드에서는 작은 내부 디버그 정보만 숨기고 과학적 한계 표기는 유지.

## 기능 범위

1. 현재 저장 모델을 복원한 순방향 예측.
2. 다른 8축을 고정한 1축 inverse: scan으로 구간 확인 후 bracket별 solve. 해 없음·다중 교차·경계 밖·censoring을 별도 상태로 표시. 유일한 물리 원인 복원으로 표시하지 않는다.
3. 논문 시나리오 프리셋: .625→.575 V, NMOS mismatch 감소, PMOS 감소, N/P 분담, corner pull-in. 논문 nominal(모드별 배치 중앙값) 재현과 공통 물리 좌표 질의를 분리한다.
4. 결과 비교 및 설정/결과 JSON·CSV, 발표용 SVG/이미지 내보내기. 원본 데이터나 training labels를 export 결과에 넣지 않는다.
5. 시연 순서 저장·재생과 화면 녹화용 모드. 자동 동영상 파일 인코딩은 Windows 지원 도구 확인 후 별도 추가 가능하며 초기 완료 기준에는 포함하지 않는다. 재생 화면은 saved results라고 명시한다.
6. 기존 global Sobol 표는 “저장된 z at .625 V 분석”으로 표시한다. GUI에서 바꾼 조건의 live local sensitivity인 것처럼 바꾸지 않는다.

## 아키텍처와 보호 경계

계산 코어는 UI와 분리하여 기존 Surrogate.predict_mean/physics layer를 재사용한다. top-level 실행되는 논문 스크립트를 import하지 않는다. 모델은 시작 시 한 번 로드하고 요청을 제한/직렬화한다. GP 초기 로드·대량 grid 비용이 있으므로 응답속도는 실측 후 안내한다.

현재 checkpoint는 exact GP 복원에 training y가 추가로 필요하다. 로컬 준비 단계에서 canonical cleaned loader와 condition split을 사용해 self-contained inference bundle을 만들고, raw XLSX가 없는 독립 디렉터리에서 실행을 확인한다. bundle도 민감한 모델·학습 자산이다. 공개 배포하지 않는다. 임의 모델 업로드·외부 바인딩·외부 telemetry는 지원하지 않는다. 신뢰한 로컬 모델 파일만 로드한다.

추가 패키지는 기존 의존성으로 충족되는지 먼저 검토한다. Windows 패키저 등 신규 의존성이 필요하면 명시하고 결정한다. 패키징 편의 때문에 외부 업로드를 하지 않는다.

## 검증·완료 조건

- 기존 corner baseline 및 scenario 값과 tolerance 내 일치.
- 합성 단조/비단조 함수로 inverse 검사; NaN, invalid range, no root, multiple roots, censoring 테스트.
- JSON 필드·축 순서·단위·모드·training box·target z 일관성 검사.
- real inference smoke test와 UI 상호작용/export 확인.
- 원고·기존 결과·모델 변경 없음.
- Windows 실행 확인은 별도 증거가 있을 때만 완료로 표기. Linux 테스트만 통과한 상태와 구분.

## 제외 범위

9개 미지수의 유일 원인 복원, 9D 전역 최악조건 증명, 실제 제조비용 최적화, 미학습 assist/layout/topology 예측, 실리콘 yield 보장, 실측하지 않은 53배 wall-clock 주장.

## 다음 단계

권장 구조/초기 기능에 대한 사용자 설계 확인 후 구현 계획과 작업으로 진행한다. 설계 근거와 논문 해설: `2026-09-22_manuscript_explanation_and_demo.md`.
