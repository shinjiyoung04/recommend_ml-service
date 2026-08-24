# ML 파이프라인 보완 결과

## 완료

- 사전 계산 SBERT: `movie_embeddings.npy`/메타/manifest의 ID 순서, 모델명, 행렬 크기, SHA-256을 검증해 추천 엔진이 직접 사용한다. 5,000개 고정 카탈로그 이후 추가 영화만 로컬 인코더로 계산한다.
- 대화: 한 발화의 복수 OTT를 모두 저장하고, `나도`가 직전 발화의 복수 장르·브랜드·OTT 효과 전체를 계승한다.
- 비교·부정: `2시간 이상은 싫어`를 `min_runtime=120`이 아니라 `max_runtime=120`으로 해석한다.
- 골든셋: `data/golden/chat_golden_500.jsonl`에 500발화, 시간순 350/75/75 분할, 출처·대화 ID·시각을 저장했다. 원본 실사용 로그가 ZIP에 없으므로 출처는 정직하게 `curated_conversation_v2`이다.
- 그룹 평가: 40개 시나리오와 실행 결과를 저장했다. HitRate@3=1.0, AcceptanceRate@3=0.8333.
- 모델 배포: 후보 저장 → 재로드 검증 → 원자적 current 교체 → 실패 시 previous 복원 순서이며 성공 즉시 메모리 모델도 교체한다.
- 무결성: 카탈로그 ID 순서, 선택 필드 내용 SHA-256, 임베딩 SHA-256 기반 모델 artifact revision을 고정했다.
- 다중 엔티티: 복수 엔티티 및 계승 회귀 테스트를 포함했다.
- 시간 분할: 추천 relation은 개봉일 cutoff, 500발화 골든셋은 `created_at` 순서로 분할한다.

## 검증

- 자동 테스트: 29 passed, 3 skipped. skip은 인증정보가 필요한 수동 TMDB smoke script 2개와 의도적으로 카탈로그를 변경하는 수동 script 1개다.
- Spring backend: `gradlew.bat test` 통과.
- Frontend: 압축본에 `node_modules`가 없어 빌드는 실행하지 않았으며, `npm ci` 후 재현 가능하다.
- 평가 결과: `ml-service/evaluation/group_scenarios_40.json`

## P2 상태

LTR 데이터셋 생성·라벨 우선순위·요약 테스트는 준비되어 있다. 실제 LTR 학습과 A/B 라우팅은 충분한 운영 피드백과 실험 단위/중단 기준이 없으므로 활성화하지 않았다. 이는 P0/P1 이후의 안전한 준비 상태이며, 임의의 합성 데이터로 운영 모델을 승격하지 않는다.

## 남은 외부 입력

실제 사용자 대화 500발화를 법적·개인정보 검토 후 제공하면 현재 JSONL 스키마로 교체하고 동일한 시간순 평가를 수행해야 한다. 현재 ZIP만으로는 이 항목을 “실제 로그 완료”라고 주장할 수 없다.
