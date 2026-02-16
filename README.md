# wol-web    아직 업데이트중입니다

Tailnet 전용 Wake-on-LAN & 전원 제어 대시보드입니다. FastAPI + 정적 프론트엔드로 구성되어 있으며, Docker 또는 systemd 중 하나의 방식으로 구동할 수 있습니다.

## Next.js 프론트엔드(`web/`)
기존 정적 자바스크립트 UI는 Next.js(App Router) 기반 SPA로 재구성되었습니다. FastAPI 백엔드와 동일한 오리진에서 서비스를 제공하면
상대경로(`/api/...`)로 바로 연동할 수 있고, 개발 환경에서는 `NEXT_PUBLIC_API_BASE` 환경변수로 백엔드 주소를 지정할 수 있습니다.

### 개발 서버 실행

```bash
cd web
npm install
# FastAPI 개발 서버가 http://127.0.0.1:8000 에서 동작 중이라고 가정
export NEXT_PUBLIC_API_BASE="http://127.0.0.1:8000"
npm run dev
```

### FastAPI에서 서빙할 정적 번들 생성

Next.js는 `output: 'export'` 설정으로 정적 HTML/JS 번들을 생성하며, 아래 스크립트가 결과물을 `app/static/`에 복사합니다. Node.js 20 이상이 필요합니다.

```bash
# 저장소 루트에서 실행
export NEXT_PUBLIC_API_BASE=""   # 동일 오리진이면 빈 문자열 유지
./scripts/build_frontend.sh
```

Windows PowerShell:

```powershell
$env:NEXT_PUBLIC_API_BASE = ""
./scripts/build_frontend.ps1
```

빌드가 끝나면 `app/static/index.html` 이하에 Next.js 산출물이 복사되며 FastAPI가 `/` 및 `/wol` 경로를 정적 자산으로 서빙합니다.

## 주요 기능
- Wake / Shutdown / Reboot 명령 API 및 JSONL 로그 기록
- 타겟(PC) 목록 CRUD, 상태 폴링, Wake 실행을 제공하는 웹 UI
- MAC 미설정 장비에 대한 자동 학습(ARP 기반, 온라인 상태에서) 및 시각적 안내

## 빠른 시작 (Windows 개발)
```powershell
# 1) Next.js 번들 생성 (최초 1회)
./scripts/build_frontend.ps1

# 2) FastAPI 의존성 설치 및 서버 실행
.\.venv\Scripts\Activate.ps1
python -m app.main

# 3) 브라우저 접속
http://127.0.0.1:8000/
```

## 빠른 시작 (Ubuntu 운영)

### 자동화 스크립트
```bash
./scripts/setup_ubuntu.sh --install-systemd
```
- Node.js 20.x, Python 3, etherwake 등 필요한 패키지를 설치합니다.
- `.venv/` 가상환경을 생성하고 `requirements.txt`를 설치합니다.
- `scripts/build_frontend.sh`를 호출해 Next.js 정적 자산을 `app/static/`으로 동기화합니다.
- `--install-systemd` 옵션을 주면 `systemd/wol-web.service`를 `/etc/systemd/system/`으로 복사하고 즉시 실행합니다.
- 기존에 패키지를 설치해 두었으면 `--skip-apt`, 외부 API 주소가 다르면 `--api-base https://foo` 같은 인자를 추가하세요.
- 필요한 단계마다 `sudo` 권한을 요청하므로 일반 사용자 계정에서 실행하면 됩니다.
- Windows에서 바로 원격 서버를 준비하려면 `./scripts/setup_ubuntu.sh --remote-host ubuntu@192.168.123.112 --remote-path /opt/wol-web --install-systemd` 처럼 실행하면 저장소가 SSH로 복사되고 원격에서 동일 스크립트가 실행됩니다 (rsync 사용 가능 시 활용, 없으면 tar/ssh로 전송).

### 수동 절차 (참고용)
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip etherwake
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./scripts/build_frontend.sh
cp .env.example .env  # 환경에 맞게 수정
sudo cp systemd/wol-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wol-web
sudo systemctl status wol-web --no-pager
```

## 환경 변수 (.env)
| 키 | 설명 |
| --- | --- |
| `LAN_IFACE` | 매직 패킷을 보낼 NIC 이름. Linux: `ip -br addr` 로 확인 |
| `BROADCAST` | 대상 PC 서브넷 브로드캐스트 IP |
| `WOL_METHOD` | `python`(기본) 또는 `etherwake` |
| `STATUS_TCP_PORTS` | ping 응답이 차단된 장비를 위해 상태 확인 시 추가로 검사할 TCP 포트 목록 (쉼표 구분, 기본 `3389,445,22`) |
| `HOST`, `PORT` | FastAPI 바인딩 주소/포트 |
| `LOG_PATH` | JSONL 로그 파일 경로 |
| `LOG_RETENTION_DAYS`, `LOG_MAX_LIMIT` | 로그 보존 일수 / `/api/logs` 반환 최대 개수 |
| `NEXT_PUBLIC_API_BASE` | Next.js 빌드 시 API 기본 URL. 동일 오리진이면 빈 문자열 유지 |

`.env.example` 는 Docker/운영 기본값을 참고용으로 제공합니다.

## 타겟 저장소 구조 (`app/targets.json`)
타겟의 IP/MAC/명령은 **`app/targets.json` 한 파일만** 사용합니다.  
IP를 바꿀 때는 `ip` 필드만 수정하면 되고, 명령에서 `{ip}`, `{name}`, `{mac}` 템플릿을 사용할 수 있습니다.

기존 딕셔너리 형태를 자동 변환하며, 새 UI는 다음 포맷을 사용합니다.
```json
{
  "targets": [
    { "name": "mainpc", "ip": "192.168.123.20", "mac": "AA:BB:CC:DD:EE:FF" },
    { "name": "nas", "ip": "192.168.123.11" }
  ]
}
```
- `name`: 소문자/숫자/하이픈 2~32자, 고유 필수
- `ip`: IPv4 필수
- `mac`: 선택(AA:BB 형식). 없으면 온라인 상태에서 `ip neigh`/`arp -n` 으로 자동 학습을 시도하고, UI에서 Wake 버튼이 비활성화됩니다.
- 기존 `shutdown`/`reboot` 명령 필드가 있다면 그대로 유지되며, API를 통해 실행 가능합니다.

## API 개요
| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `api/targets` | 타겟 목록 조회 (MAC 보유 여부, 최근 상태/웨이크 시간 포함) |
| `POST` | `api/targets` | 타겟 추가 `{ name, ip, mac? }` |
| `PATCH` | `api/targets/{name}` | 타겟 수정 (이름/IP/MAC 부분 업데이트) |
| `DELETE` | `api/targets/{name}` | 타겟 삭제 |
| `GET` | `api/status?target=<name>` | 단건 상태 체크 (ping 1회) + MAC 자동 학습 |
| `POST` | `api/wake` | Wake on LAN 전송 `{ target }` |
| `POST` | `api/shutdown` / `api/reboot` | 타겟에 설정된 명령 실행 |
| `GET` | `api/logs?limit=N` | 최근 로그 반환 (JSONL 역순)

모든 경로는 Tailscale Serve로 `/wol` 서브패스에 배포할 때를 고려하여 **상대경로** (`api/...`, `static/...`)를 사용합니다.

## 웹 UI 요약
- 상단 검색창 + “+ 타겟 추가” 버튼으로 빠른 필터링 및 생성
- 각 행에서 Wake / 편집 / 삭제 버튼 제공, MAC 미설정 시 배지 및 Wake 비활성화
- 15초 간격 자동 상태 폴링(수동 새로고침 버튼 제공)
- 최근 로그 패널에서 100건 단위로 더보기 가능
- 토큰이 필요한 환경이면 우측 상단 토큰 패널에서 저장 → 모든 fetch 요청에 헤더 자동 첨부

## 운영 모드 선택 (Docker 권장)
- Docker Compose(prod)를 사용할 경우 `docker compose -f docker/compose.prod.yml up -d`
  - systemd 서비스가 이미 돌고 있다면 `sudo systemctl disable --now wol-web`
- systemd 기반으로 운영한다면 Docker Compose는 중단(`docker compose -f docker/compose.prod.yml down`)
- 두 방식을 동시에 켜면 8000 포트가 충돌합니다.

## Docker
- Linux 서버에서는 host 네트워크 모드 사용 시 브로드캐스트(WOL) 가 동작이 보장됩니다.
- Windows Docker Desktop은 host 모드가 제한적이므로 개발용으로는 venv 실행을 권장합니다.
- Next.js 번들이 컨테이너 빌드 단계에서 생성되므로 `NEXT_PUBLIC_API_BASE` 환경변수를 필요에 따라 지정하세요 (기본은 빈 문자열로 동일 오리진 호출).

```bash
docker compose -f docker/compose.prod.yml up -d
```

## 테스트
```bash
pytest -q
```

## 프로젝트 구조
```
wol-web/
  app/
    api/
      __init__.py
      routes.py
    core/
      __init__.py
      settings.py
    services/
      __init__.py
      logs.py
      power.py
      targets.py
    static/
      (Next.js 빌드 산출물이 위치 – scripts/build_frontend.sh 실행 시 생성)
    config.py
    main.py
    targets.json            # 예시
  docker/
    Dockerfile
    compose.dev.yml
    compose.prod.yml
  logrotate/
    wol-web
  scripts/
    dev.ps1
    dev.sh
    build_frontend.ps1
    build_frontend.sh
    setup_ubuntu.sh
  systemd/
    wol-web.service
  tests/
    test_status.py
  .env.example
  requirements.txt
  README.md
```

## 종료/재부팅 명령 구성
`app/targets.json`에서 `shutdown`/`reboot` 키를 정의하면 API가 해당 명령을 실행합니다. 명령은 문자열, 배열, 또는 객체(`cmd`, `shell`, `timeout`) 형태를 지원합니다.
명령 내 `{ip}`, `{name}`, `{mac}`(또는 `{target}`)은 실행 시 타겟 값으로 치환됩니다.
```json
{
  "targets": [
    {
      "name": "mainpc",
      "ip": "192.168.123.175",
      "mac": "AA:BB:CC:DD:EE:FF",
      "shutdown": {
        "cmd": ["ssh", "user@{ip}", "powershell", "-NoProfile", "Stop-Computer", "-Force"],
        "timeout": 15
      },
      "reboot": {
        "cmd": ["ssh", "user@{ip}", "powershell", "-NoProfile", "Restart-Computer", "-Force"],
        "timeout": 15
      }
    }
  ]
}
```

### 로그 보존
`.env`의 `LOG_RETENTION_DAYS` (기본 7일), `LOG_MAX_LIMIT`(기본 500)으로 JSONL 로그 유지 기간과 API 반환 개수를 제어할 수 있습니다. `/api/logs`는 UI에서 그대로 표시됩니다.
## PowerShell 실행 정책 참고


PowerShell 실행 정책 오류 원인과 해결

Windows PowerShell은 기본적으로 디지털 서명이 없는 스크립트를 실행하지 못하도록 막아 둡니다. scripts/build_frontend.ps1는 개인 저장소에 포함된 개발용 스크립트이기 때문에 서명이 없고, 이 때문에 “cannot be loaded … not digitally signed”라는 메시지가 출력된 것입니다.

스크립트 실행을 허용하는 가장 간단한 방법은 현재 PowerShell 세션에서만 실행 정책을 완화하는 것입니다.

# ① PowerShell을 관리자 권한으로 열고, 현재 창에서만 정책 완화
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# ② 또는 파일을 미리 해제
Unblock-File -Path .\scripts\build_frontend.ps1

이후 동일한 PowerShell 창에서 ./scripts/build_frontend.ps1을 다시 실행하면 빌드가 진행됩니다. 새 창을 열면 정책이 원래대로 돌아오므로, 필요할 때마다 ①을 반복하면 됩니다.
Windows에서 전체 빌드 순서

    사전 준비

        Node.js 20 이상과 npm, Python 3.11(또는 프로젝트에서 사용하는 버전)을 설치합니다.

        가상환경을 만들고 FastAPI 의존성을 설치합니다.

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt

PowerShell 실행 정책 완화

    위의 Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass를 먼저 실행해 스크립트를 허용합니다.

프런트엔드 번들 생성

    필요하다면 API 주소를 환경 변수로 지정한 뒤 빌드 스크립트를 실행합니다.

$env:NEXT_PUBLIC_API_BASE = ""   # 동일 오리진이면 빈 문자열 유지
./scripts/build_frontend.ps1

이 스크립트는 web/ 디렉터리에서 npm install(최초 1회), npm run build를 수행하고, 생성된 out/ 디렉터리의 정적 파일을 FastAPI가 사용하는 app/static/으로 복사합니다.

NEXT_PUBLIC_API_BASE가 어떤 용도인지 README의 환경 변수 표에 정리되어 있으니 필요에 맞게 값을 지정합니다.

백엔드 실행

    이미 활성화된 가상환경에서 FastAPI 앱을 기동합니다.

python -m app.main

README의 “빠른 시작 (Windows 개발)” 절차와 동일하게 브라우저에서 http://127.0.0.1:8000/으로 접속하여 결과를 확인할 수 있습니다.

반복 작업 시

    프런트엔드 소스를 수정할 때마다 3단계를 다시 실행해 app/static/을 최신 상태로 갱신한 뒤 FastAPI를 재시작하면 됩니다.
