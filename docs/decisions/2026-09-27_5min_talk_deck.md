# 5분 구두 발표 자료 (한국어) 결정 기록

작성: 2026-09-27 · 산출물: `manuscript/presentation/SRAM_Vmin_5min_KR.{pptx,pdf}`, `SCRIPT_5min_KR.md`

## 재생성

```bash
.venv/bin/python manuscript/presentation/make_talk_figs.py   # talk_figs/*.png
.venv/bin/python manuscript/presentation/make_talk_5min.py   # pptx + 노트 대본 + SCRIPT md
```

PDF는 Windows PowerPoint COM으로 내보냈다(LibreOffice 없음). 캔버스는 항상 Widescreen 13.333×7.5 in.

## 결정

- **수치 출처**: `SRAM_Vmin_IEEE_KR.docx`와 같은 `results/*.json`. `paper_*.md`는 D-16 이전 수치라 쓰지 않는다.
- **흐름 (10장)**: 고객 VOC 사례 → 기존 방법(MC vs corner) → 네 질문(정확도·민감도·역산·비용) → 구현 → 네 답 → 정리. 사용자가 "VOC에서 어떤 공정 action이 효과적인지 탐색하는 데 유용했다"를 강조하길 원해, 8장을 VOC의 답(NMOS local-σ −10.9 %)으로 제목을 달았다.
- **디자인**: 전역 스킬 `slide-design-patterns` Preset A. 네 질문에 색(navy/steel/blue/black)을 고정해 뒤 장표의 범례로 쓴다.
- **성능 수치 없음**: VOC의 "성능 개선"은 요구로만 적었다. 논문에 성능 결과가 없으므로 새 숫자를 만들지 않았다. mobility 축 ST ≤ 0.015는 Sobol 결과 그대로다.
- **9개 축 설명**: 논문 본문의 "gate length, oxide thickness"와 Table V의 "N/P threshold skew"는 실제 입력과 어긋난다. 발표는 코드 기준(Vth shift / local-σ / mobility × NMOS 공통·PG–PD skew·PMOS)을 따랐다. **논문 문구 정정이 남아 있다.**
- **그림**: 실측 그림(썸네일, Vmin gap, cost)과 개념도(margin tail, μ·σ→Vmin, 6T knob map)를 구분하고, 개념도에는 그림 안에 "개념도"를 표기했다. 3장 산점도는 조건 분포 예시임을 각주에 적었다.

## 시행착오

- PowerPoint는 한글을 글자 단위로 줄바꿈한다 → 카드·결론 문구는 줄을 명시적으로 나눴다.
- 번역투 지적 → "~에 대해/~를 통해/~라는 점" 류와 명사화를 걷어내고 구어 종결로 대본을 다시 썼다.
- `inverse_boundary.npz`의 `vmin`은 `[pu, cn]` 순서다(전치하면 경계가 뒤집힌다).
