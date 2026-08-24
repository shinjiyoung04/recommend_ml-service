# MeetupLog AI 추천 PPT 데모 안내

이 프로젝트는 강화된 FastAPI ML 서비스의 누적 성향 상태와 React 추천 화면을 연결한 PPT 캡처용 통합본입니다.

## 화면에서 확인할 핵심

- 채팅을 전송하면 오른쪽에 A/B 사용자별 분석 성향과 가중치가 표시됩니다.
- 배우와 감독은 ML 응답의 역할별 필드(`liked_actors`, `liked_directors` 등)를 구분해 표시합니다.
- 추천 직전에 최신 `state_version`을 조회하고 누적 성향 기반 추천 API를 호출합니다.
- TOP 3 카드에는 그룹 매칭 점수와 A/B 개인 적합도가 함께 표시됩니다.
- 오른쪽의 `TOP 1 개인 적합도`는 첫 번째 추천 카드의 A/B 점수와 같은 값입니다.
- `localhost:5173`과 `127.0.0.1:5173` 어느 주소로 실행해도 추천 요청이 허용됩니다.

## 실행 순서

PowerShell 창 세 개에서 프로젝트 루트를 기준으로 각각 실행합니다.

### 1. FastAPI ML 서비스

```powershell
cd ml-service
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m uvicorn meetup_ml.api:app --reload --port 8000
```

### 2. Spring Boot 연동 서버

MySQL의 `lostmatch3_dev` 데이터베이스와 `application.yaml`의 계정 설정을 먼저 확인합니다.

```powershell
cd backend
.\gradlew.bat bootRun
```

### 3. React 화면

```powershell
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 또는 `http://127.0.0.1:5173`을 엽니다.

## PPT 캡처 추천 순서

1. 브라우저를 1920×1080 크기로 맞춥니다.
2. 포함된 `chat-test` 데모 대화를 불러온 뒤 `AI 영화 추천`을 누릅니다.
3. 한 화면에 다음 항목이 보이도록 캡처합니다.
   - 대화에서 반영된 성향 요약 칩
   - TOP 3 영화의 그룹 매칭 점수
   - 각 영화의 A/B 개인 적합도 막대
   - 오른쪽 A/B 분석 성향과 TOP 1 개인 적합도
4. 첫 번째 카드의 `상세보기`를 누르면 추천 이유와 영화 정보를 별도로 캡처할 수 있습니다.

## 처음부터 새 대화로 시연하는 예시

`대화 초기화` 후 다음 순서로 입력하면 장르·소재·배우·OTT·상영시간이 분리되어 표시됩니다.

- A: `잔잔한 영화가 좋아`
- A: `애니메이션과 로맨스는 별로야`
- A: `박지훈 나오는 영화 보고 싶어`
- A: `120분 이하는 좋아`
- B: `긴장감 있는 영화가 좋아`
- B: `황정민 나오는 영화 보고 싶어`
- B: `넷플릭스와 디즈니+ 구독 중이야`
- B: `영화관에서 보고 싶어`
- B: `120분 이상도 좋아`

마지막으로 `AI 영화 추천`을 누르면 오른쪽 누적 성향과 동일한 상태 버전으로 추천 점수가 계산됩니다.

## 검증 결과

- React TypeScript 프로덕션 빌드 통과
- 강화 ML 전체 테스트 67개 통과, 3개 선택적 테스트 제외
- Spring Boot 테스트 통과
- 브라우저에서 채팅 상태 조회 → TOP 3 추천 → A/B 점수 및 오른쪽 성향 표시까지 확인
