# CHAT-SERVER-PUBLIC

공용 채팅방: 아이디/비밀번호 회원가입, 로그인, 메시지 최대 25자, 최신 메시지 20개만 DB에 유지합니다.

## 공개 배포 전에 알아둘 점
- 앱은 Gunicorn으로 실행하며 Flask 개발 서버(debug=True)를 사용하지 않습니다.
- CSRF 보호, 보안 헤더, 로그인/회원가입/메시지 요청 제한을 추가했습니다.
- `SECRET_KEY`는 배포 플랫폼에서 강한 비밀값으로 설정합니다.
- `database.db`에는 계정과 메시지가 저장됩니다. DB가 있는 `data/` 경로는 **영구 저장 디스크/볼륨**에 연결해야 재배포 후에도 계정이 유지됩니다.
- 무료 호스팅은 24시간 가동, 저장공간 영구 보존 또는 무제한 사용량을 보장하지 않을 수 있습니다.
- SQLite를 쓰는 이 기본판은 단일 인스턴스/단일 worker 용도입니다. 여러 인스턴스로 확장하려면 PostgreSQL 등으로 바꾸세요.
- 이 버전은 WebSocket이 아니라 2초마다 새 메시지를 확인하는 polling 방식입니다.
- 운영 전에는 백업, 개인정보 안내, 신고/차단 및 관리 기능도 추가하는 것을 권장합니다.

## 로컬에서 테스트 (Windows PowerShell)
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
New-Item -ItemType Directory -Force data
$env:APP_ENV = "development"
$env:SECRET_KEY = "local-test-only-change-this-to-a-long-random-value"
$env:COOKIE_SECURE = "0"
$env:CHAT_DATA_DIR = "./data"
python -m flask --app app run
```
브라우저에서 `http://127.0.0.1:5000` 을 엽니다.

## GitHub + Render 배포 (가장 간단한 업로드 경로)
1. GitHub에서 새 **Private repository**를 만듭니다.
2. 압축을 푼 이 폴더의 파일들을 저장소에 업로드합니다. `.env`나 `data/`/DB 파일은 올리지 않습니다.
3. Render에서 새 Web Service를 만들고 GitHub 저장소를 연결합니다. `render.yaml`이 배포 설정을 제공합니다.
4. Render 환경변수에서 `APP_ENV=production`, `SECRET_KEY`(Generate/임의의 긴 비밀값), `COOKIE_SECURE=1`을 확인합니다.
5. 중요: Render 무료 인스턴스는 잠들 수 있고 로컬 파일이 영구 보존되지 않을 수 있습니다. 영구 디스크는 유료일 수 있으므로, **무료 Render에 DB를 두고 실제 서비스 운영을 시작하지 마세요**. 테스트용으로만 쓰거나 영구 저장이 가능한 서버/볼륨을 구성하세요.

## Oracle Cloud VM에 배포 (상시 실행에 더 적합하지만 설정이 더 어려움)
1. Oracle Cloud Free Tier에서 VM을 만들고 Linux 이미지를 선택합니다. 사용 가능 여부와 무료 자원은 계정/지역에 따라 달라질 수 있습니다.
2. SSH로 접속하거나 Cloud Shell을 사용해 프로젝트 파일을 VM에 복사합니다. GitHub 저장소를 쓴다면:
   ```bash
   git clone https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
   cd YOUR-REPOSITORY
   ```
3. 서버에 Python 3.12+, `python3-venv`, `nginx`를 설치합니다.
4. 프로젝트 폴더에서 가상환경을 만들고 설치합니다.
   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   mkdir -p data
   ```
5. `SECRET_KEY`는 충분히 긴 임의 문자열로 만들고, `APP_ENV=production`, `COOKIE_SECURE=1`, `CHAT_DATA_DIR=/절대경로/프로젝트/data` 환경변수를 설정합니다. `COOKIE_SECURE=1`은 HTTPS 설정을 마친 뒤 사용합니다.
6. Nginx를 HTTPS 역방향 프록시로 설정하고, Gunicorn을 systemd 서비스로 실행하도록 구성합니다. 외부에 Gunicorn 포트를 직접 공개하지 마세요.
7. 방화벽에서 HTTPS(443)만 공개하고, HTTPS가 동작하는지 확인합니다.

Oracle Cloud VM 배포는 계정/OS별 설정이 다르므로 README의 안내만으로 모든 방화벽·도메인·TLS 설정이 자동 완료되지는 않습니다.
