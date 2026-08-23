# Windows Ubuntu 일회성 부팅 적용 체크리스트

이 문서는 듀얼부트 `mainpc`의 Windows 관리자 또는 Windows 측 에이전트가 수행할 작업만 정리한다. 프로젝트가 기대하는 인터페이스는 [Ubuntu 선택 부팅 SSH 계약](ubuntu-boot-ssh-contract.md)을 기준으로 한다.

실제 firmware GUID, IP/MAC, SSH key 본문, 계정 자격 증명은 이 저장소와 작업 보고서에 기록하지 않는다.

## 1. 적용 전 중단 조건

다음 중 하나라도 해당하면 BootNext 설정과 재부팅 시험을 진행하지 않는다.

- 관리자 PowerShell에서 BCD를 읽을 수 없다.
- F12에서 선택하는 Ubuntu 항목과 BCD firmware entry를 확실히 연결할 수 없다.
- BitLocker 상태가 모든 관련 볼륨에서 명확하지 않다.
- 현재 기본 부팅 대상과 firmware boot order를 백업하지 않았다.
- WOL 서버가 사용할 정확한 SSH key의 권한과 제한을 확인하지 못했다.
- wrapper가 호출자에게 GUID 또는 임의 PowerShell 인수를 받는다.
- `set-ubuntu-once`가 설정 결과를 재조회하지 않고 성공을 반환한다.

## 2. 관리자 읽기 전용 점검과 백업

관리자 PowerShell에서 다음 내용을 먼저 확인한다.

```powershell
bcdedit /enum firmware /v
bcdedit /enum all /v
manage-bde -status
Confirm-SecureBootUEFI
Get-Service sshd
Get-NetTCPConnection -State Listen -LocalPort 22
```

변경 전에는 Git 저장소 밖의 관리자 전용 디렉터리에 다음 항목을 시각이 포함된 이름으로 백업한다.

- `bcdedit /export`로 내보낸 BCD 백업
- `bcdedit /enum firmware /v` 및 `/enum all /v` 결과
- 현재 `%ProgramData%\ssh\sshd_config`
- `%ProgramData%\ssh\administrators_authorized_keys` 원본과 ACL 정보
- 현재 OpenSSH 방화벽 규칙

백업 디렉터리는 Administrators와 SYSTEM만 접근하도록 제한한다. private key는 새로 복사하거나 보고서에 첨부하지 않는다.

확인 결과는 다음 기준을 충족해야 한다.

- F12의 Ubuntu 항목 설명, BCD entry, EFI device/path가 서로 일치한다.
- Ubuntu entry의 실제 GUID는 Windows wrapper 내부에만 보관한다.
- 현재 기본 부팅 대상과 order가 기록돼 있다.
- 사용자 확인과 별개로 `manage-bde -status`에서 BitLocker 비활성 상태가 확인된다.
- Secure Boot 상태를 기록하되 이 기능을 위해 변경하지 않는다.

## 3. BootNext 전용 SSH 권한 구성

BootNext에는 기존 종료·재부팅 명령용 key와 분리된 전용 key를 권장한다. 현재 `app/targets.json`의 기존 전원 명령은 별도 legacy key와 임의 PowerShell 명령 형식을 사용할 수 있으므로, 기존 key를 아래 4개 명령 전용으로 즉시 제한하면 기존 종료·재부팅이 중단될 수 있다.

적용 원칙은 다음과 같다.

- BootNext 전용 public key만 Windows에 추가한다.
- 해당 key는 WOL 서버의 고정 LAN 또는 Tailnet 주소에서만 허용한다.
- PTY, agent forwarding, port forwarding, X11 forwarding을 허용하지 않는다.
- key는 관리자 소유의 forced-command wrapper 또는 동등한 JEA endpoint만 호출한다.
- wrapper 파일과 내부 설정은 Administrators와 SYSTEM만 쓰기 가능해야 한다.
- 호출자가 GUID, 경로, 명령 또는 추가 인수를 전달할 수 없어야 한다.
- 기존 전원 제어 key는 별도로 유지하고 동작을 확인한다. 통합은 프로젝트의 기존 shutdown/reboot 계약까지 함께 변경한 뒤 별도 작업으로 진행한다.

Administrators 그룹 계정은 일반 사용자 프로필이 아니라 `%ProgramData%\ssh\administrators_authorized_keys`를 사용할 수 있으므로 실제 적용 파일과 ACL을 관리자 권한으로 확인한다. key 본문은 화면 캡처나 보고서에 남기지 않는다.

## 4. Windows wrapper 계약

wrapper는 아래 명령만 exact match로 허용하고, 추가 인수가 있으면 거부한다.

| 입력 명령 | 성공 출력 | Windows 내부 요구 동작 |
| --- | --- | --- |
| `probe-windows` | `WINDOWS_READY_V1` | wrapper와 고정 Ubuntu entry를 읽기 전용으로 검증 |
| `set-ubuntu-once` | `BOOTNEXT_SET_V1` | 검증된 Ubuntu entry를 다음 1회 부팅으로 설정한 뒤 재조회 |
| `clear-ubuntu-once` | `BOOTNEXT_CLEARED_V1` | 일회성 설정을 제거한 뒤 재조회 |
| `reboot` | `REBOOT_ACCEPTED_V1` | 표식을 먼저 반환한 뒤 지연·비동기 재부팅 |

추가 요구사항:

- 성공 시 표식 한 줄만 stdout으로 반환한다.
- 실패 시 non-zero exit code를 사용하고 GUID, EFI 경로, BCD 출력, 실행 명령을 반환하지 않는다.
- `probe-windows`는 고정 entry가 실제로 조회되고 wrapper 권한이 유효할 때만 성공한다.
- `set-ubuntu-once`는 현재 기본 boot order를 영구 변경하지 않는다.
- `clear-ubuntu-once`는 설정이 없더라도 안전한 상태임을 재확인한 뒤 성공할 수 있어야 한다.
- `reboot`는 BootNext 설정 여부를 독자적으로 추측하지 않고 wrapper의 안전 조건을 검사한다.
- wrapper 로그에도 GUID, key, 원격 명령 원문과 전체 BCD 출력은 남기지 않는다.

프로젝트는 Windows PowerShell 설치 스크립트나 GUID를 제공하지 않는다. wrapper의 구현과 관리자 ACL 적용은 Windows 관리자가 담당한다.

## 5. OpenSSH와 방화벽 보완

기존 감사 결과에서는 `sshd`가 모든 인터페이스의 TCP 22에서 수신하고 방화벽 원격 주소도 `Any`였다. 적용 후 다음 상태를 목표로 한다.

- TCP 22 인바운드는 WOL 서버의 필요한 주소 범위로 제한한다.
- 사용하지 않는 password 인증은 비활성 여부를 확인한다.
- 운영 `LogLevel`은 장애 분석에 필요한 수준으로 낮춘다. 기존 `DEBUG3`는 상시 운영에 사용하지 않는다.
- 설정 변경 전 `sshd_config`를 백업하고, 변경 후 유효 설정과 서비스 상태를 확인한다.
- 잘못된 SSH 설정이면 재시작하지 말고 백업과 diff를 먼저 확인한다.
- 로컬 콘솔 접근이 가능한 상태에서 `sshd` 재시작과 새 SSH 세션 시험을 수행한다.

방화벽을 제한한 뒤에도 WOL 서버에서만 접속되고 다른 LAN/Tailnet 장비에서는 차단되는지 확인한다.

## 6. 승인 단계별 시험

### 단계 A — 변경 없는 연결 시험

Windows가 실행 중일 때 WOL 서버 컨테이너에서 다음 명령이 정확히 한 줄을 반환해야 한다.

```bash
ssh -F /run/wol-ssh/config mainpc-windows probe-windows
```

예상 출력:

```text
WINDOWS_READY_V1
```

동시에 Ubuntu alias의 `uname -s`는 성공하면 안 된다. exit code 0이어도 출력이 exact token과 다르면 실패로 처리한다.

### 단계 B — BootNext 설정·해제 시험(재부팅 없음)

BCD 백업, GUID 매핑, BitLocker 확인과 사용자 승인이 모두 끝난 뒤에만 수행한다.

1. `set-ubuntu-once`를 호출해 `BOOTNEXT_SET_V1`을 확인한다.
2. 관리자 콘솔에서 BootNext가 검증된 Ubuntu entry 하나로 설정됐는지 읽기 전용으로 재확인한다.
3. 재부팅하지 말고 즉시 `clear-ubuntu-once`를 호출한다.
4. `BOOTNEXT_CLEARED_V1`을 확인한다.
5. BootNext가 제거되고 기본 boot order가 백업과 동일한지 확인한다.

토큰 불일치, 기본 order 변화 또는 해제 실패가 있으면 실제 재부팅 시험을 금지한다.

### 단계 C — 실제 부팅 시험

서버 문서의 사전 검증을 완료하고 사용자가 실제 재부팅을 승인한 뒤 아래 순서로 진행한다.

1. Windows 실행 중 포털에서 `Ubuntu로 켜기`를 한 번만 실행한다.
2. `set-ubuntu-once` 성공 후 Windows가 재부팅되는지 확인한다.
3. Ubuntu SSH에서 `uname -s`가 정확히 `Linux`를 반환하는지 확인한다.
4. 다음 일반 부팅에서 기존 기본 OS로 복귀하는지 확인한다.
5. F12 수동 선택과 기존 Windows 종료·재부팅 기능도 그대로 동작하는지 확인한다.

## 7. Windows 작업 완료 보고서 양식

Windows 측 에이전트는 값 자체가 아니라 판정만 작성한다.

| 항목 | 결과 | 비고 |
| --- | --- | --- |
| 관리자 BCD 조회 | PASS/FAIL | GUID 기록 금지 |
| F12 Ubuntu entry 매핑 | PASS/FAIL | 설명·경로 원문 기록 금지 |
| BCD 백업 | PASS/FAIL | 저장소 밖 보관 |
| BitLocker 비활성 독립 확인 | PASS/FAIL | 관련 볼륨 전체 |
| 기본 boot order 기록 | PASS/FAIL | 원문 저장소 커밋 금지 |
| 전용 key와 forced wrapper | PASS/FAIL | key 본문 기록 금지 |
| wrapper 파일 ACL | PASS/FAIL | 관리자 쓰기 전용 |
| 방화벽 source 제한 | PASS/FAIL | 실제 주소 기록 생략 가능 |
| `probe-windows` exact token | PASS/FAIL | 토큰만 기록 |
| set → clear 무재부팅 시험 | PASS/FAIL/NOT RUN | 사전 승인 필수 |
| 기존 shutdown/reboot 회귀 시험 | PASS/FAIL | legacy key 분리 확인 |
| 실제 Ubuntu 부팅 시험 | PASS/FAIL/NOT RUN | 최종 승인 후 |
| 다음 부팅 기본 OS 복귀 | PASS/FAIL/NOT RUN | 영구 order 불변 확인 |

최종 판정은 `GO`, `NO-GO`, `GO WITH UBUNTU_BOOT_ENABLED=false` 중 하나로 남긴다. 하나라도 필수 항목이 실패하면 서버의 `UBUNTU_BOOT_ENABLED`는 `false`로 유지한다.
