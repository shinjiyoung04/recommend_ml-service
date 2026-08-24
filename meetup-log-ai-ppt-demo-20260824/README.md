# MeetupLog 정리본

이 폴더는 원본 `C:\student_sjy\MeetupLog\project2`를 변경하지 않고 만든 실행용 정리본입니다.

## 구성

- `frontend/`: React + Vite, 기본 포트 5173, `/api` 요청을 Spring 8080으로 프록시
- `backend/`: Spring Boot, 기본 포트 8080, FastAPI 8000 호출
- `ml-service/`: FastAPI, 기본 포트 8000, 모델 버전 `semantic-group-hybrid-0.6.0`
- 모델 `semantic-group-hybrid-0.6.0`은 TMDB 배우·감독 ID/원문명 수집, 시계열 분리 평가, 콘텐츠·학습 랭커 결합 추천을 지원합니다.

### 인물 및 기준 영화 추천

- TMDB 수집 시 상위 출연진 20명과 감독 전원을 국적 구분 없이 저장합니다.
- `data/normalized/people.json`에는 인물 ID, 표시명, 원문명, 역할, 출연 영화가 생성됩니다.
- "위대한 쇼맨 같은 영화가 좋아"처럼 말하면 해당 영화를 `liked_movies` 기준 영화로 보존합니다.
- 후보는 장르 30%, 키워드 25%, 출연진·감독 15%, 줄거리 20%, TMDB 유사/추천 관계 10%로 비교합니다.
- 누락된 메타데이터 항목은 분모에서도 제외하며, `score_breakdown`에 항목별 근거를 반환합니다.

### 배우·감독 인물 ID 보강 및 검증

- 선호/비선호는 `liked_actors`, `disliked_actors`, `liked_directors`, `disliked_directors`로 역할을 분리하고 TMDB 인물 ID를 우선 비교합니다.
- 예전 이름 목록(`liked_people`, `disliked_people`)도 호환되지만, 이름이 같아도 역할 또는 TMDB ID가 다르면 같은 인물로 처리하지 않습니다.
- 기존 `movies.json`에 인물 ID가 없다면 TMDB 인증값을 `.env`에 설정한 뒤 아래 명령을 실행합니다. 50편마다 저장하므로 중단 후 같은 명령으로 다시 시작할 수 있습니다.

```powershell
cd ml-service
python -m meetup_ml.cli sync-person-ids --checkpoint-every 50
```

- 동결 카탈로그 기반 배우·감독 점수, 비선호 회피, 문맥 계승, 정확히 3편 출력을 재평가하려면 다음을 실행합니다.

```powershell
python tests/evaluate_role_context_model.py
```

결과는 `ml-service/evaluation/role_context_validation.json`에 저장됩니다. 이 보고서는 TMDB 크레딧 기반 구성요소 검증이며 실제 사용자 수용률을 뜻하지 않습니다.

## 처음 한 번 설치

PowerShell 창을 각각 열어 아래를 실행합니다.

### ML

```powershell
cd ml-service
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m uvicorn meetup_ml.api:app --reload --port 8000
```

이미 설치를 마친 기존 복사본에서 `No module named 'rapidfuzz'`가 나온다면 한 번만 실행하세요.

```powershell
python -m pip install rapidfuzz
```

### Backend

```powershell
cd backend
.\gradlew.bat bootRun
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173`을 엽니다.

## 연결 확인

- ML: `http://localhost:8000/health`
- Spring → ML: `http://localhost:8080/api/v1/recommendations/health`
- 평가: `http://localhost:8080/api/v1/recommendations/evaluation`

비밀값이 필요한 경우 각 `.env.example`을 참고해 로컬 `.env`를 새로 만드세요. 실제 `.env`는 ZIP에 포함하지 않았습니다.
