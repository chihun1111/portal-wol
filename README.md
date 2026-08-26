# wol-web    아직 업데이트중입니다

Tailnet 전용 Wake-on-LAN, 전원 제어 및 Ubuntu 일회성 선택 부팅 대시보드입니다. FastAPI + 정적 프론트엔드로 구성되며 운영 환경은 Docker와 Tailscale Serve를 사용합니다.

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
- 대상이 꺼져 있으면 WOL 전송 → Windows 제한 계정 SSH 로그인 확인 → 일회성 Ubuntu BootNext → Ubuntu SSH 확인 작업
- 타겟(PC) 목록 CRUD, 상태 폴링, Wake 실행을 제공하는 웹 UI
- MAC 미설정 장비에 대한 자동 학습(ARP 기반, 온라인 상태에서) 및 시각적 안내
- Tailscale Serve identity 기반 API 보호

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

1. `.env.example`을 참고해 `.env`를 준비하되 `UBUNTU_BOOT_ENABLED=false`를 유지합니다.
2. `logs`, `data`, `secrets/ssh`를 컨테이너 UID/GID가 읽고 쓸 수 있도록 준비합니다.
3. [Ubuntu 선택 부팅 SSH 계약](docs/ubuntu-boot-ssh-contract.md)에 따라 OS별 alias와 pinned host key를 구성합니다.
4. Docker를 시작하고 Tailscale Serve가 도메인 루트에서 localhost 포트를 프록시하도록 설정합니다.

실제 적용은 [Windows 적용 체크리스트](docs/windows-ubuntu-boot-setup-checklist.md)와 [WOL 서버 배포·검증 체크리스트](docs/wol-server-deployment-verification-checklist.md)를 순서대로 사용합니다. Windows 보고서가 `GO`가 되기 전에는 feature flag를 활성화하지 않습니다.

```bash
mkdir -p logs data secrets/ssh
docker compose -f docker/compose.prod.yml up -d --build
tailscale serve --bg 8000
docker compose -f docker/compose.prod.yml ps
```

컨테이너는 host network를 사용하지만 FastAPI를 `127.0.0.1:8000`에만 바인딩합니다. LAN 주소나 Tailscale IP의 `:8000`으로 직접 접근하지 말고 Serve가 출력한 HTTPS URL을 사용합니다.

Compose의 `WOL_SSH_DIR`은 새 OS 판별/BootNext SSH 구성을, `WOL_LEGACY_SECRETS_DIR`은 기존 `targets.json` 전원 명령이 참조하는 key 경로를 각각 read-only로 연결합니다. 호스트 경로를 바꾸려면 Compose 실행 전에 두 값을 지정합니다.

## 환경 변수 (.env)
| 키 | 설명 |
| --- | --- |
| `LAN_IFACE` | 매직 패킷을 보낼 NIC 이름. Linux: `ip -br addr` 로 확인 |
| `BROADCAST` | 대상 PC 서브넷 브로드캐스트 IP. 서버 LAN이 바뀌면 반드시 함께 갱신 (`ip route`로 확인) |
| `WOL_METHOD` | `python`(기본) 또는 `etherwake` |
| `STATUS_TCP_PORTS` | ping 응답이 차단된 장비를 위해 상태 확인 시 추가로 검사할 TCP 포트 목록 (쉼표 구분, 기본 `3389,445,22`) |
| `HOST`, `PORT` | FastAPI 바인딩 주소/포트 |
| `LOG_PATH` | JSONL 로그 파일 경로 |
| `LOG_RETENTION_DAYS`, `LOG_MAX_LIMIT` | 로그 보존 일수 / `/api/logs` 반환 최대 개수 |
| `NEXT_PUBLIC_API_BASE` | Next.js 빌드 시 API 기본 URL. 동일 오리진이면 빈 문자열 유지 |
| `UBUNTU_BOOT_ENABLED` | Windows/SSH 수동 검증 후에만 `true`로 변경 (기본 `false`) |
| `UBUNTU_BOOT_TARGET` | Ubuntu 선택 부팅을 허용할 단일 대상 (기본 `mainpc`) |
| `WINDOWS_SSH_ALIAS`, `UBUNTU_SSH_ALIAS` | read-only SSH config에 정의한 OS별 alias |
| `WOL_SSH_CONFIG` | 컨테이너 내부 SSH config 경로 |
| `BOOT_DB_PATH` | 작업 상태 SQLite 경로 |
| `WINDOWS_READY_TIMEOUT`, `UBUNTU_READY_TIMEOUT`, `BOOT_JOB_TIMEOUT` | 단계별 및 전체 제한 시간(초) |
| `BOOT_POLL_INTERVAL`, `SSH_COMMAND_TIMEOUT` | OS 확인 주기와 SSH 명령 제한 시간(초) |
| `REBOOT_START_TIMEOUT` | Windows가 계속 응답할 때 재부팅 미시작으로 판정하기 전 대기 시간(초) |

`.env.example` 는 Docker/운영 기본값을 참고용으로 제공합니다. 현재 운영 LAN
`192.168.123.0/24`에서는 `BROADCAST=192.168.123.255`를 사용합니다. 값이 빠진 경우
애플리케이션은 특정 사설망에 종속되지 않는 `255.255.255.255`를 사용합니다.

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
| `POST` | `api/boot/ubuntu` | Ubuntu 부팅 job 생성 (`202`) |
| `GET` | `api/jobs`, `api/jobs/{id}` | 작업 목록 및 상태 조회 |
| `POST` | `api/jobs/{id}/cancel` | BootNext 설정 전 작업 취소 |
| `GET` | `api/logs?limit=N` | 최근 로그 반환 (JSONL 역순)
| `GET` | `healthz` | localhost 컨테이너 상태 확인 (identity 제외) |

모든 `api/...` 요청은 Tailscale Serve가 추가하는 `Tailscale-User-Login` header가 필요합니다. 백엔드를 localhost에만 바인딩해야 이 header를 신뢰할 수 있습니다. 포털은 Serve 도메인의 루트 `/`에 배포하며 `NEXT_PUBLIC_API_BASE`는 빈 문자열을 사용합니다.

identity header가 있는 사용자는 모두 허용되므로 해당 장비를 공유받은 외부 Tailscale 사용자도 Tailnet 정책상 Serve에 접근할 수 있다면 포함됩니다. 전원 권한 범위는 Tailscale ACL과 장비 공유 설정에서 제한합니다.

## 웹 UI 요약
- 상단 검색창 + “+ 타겟 추가” 버튼으로 빠른 필터링 및 생성
- 각 행에서 Wake / 종료 / 재부팅 / Ubuntu 부팅 / 편집 / 삭제 버튼 제공
- Ubuntu 부팅 작업의 단계, 경과 시간, 취소 가능 여부를 2초 간격으로 표시
- 15초 간격 자동 상태 폴링(수동 새로고침 버튼 제공)
- 최근 로그 패널에서 100건 단위로 더보기 가능

## 운영 모드

운영은 Docker Compose만 사용합니다. 기존 systemd 서비스가 있다면 먼저 중지하고 비활성화해야 하며 두 방식을 동시에 실행하지 않습니다. `scripts/setup_ubuntu.sh`와 `systemd/`는 기존 설치 호환용으로만 남아 있고 Ubuntu 선택 부팅 운영 경로가 아닙니다.

## Docker
- Linux 서버에서는 host 네트워크 모드 사용 시 브로드캐스트(WOL) 가 동작이 보장됩니다.
- Windows Docker Desktop은 host 모드가 제한적이므로 개발용으로는 venv 실행을 권장합니다.
- 컨테이너는 비루트 UID/GID로 실행하며 SSH 설정은 read-only로 연결합니다. job DB, 로그와 기존 대상 CRUD에 필요한 `app/targets.json`만 쓰기 가능 볼륨으로 연결합니다.
- Next.js 번들은 빈 `NEXT_PUBLIC_API_BASE`로 빌드해 Serve HTTPS URL과 동일 오리진을 사용합니다.

```bash
docker compose -f docker/compose.prod.yml up -d
```

실제 BootNext 기능은 Windows 관리자 BCD 확인, 제한 wrapper와 OS별 SSH 시험을 마친 뒤에만 `.env`의 `UBUNTU_BOOT_ENABLED=true`로 활성화하고 컨테이너를 재생성합니다. 초기 배포와 인증 검증은 반드시 `false` 상태에서 수행합니다.

## 테스트
```bash
pytest -q
cd web && npm run lint && npm run build
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
