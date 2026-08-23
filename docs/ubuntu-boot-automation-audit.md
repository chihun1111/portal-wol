# Ubuntu 선택 부팅 자동화 사전 점검 보고서

- 작성일: 2026-08-23
- 대상 프로젝트: `portal-wol`
- 현재 단계: 조사 및 인수인계 문서 작성만 완료. 부팅 설정과 시스템 설정은 변경하지 않음.

## 1. 목표와 전제

대상 PC는 Windows와 Ubuntu가 설치된 듀얼 부팅 PC이며, 현재 전원을 켠 뒤 F12 부팅 메뉴에서 운영체제를 직접 선택한다.

확인된 전제:

- BitLocker는 꺼져 있다.
- 일반 WOL은 현재 MAC 주소로 전송할 수 있다.
- Windows 종료 및 재부팅은 WOL 서버에서 `wolsvc` 계정으로 SSH 접속해 PowerShell 명령을 실행하는 구조다.
- F12 메뉴의 Ubuntu 항목 ID와 실제 EFI 경로는 아직 확인하지 않았다.

희망 동작:

1. 기존 `Wake`는 현재 기본 운영체제로 부팅한다.
2. 새 `Ubuntu로 켜기` 동작은 PC가 꺼져 있으면 먼저 WOL을 보낸다.
3. Windows SSH가 준비될 때까지 기다린다.
4. 다음 한 번의 UEFI 부팅 항목을 Ubuntu로 지정한다.
5. Windows를 재부팅한다.
6. Ubuntu가 올라왔는지 별도의 판별 방법으로 확인한다.
7. 다음 부팅부터는 원래 기본 부팅 순서로 돌아간다.

## 2. 현재 프로젝트 조사 결과

### 백엔드

- `POST /api/wake`, `/api/shutdown`, `/api/reboot`만 구현되어 있다.
- `app/services/power.py`는 대상별 명령 배열과 `{name}`, `{ip}`, `{mac}` 치환을 지원한다.
- 명령 기본 제한 시간은 15초라서 WOL 후 Windows 부팅을 기다리는 장기 작업에는 맞지 않는다.
- 대상 온라인 판별은 ping 또는 TCP `3389,445,22` 중 하나만 열려 있어도 성공한다. Windows와 Ubuntu를 구분하지는 못한다.
- 동시 요청 방지, 작업 ID, 진행 상태 조회, 취소 및 단계별 재시도 기능은 없다.

### 프런트엔드

- 동작 타입이 `wake | shutdown | reboot`로 고정되어 있다.
- `Ubuntu로 켜기` 버튼, 단계별 진행 표시 및 해당 로그 타입은 없다.
- 전원 종료와 재부팅은 삭제와 달리 확인 대화상자가 없다.

### Windows 원격 제어

- `app/targets.json`의 `mainpc`는 `/srv/wol-core/secrets/wolsvc_ed25519` 키로 Windows의 `wolsvc` 계정에 접속한다.
- 현재 명령은 `Stop-Computer`와 `Restart-Computer`만 사용한다.
- `wolsvc`가 UEFI/BCD를 변경할 수 있는 관리자 권한을 가졌는지 확인되지 않았다.
- Ubuntu EFI 항목의 GUID가 확인되지 않아 지금은 `bcdedit` 변경 명령을 확정하면 안 된다.

### 배포 구성

- `systemd/wol-web.service`는 `WorkingDirectory=/srv/wol-core`, `User=ubuntu`로 고정되어 있다.
- 반면 원격 설치 스크립트 기본 경로는 `~/wol-web`이고, 로컬 실행 위치도 임의 경로일 수 있다. 서비스 파일을 그대로 복사하면 경로 또는 사용자 불일치로 실행에 실패할 수 있다.
- 서비스는 `0.0.0.0:8000`으로 수신한다. Docker 운영 구성도 host network와 `0.0.0.0:8000`을 사용한다.
- Docker 이미지에는 WOL 서버의 SSH private key가 연결되지 않아 현재 Windows 종료/재부팅 명령은 별도 볼륨 및 SSH 설정 없이는 동작하지 않는다.

### 보안상 우선 수정 항목

- 실제 FastAPI 라우트에는 인증 또는 권한 검사가 없다.
- 프런트엔드 요청 코드도 인증 헤더를 추가하지 않는다.
- README의 토큰 패널 설명과 현재 구현이 일치하지 않는다.
- 따라서 LAN이나 Tailnet에서 8000 포트에 접근할 수 있는 사용자는 타겟 수정·삭제 및 전원 명령을 직접 호출할 수 있다.
- 관리자 권한이 필요한 Ubuntu 선택 부팅을 추가하기 전에 API 인증, 요청 위조 방지 범위, 접근 네트워크를 먼저 확정해야 한다.
- `app/targets.json`이 Git에 추적되고 있으며 실제 장비의 IP/MAC 및 SSH 키 경로를 포함한다. private key 자체는 `secrets/` ignore 규칙으로 제외되어 있다.

## 3. 권장 구현 구조

단순히 긴 HTTP 요청 하나에서 `sleep`하며 기다리지 말고, 대상별 상태를 가진 백그라운드 작업으로 구현한다.

예상 상태 흐름:

```text
queued
  -> waking
  -> waiting_for_windows_ssh
  -> setting_uefi_bootnext
  -> rebooting
  -> waiting_for_ubuntu
  -> succeeded | failed | timed_out
```

필수 안전장치:

- 대상별 작업 잠금으로 버튼 중복 실행 방지
- 각 단계의 제한 시간과 전체 제한 시간
- Ubuntu BootNext 지정 성공을 확인한 뒤에만 재부팅
- 실패 시 기본 부팅 순서를 영구 변경하지 않음
- GUID, 비밀번호, 키 내용은 API 응답과 로그에 기록하지 않음
- 서버가 재시작되어도 진행 중이던 작업을 실패 또는 복구 가능 상태로 정리
- `Ubuntu로 켜기`에 명확한 확인 대화상자 제공
- OS 판별은 단순 ping이 아니라 Windows 전용 SSH 명령과 Ubuntu 전용 표식/서비스를 사용

권장 API 초안:

- `POST /api/boot/ubuntu`: 작업 생성, `202`와 작업 ID 반환
- `GET /api/jobs/{id}`: 현재 단계와 안전하게 정제된 오류 반환
- `POST /api/jobs/{id}/cancel`: 재부팅 전 대기 단계에서만 취소

## 4. Windows에서 다음에 확인할 항목

Windows 관리자 PowerShell에서 **먼저 읽기 전용으로만** 조사한다. 출력에 키, 암호, 토큰을 포함하지 않는다.

```powershell
bcdedit /enum firmware /v
bcdedit /enum all /v
manage-bde -status
Get-ComputerInfo -Property BiosFirmwareType,WindowsProductName,WindowsVersion,OsBuildNumber
Confirm-SecureBootUEFI
Get-Service sshd
Get-NetFirewallRule -DisplayName '*OpenSSH*' |
  Select-Object DisplayName,Enabled,Direction,Action,Profile
whoami
whoami /groups
```

추가 확인:

- F12 화면의 Ubuntu 항목과 `bcdedit /enum firmware /v`의 GUID·설명·EFI 경로 연결
- Windows가 UEFI 모드인지 확인
- `wolsvc`가 현재 SSH 접속 및 종료/재부팅에 실제로 사용하는 계정인지 확인
- `wolsvc`가 BCD 변경 권한을 가지는지 확인하되, 조사 단계에서는 변경 명령을 실행하지 않음
- `sshd_config`와 `authorized_keys`에서 `wolsvc`가 임의 관리자 명령을 실행할 수 있는 구조인지 확인
- Windows 빠른 시작과 최대 절전모드 상태 확인
- Ubuntu 부팅 후 SSH 등 Ubuntu 전용 확인 수단의 주소·포트·호스트키 확인

## 5. 구현 전 결정할 사항

1. `Ubuntu로 켜기`가 꺼진 PC뿐 아니라 이미 Windows가 켜진 상태에서도 동작해야 하는가?
2. 현재 기본 부팅 항목은 Windows인가, GRUB인가?
3. Ubuntu 부팅 성공을 무엇으로 판정할 것인가? 권장은 Ubuntu에만 존재하는 제한된 상태 확인 서비스 또는 별도 SSH 호스트키 확인이다.
4. API 보호는 Tailscale identity 기반 프록시 인증으로 할지, 애플리케이션 토큰 인증도 추가할지 결정한다.
5. Windows 측 권한은 전체 관리자 SSH보다 제한된 전용 스크립트, `authorized_keys`의 강제 명령 또는 JEA 방식 중 하나를 선택한다.
6. 실제 운영 방식은 systemd와 Docker 중 하나만 선택하고 설치 경로와 실행 사용자를 일치시킨다.

## 6. Windows 에이전트 인수인계 요청문

아래 요청을 Windows에서 실행 중인 에이전트에게 전달한다.

> `portal-wol/docs/ubuntu-boot-automation-audit.md`를 처음부터 끝까지 읽고, 저장소의 `AGENTS.md` 지침을 준수해 주세요. 먼저 Windows 및 UEFI/BCD/OpenSSH/권한/빠른 시작 상태를 읽기 전용으로 조사하고 결과를 `docs/windows-boot-environment-report.md`에 기록해 주세요. BitLocker는 사용자가 꺼져 있다고 알려줬지만 명령으로 상태만 재확인하세요. secret 값, private key, 암호, 토큰은 출력하거나 문서에 기록하지 마세요. 조사 단계에서는 `bcdedit /set`, `bcdedit /bootsequence`, 펌웨어 순서 변경, 재부팅을 실행하지 마세요. F12의 Ubuntu 항목과 firmware entry GUID 및 EFI 경로를 근거와 함께 식별하고, `wolsvc`가 필요한 제한 권한으로 다음 1회 Ubuntu 부팅과 재부팅을 수행할 수 있는지 평가하세요. 현재 프로젝트 코드와 실제 Windows 설정의 차이, 위험 요소, 필요한 변경 파일, 검증 및 롤백 절차를 보고서에 작성하세요. 구현은 보고서를 사용자에게 보여주고 명시적으로 진행 요청을 받은 뒤에만 하세요.

## 7. 한 번에 적용할 때의 검증 순서

1. Git 상태와 사용자 변경분 확인
2. 현재 설정 파일 백업 및 BCD/firmware 출력 보관
3. API 인증과 접근 범위 적용 및 검증
4. 제한된 Windows 부팅 전환 명령 준비
5. 백엔드 작업 상태 머신, 잠금, 제한 시간 및 로그 구현
6. 프런트엔드 버튼, 확인창, 진행 상태 및 번역 구현
7. 단위 테스트와 프런트엔드 lint/build 실행
8. Windows가 켜진 상태에서 BootNext 설정까지만 검증 가능한 안전 점검 수행
9. 사용자 승인 후 실제 한 번 재부팅하여 Ubuntu 진입 확인
10. 다시 Windows로 부팅되는지 확인하여 일회성 설정임을 검증
11. PC가 꺼진 상태에서 WOL부터 시작하는 전체 흐름 검증
12. 실패 및 시간 초과 시 기본 부팅 순서가 보존되는지 확인

## 8. 현재 결론

F12로 Ubuntu를 선택할 수 있으므로 자동화 가능성은 높다. 다만 현재 코드에 부팅 선택 기능만 바로 붙이면 인증 부재, OS 오판, 중복 실행 및 배포 경로 불일치 위험이 있다. Windows 환경 보고서로 정확한 EFI 항목과 권한 모델을 확정한 뒤, 보안 보완과 상태 기반 부팅 작업을 함께 적용하는 것이 안전하다.
