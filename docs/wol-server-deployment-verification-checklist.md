# WOL 서버 배포 및 Ubuntu 부팅 검증 체크리스트

이 문서는 실제 `wol-core` Ubuntu 서버에 프로젝트를 배포하고 검증할 때 사용하는 운영 체크리스트다. 듀얼부트 PC의 Windows 작업은 [Windows Ubuntu 일회성 부팅 적용 체크리스트](windows-ubuntu-boot-setup-checklist.md)를 따른다.

초기 배포는 반드시 `UBUNTU_BOOT_ENABLED=false`로 수행한다. 실제 BootNext 활성화와 재부팅은 Windows 체크리스트가 `GO`인 경우에만 진행한다.

## 1. 배포 중단 조건

다음 중 하나라도 발생하면 기능을 활성화하지 않는다.

- 서버 작업 트리에 보존해야 할 변경이 있는데 덮어쓸 배포를 하려 한다.
- `.env`, `app/targets.json`, `secrets`, `logs`, `data`의 백업 또는 보존 계획이 없다.
- systemd 서비스와 Docker 컨테이너가 동시에 TCP 8000을 사용한다.
- FastAPI가 `0.0.0.0:8000`, LAN IP 또는 Tailscale IP에 직접 노출된다.
- `/api/*`가 `Tailscale-User-Login` header 없이 성공한다.
- 컨테이너가 root로 실행되거나 SSH mount가 쓰기 가능하다.
- OS별 host key를 고정하지 않았거나 두 alias가 같은 known_hosts 구성을 공유한다.
- Windows exact token 또는 Ubuntu의 exact `Linux` 출력이 일치하지 않는다.
- Windows 체크리스트가 `GO`가 아니다.

## 2. 서버 현재 상태 조사와 백업

실제 `wol-core` 서버에서 먼저 다음 상태를 읽기 전용으로 확인한다.

```bash
cd /srv/wol-core
git status --short
git branch --show-current
git remote -v
id
systemctl status wol-web --no-pager
docker compose -f docker/compose.prod.yml ps
ss -ltnp 'sport = :8000'
tailscale serve status
```

주의사항:

- 현재 접속한 호스트가 실제 `wol-core`인지 확인한다. 듀얼부트 대상 PC에 Serve나 컨테이너를 대신 설정하지 않는다.
- `git status`에 사용자 변경이 있으면 자동 덮어쓰기, `git reset --hard`, `git clean`을 사용하지 않는다.
- 기존 systemd와 Docker 중 현재 운영 주체를 확인한다. Docker 전환 전까지 기존 서비스를 먼저 삭제하지 않는다.
- 배포 변경 전 `.env`, `app/targets.json`, Compose 설정, systemd unit 상태를 Git 밖의 관리자 전용 백업 위치에 보관한다.
- `secrets`는 별도 보안 백업 정책을 사용하고 mode를 유지한다. key 본문을 터미널 로그나 보고서에 출력하지 않는다.
- `logs`와 `data/boot-jobs.sqlite3`는 장애 조사와 작업 이력 보존을 위해 삭제하지 않는다.

소스 반영은 변경 사항을 확인한 뒤 fast-forward Git 배포 또는 검토된 파일 전송 방식으로 진행한다. 파일 전송 시에도 `.env`, `secrets`, `logs`, `data`, 운영 `app/targets.json`을 제외 없이 덮어쓰거나 `--delete`하지 않는다.

## 3. 운영 파일과 권한 준비

필요한 호스트 경로는 다음과 같다.

| 호스트 경로 | 컨테이너 경로 | 권한 |
| --- | --- | --- |
| `.env` | `/app/.env` | read-only |
| `app/targets.json` | `/app/app/targets.json` | read-write |
| `logs/` | `/app/logs` | read-write |
| `data/` | `/app/data` | read-write |
| `secrets/ssh/` | `/run/wol-ssh` | read-only |
| `secrets/` | `/srv/wol-core/secrets` | read-only, 기존 전원 명령 호환 |

컨테이너 UID/GID는 서버의 파일 소유권과 맞춰야 한다. 기본값 `1000:1000`이 다르면 `.env` 또는 Compose 실행 환경에 `WOL_UID`, `WOL_GID`를 실제 값으로 지정한다.

권장 확인 기준:

- `secrets`와 `secrets/ssh` 디렉터리는 일반 사용자가 탐색할 수 없다.
- private key는 소유자만 읽을 수 있다.
- SSH `config`와 OS별 known_hosts는 컨테이너 UID가 읽을 수 있지만 쓰기는 불가능하다.
- `logs`, `data`, `app/targets.json`은 컨테이너 UID만 필요한 범위에서 쓸 수 있다.
- `.gitignore`가 `.env`, private key, SQLite 운영 DB와 로그를 추적하지 않는지 확인한다.

## 4. OS별 SSH 구성

`secrets/ssh/config`에 다음 alias가 있어야 한다.

- `mainpc-windows`: Windows 전용 key, Windows 전용 known_hosts, `HostKeyAlias mainpc-windows`
- `mainpc-ubuntu`: Ubuntu 전용 key, Ubuntu 전용 known_hosts, `HostKeyAlias mainpc-ubuntu`

두 OS가 같은 IP를 사용하더라도 known_hosts 파일과 `HostKeyAlias`를 분리한다. 운영에서는 `StrictHostKeyChecking yes`, `BatchMode yes`, `IdentitiesOnly yes`를 사용한다. `accept-new`로 자동 등록하지 않는다.

Windows BootNext 전용 key는 기존 `app/targets.json`이 사용하는 legacy 전원 key와 분리한다. Compose의 부모 `secrets` mount는 기존 shutdown/reboot 명령 경로 호환용이며, 새 boot job은 `/run/wol-ssh/config`만 사용한다.

실제 구성 예시는 [Ubuntu 선택 부팅 SSH 계약](ubuntu-boot-ssh-contract.md)을 따른다.

## 5. `.env` 초기값

운영 배포 전에 다음 값을 확인한다. 실제 주소, key 경로와 비밀값은 저장소에 커밋하지 않는다.

```dotenv
HOST=127.0.0.1
PORT=8000
NEXT_PUBLIC_API_BASE=

UBUNTU_BOOT_ENABLED=false
UBUNTU_BOOT_TARGET=mainpc
WINDOWS_SSH_ALIAS=mainpc-windows
UBUNTU_SSH_ALIAS=mainpc-ubuntu
WOL_SSH_CONFIG=/run/wol-ssh/config
BOOT_DB_PATH=/app/data/boot-jobs.sqlite3
WINDOWS_READY_TIMEOUT=180
UBUNTU_READY_TIMEOUT=300
BOOT_JOB_TIMEOUT=480
BOOT_POLL_INTERVAL=5
SSH_COMMAND_TIMEOUT=10
REBOOT_START_TIMEOUT=30
BOOT_JOB_RETENTION_DAYS=7
```

`NEXT_PUBLIC_API_BASE`는 Serve와 동일 오리진을 사용하도록 빈 문자열로 둔다. 초기 상태의 `UBUNTU_BOOT_ENABLED=false`는 Windows 작업이 끝나기 전에 버튼과 생성 API가 활성화되는 것을 막는다.

## 6. Docker 빌드와 기동

먼저 Compose 구성을 검증하고 이미지를 빌드한다.

```bash
cd /srv/wol-core
docker compose -f docker/compose.prod.yml config
docker compose -f docker/compose.prod.yml build
```

빌드가 성공하고 새 컨테이너가 준비된 뒤에만 기존 `wol-web` systemd 서비스의 중지·비활성화를 진행한다. 서비스 파일은 삭제하지 말고 백업 상태를 유지한다. TCP 8000을 사용할 프로세스가 하나만 남은 것을 확인한 뒤 컨테이너를 시작한다.

```bash
docker compose -f docker/compose.prod.yml up -d
docker compose -f docker/compose.prod.yml ps
```

## 7. 컨테이너와 직접 노출 검증

다음 검증을 모두 통과해야 한다.

```bash
curl --fail http://127.0.0.1:8000/healthz
curl -i http://127.0.0.1:8000/api/targets
curl -i -H 'Tailscale-User-Login: local-deployment-check' http://127.0.0.1:8000/api/targets
ss -ltnp 'sport = :8000'
docker compose -f docker/compose.prod.yml exec -T wolweb id
docker compose -f docker/compose.prod.yml exec -T wolweb test ! -w /run/wol-ssh
docker compose -f docker/compose.prod.yml exec -T wolweb test -w /app/data
docker compose -f docker/compose.prod.yml exec -T wolweb test -w /app/logs
```

예상 결과:

- `/healthz`는 `200`이다.
- identity header 없는 `/api/targets`는 `401`이다.
- localhost에서 시험용 identity header를 넣은 요청만 `200`이다.
- TCP 8000은 `127.0.0.1`에만 수신한다.
- 컨테이너 UID는 `0`이 아니다.
- `/run/wol-ssh`와 legacy secret mount는 쓰기 불가능하다.
- `/app/data`, `/app/logs`, `/app/app/targets.json`은 필요한 쓰기 권한이 있다.
- 컨테이너 root filesystem은 read-only이고 health 상태는 healthy다.
- `/api/targets`의 `mainpc.can_boot_ubuntu`는 아직 `false`다.

시험용 `Tailscale-User-Login` header는 localhost 진단에서만 직접 넣는다. 외부 클라이언트가 임의 header로 backend에 도달하지 못하도록 localhost 바인딩을 유지한다.

## 8. Tailscale Serve 검증

이 설정은 실제 `wol-core`에서만 수행한다.

```bash
tailscale serve --bg 8000
tailscale serve status
```

Serve 상태에서 도메인 루트 `/`가 `http://127.0.0.1:8000`으로 전달되는지 확인한다. `/wol` 같은 서브경로가 아니다.

Tailnet의 다른 허용 사용자로 HTTPS URL에 접속해 다음을 확인한다.

- 포털과 `/api/targets`가 정상 표시된다.
- Serve가 identity header를 추가한다.
- LAN IP, Tailnet IP의 `:8000` 직접 접속은 실패한다.
- 공유 장비와 외부 Tailnet 사용자의 접근 범위가 Tailscale ACL/공유 정책과 일치한다.

identity header가 있는 모든 Serve 사용자는 전원 API를 사용할 수 있으므로 ACL 검토가 완료되지 않으면 기능을 활성화하지 않는다.

## 9. 기능 활성화 전 SSH 시험

`UBUNTU_BOOT_ENABLED=false` 상태에서 OS별 probe만 시험한다.

Windows가 실행 중일 때:

```bash
docker compose -f docker/compose.prod.yml exec -T wolweb \
  ssh -F /run/wol-ssh/config mainpc-windows probe-windows
```

출력은 정확히 `WINDOWS_READY_V1`이어야 하며 Ubuntu alias는 성공하면 안 된다.

Ubuntu가 실행 중일 때:

```bash
docker compose -f docker/compose.prod.yml exec -T wolweb \
  ssh -F /run/wol-ssh/config mainpc-ubuntu 'uname -s'
```

출력은 정확히 `Linux`여야 하며 Windows probe는 성공하면 안 된다. host key 불일치, 추가 banner, token 앞뒤의 다른 출력도 실패로 취급한다.

`set-ubuntu-once`, `clear-ubuntu-once`, `reboot`는 Windows 체크리스트의 승인 단계에서만 호출한다.

## 10. 기능 활성화

아래 조건이 전부 충족된 경우에만 진행한다.

- Windows 완료 보고서가 `GO`다.
- Windows에서 set → clear 무재부팅 시험이 통과했다.
- 서버의 인증, 포트, 비루트, read-only mount 검증이 통과했다.
- Windows/Ubuntu alias가 각 OS에서 서로 배타적으로 성공했다.
- 기존 Wake, shutdown, reboot 기능이 회귀 시험을 통과했다.

`.env`를 백업한 뒤 `UBUNTU_BOOT_ENABLED=true`로 변경하고 컨테이너를 재생성한다.

```bash
docker compose -f docker/compose.prod.yml up -d --force-recreate
docker compose -f docker/compose.prod.yml ps
```

Serve를 통해 `/api/targets`의 `mainpc.can_boot_ubuntu=true`, UI의 `Ubuntu로 켜기` 버튼, 확인창과 작업 단계 표시를 확인한다. 다른 대상에는 capability와 버튼이 없어야 한다.

## 11. 실제 인수 시험 순서

각 시험은 이전 단계가 성공한 뒤 하나씩 진행한다.

1. **Windows 켜짐 → Ubuntu**: 버튼을 한 번 실행하고 `setting_bootnext`, `rebooting`, `waiting_for_ubuntu`, `succeeded` 흐름을 확인한다.
2. **다음 일반 부팅**: 기존 기본 OS로 복귀하고 firmware 기본 order가 변하지 않았는지 확인한다.
3. **Ubuntu 이미 실행 중**: 다시 실행했을 때 WOL과 재부팅 없이 성공하는지 확인한다.
4. **PC OFF → Ubuntu**: WOL 한 번, Windows 준비, BootNext, 재부팅, Ubuntu 확인 순서를 확인한다.
5. **중복 요청**: 진행 중 같은 대상 요청이 기존 job ID와 함께 `409`인지 확인한다.
6. **취소**: `setting_bootnext` 전에만 가능하고 그 이후에는 불가능한지 확인한다.
7. **새로고침 복원**: 페이지를 새로 열어도 활성 job 단계가 복원되는지 확인한다.

강제로 재부팅 실패나 host key 불일치를 만드는 시험은 실제 운영 장비가 아니라 통제된 staging 또는 mock 환경에서 우선 수행한다.

## 12. 로그·DB·회귀 확인

시험 후 다음을 확인한다.

- job DB가 `/app/data/boot-jobs.sqlite3`에 생성되고 재생성 후에도 유지된다.
- API job 응답에는 계약된 안전 필드만 있다.
- 로그에는 사용자 identity, target, stage, 안전한 error code만 남는다.
- 로그와 API에 GUID, key 경로, SSH 명령, stdout/stderr, 실제 secret이 없다.
- 7일이 지난 종료 job 정리 정책이 설정돼 있다.
- 컨테이너 재시작 시 진행 중 job은 자동 재개되지 않고 `failed/service_restarted`로 정리된다.
- 기존 Wake, shutdown, reboot, target 수정과 로그 조회가 정상이다.

secret 확인을 위해 `cat`으로 key를 출력하지 않는다. 권한과 파일 존재 여부만 검사한다.

## 13. 문제 발생 시 복구

Ubuntu 기능에 문제가 있으면 전체 포털을 먼저 내리지 말고 다음 순서로 기능만 차단한다.

1. `.env`의 `UBUNTU_BOOT_ENABLED=false`를 적용한다.
2. 컨테이너를 재생성한다.
3. `/api/targets`에서 capability가 `false`인지 확인한다.
4. 진행 중 job과 Windows BootNext 상태를 확인한다.
5. 재부팅이 시작되지 않았고 BootNext만 남은 것이 확실할 때만 승인된 `clear-ubuntu-once`를 호출한다.
6. 로그와 Windows 완료 보고서를 대조하되 민감값은 수집하지 않는다.

이전 서버 버전으로 복귀해야 하면 배포 전 백업과 검증된 image tag를 사용한다. `data`, `logs`, `.env`, `secrets`, 운영 targets를 삭제하지 않는다. Tailscale Serve를 끄는 작업은 포털 전체 노출을 중단할 때만 별도 승인 후 수행한다.

## 14. 서버 배포 결과 기록 양식

| 항목 | 결과 | 비고 |
| --- | --- | --- |
| 운영 호스트 확인 | PASS/FAIL | `wol-core` 여부 |
| 설정·데이터·secret 보존 | PASS/FAIL | key 본문 기록 금지 |
| Docker build/health | PASS/FAIL | image 식별자만 기록 가능 |
| 비루트·read-only 검증 | PASS/FAIL | UID/GID만 기록 |
| localhost 전용 8000 | PASS/FAIL | 외부 직접 접근 실패 포함 |
| API identity 401/200 | PASS/FAIL | 사용자 identity 원문 최소화 |
| Serve 루트 프록시 | PASS/FAIL | `/` 기준 |
| Tailnet ACL 검토 | PASS/FAIL | 허용 범위 값은 별도 보관 |
| Windows probe exact token | PASS/FAIL |
| Ubuntu probe exact `Linux` | PASS/FAIL |
| 기존 전원 기능 회귀 | PASS/FAIL |
| feature flag 활성화 | PASS/FAIL/NOT RUN |
| Windows → Ubuntu | PASS/FAIL/NOT RUN |
| 기본 OS 복귀 | PASS/FAIL/NOT RUN |
| OFF → WOL → Ubuntu | PASS/FAIL/NOT RUN |
| 로그 redaction | PASS/FAIL |

최종 판정은 `DEPLOYED_DISABLED`, `GO`, `NO-GO`, `ROLLED_BACK` 중 하나로 기록한다.
