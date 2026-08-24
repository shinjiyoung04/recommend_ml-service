# Windows CMD 재현 명령

프로젝트 루트에서 실행한다.

```bat
cd ml-service
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
```

평가 자산을 다시 생성하고 40개 그룹 평가를 저장한다.

```bat
.venv\Scripts\python.exe tests\build_golden_chat_500.py
.venv\Scripts\python.exe tests\freeze_catalog.py
.venv\Scripts\python.exe tests\build_group_scenarios.py
.venv\Scripts\python.exe tests\evaluate_group_scenarios.py
```

SBERT 질의 인코더까지 사용하려면 로컬/온라인 설치 단계에서 embedding extra를 설치한다. 모델은 서비스 요청 중 다운로드하지 않으며 로컬 캐시에 없으면 TF-IDF로 안전하게 대체된다.

```bat
.venv\Scripts\python.exe -m pip install -e ".[embedding,dev]"
```

서비스 실행:

```bat
.venv\Scripts\python.exe -m uvicorn meetup_ml.api:app --host 127.0.0.1 --port 8000
```

별도 CMD 창에서 backend와 frontend를 실행한다.

```bat
cd backend
gradlew.bat test
gradlew.bat bootRun
```

```bat
cd frontend
npm ci
npm run build
npm run dev
```
