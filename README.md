# KOSPI 자동 갱신 대시보드

평일 한국 시간 16:10에 코스피 일별 데이터를 자동 수집하고, SQLite와 JSON에 저장한 뒤 GitHub Pages에 차트를 배포합니다. 생성된 Pages 주소를 Notion의 `/embed` 블록에 한 번 넣으면 됩니다.

## 가장 빠른 설치 방법

1. GitHub에서 `kospi-dashboard`라는 Public 저장소를 만듭니다.
2. 이 폴더 안의 파일과 폴더를 **내용 그대로** 저장소 최상위에 업로드합니다. `kospi-dashboard` 폴더 자체가 한 단계 더 들어가지 않게 주의하세요.
3. GitHub 저장소의 `Settings → Actions → General → Workflow permissions`에서 `Read and write permissions`를 선택하고 저장합니다.
4. `Settings → Pages → Build and deployment → Source`를 `GitHub Actions`로 설정합니다.
5. 저장소의 `Actions` 탭에서 `Update KOSPI dashboard`를 열고 `Run workflow`를 누릅니다.
6. 첫 실행 완료 후 `https://깃허브아이디.github.io/kospi-dashboard/`에 접속합니다.
7. Notion에서 `/embed`를 입력하고 위 주소를 붙여넣습니다.

## 파일 구조

```text
.github/workflows/update.yml   자동 실행 및 Pages 배포
scripts/update_kospi.py        코스피 데이터 수집
data/kospi.db                  첫 실행 때 자동 생성되는 SQLite DB
docs/data/kospi.json           첫 실행 때 자동 생성되는 차트 데이터
docs/index.html                Notion에 임베드할 차트 페이지
requirements.txt               Python 패키지 목록
```

## 실행 시간 변경

`.github/workflows/update.yml`의 cron은 UTC 기준입니다.

```yaml
- cron: "10 7 * * 1-5"
```

이는 월~금 한국 시간 16:10입니다. 장 종료 직후 데이터 반영 지연을 고려해 16:00 대신 16:10으로 설정했습니다. 16:20으로 바꾸려면 `10`을 `20`으로 바꿉니다.

## 로컬 테스트

```bash
python -m venv .venv
pip install -r requirements.txt
python scripts/update_kospi.py
python -m http.server 8000 --directory docs
```

브라우저에서 `http://localhost:8000`을 엽니다. `index.html`을 파일로 직접 더블클릭하면 브라우저 보안 정책 때문에 JSON 로딩이 실패할 수 있으므로 로컬 서버로 확인해야 합니다.

## 문제 해결

- Actions의 push가 거부되면 `Settings → Actions → General → Workflow permissions`를 확인합니다.
- Pages가 404이면 Pages의 Source가 `GitHub Actions`인지 확인합니다.
- 첫 실행은 2000년부터 데이터를 받기 때문에 이후 실행보다 오래 걸릴 수 있습니다.
- `pykrx`는 KRX 웹 구조 변경에 영향을 받을 수 있습니다. 조회 오류가 지속되면 패키지 업데이트와 Actions 로그를 확인하세요.
- GitHub Actions 예약 실행은 몇 분 지연될 수 있습니다.

## 데이터 사용 주의

이 프로젝트는 교육·개인 대시보드용 기본 구성입니다. 금융 의사결정이나 상업 서비스에 사용하려면 KRX 공식 데이터와 대조하고 데이터 이용 조건을 별도로 확인하세요.
