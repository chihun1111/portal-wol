# Windows/UEFI 선택 부팅 자동화 환경 감사 보고서

- 작성일: 2026-08-23 (Asia/Seoul)
- 대상 PC: `Chihun-Desktop` / 저장소 대상명 `mainpc`
- 대상 저장소: `https://github.com/chihun1111/portal-wol`
- 점검 기준 커밋: `d2a7ee3436fc272a634817dc4e72e881ffe0707f`
- 점검 방식: 읽기 전용 조사 및 코드 대조
- 최종 판정: **조건부 보류(NO-GO)** — 구현 가능성은 높으나, 관리자 권한의 BCD/BitLocker 조회와 실제 `wolsvc` SSH 권한 검증 전에는 BootNext 설정이나 재부팅을 실행하면 안 됨

## 1. 작업 범위와 안전 준수

이번 점검에서는 다음 작업만 수행했다.

- 현재 Windows의 펌웨어 모드, 디스크/파티션, Secure Boot, 최대 절전/빠른 시작, OpenSSH 서비스·방화벽·계정 상태 조회
- 저장소 `main` 최신본의 부팅/전원 API, 프런트엔드, 배포 설정 검토
- 저장소의 `mainpc` 네트워크 정보와 현재 PC의 LAN 정보가 일치하는지 확인
- Microsoft 공식 문서로 BCDEdit 일회성 부팅 순서와 Windows OpenSSH 관리자 키 동작 확인

다음 작업은 수행하지 않았다.

- `bcdedit /set`, `bcdedit /bootsequence`, `/default`, `/displayorder` 등 BCD 변경
- EFI 파티션 마운트·파일 변경, UEFI 설정 변경
- 종료·재부팅·WOL 또는 원격 SSH 로그인 시험
- 서비스, 방화벽, 사용자, 키, 레지스트리 변경
- BitLocker, Secure Boot, 빠른 시작 설정 변경
- 저장소 소스 수정·커밋·푸시

Private key, public key 본문, 암호, 토큰, MAC 주소, 펌웨어 GUID는 수집 보고서에 기록하지 않았다.

## 2. 요약 결론

현재 PC는 저장소의 `mainpc` 대상과 LAN IPv4가 일치하므로 실제 조사 대상 PC로 판단된다. Windows는 UEFI 모드이며 Secure Boot가 활성화되어 있다. Windows용 GPT 디스크 외에 별도의 EFI 시스템 파티션과 Linux filesystem 파티션이 확인되어 Ubuntu 듀얼부트 설치도 구조적으로 확인된다.

일회성 Ubuntu 부팅 자동화에는 Microsoft가 제공하는 `bcdedit /bootsequence`를 사용할 가능성이 높다. 이 명령은 다음 한 번의 부팅 순서만 지정하고 이후 원래 순서로 돌아가도록 설계되어 있다. 그러나 현재 Codex 세션은 관리자 그룹 계정으로 실행 중이지만 UAC 비승격(중간 무결성) 토큰이므로 BCD, BitLocker, EFI 파일, 관리자 authorized key를 읽을 수 없었다. 따라서 Ubuntu firmware entry의 GUID·설명·EFI 경로와 `wolsvc` SSH 세션의 실제 BCD 변경 권한은 아직 확인되지 않았다.

또한 현재 애플리케이션은 인증 없는 전원/대상 관리 API, 동기식 15초 명령 실행, 일반 온라인 판별만 제공한다. Ubuntu 선택 부팅에 필요한 장기 작업 상태 머신, 대상별 잠금, 단계별 제한 시간, 취소, OS 전용 성공 판별 및 민감 정보 로그 제거가 없다. 이 상태에서 BootNext 명령만 추가하면 오작동과 권한 남용 위험이 크다.

## 3. Windows 환경 조사 결과

### 3.1 대상 식별

| 항목 | 결과 | 판정 |
|---|---|---|
| 컴퓨터 이름 | `Chihun-Desktop` | 확인 |
| 현재 사용자 | 로컬 관리자 그룹 구성원 | 확인 |
| 현재 토큰 | UAC 비승격, Medium integrity, Administrators SID는 deny-only | 관리자 전용 조회 불가 원인 |
| LAN 주소 | 저장소 `mainpc`의 IP와 현재 Ethernet IPv4가 일치 | 실제 대상 PC로 판단 |
| Tailscale | Tailscale 인터페이스와 별도 주소 존재 | 접근 범위 설계에 활용 가능 |

정확한 IP/MAC은 보고서에서 반복 노출하지 않았다.

### 3.2 Windows·펌웨어·디스크

| 항목 | 확인 결과 | 의미 |
|---|---|---|
| 펌웨어 모드 | `UEFI` | UEFI firmware entry 기반 일회성 부팅 가능성 있음 |
| OS 표시 정보 | Professional, DisplayVersion `25H2`, build `26200.9168` | 레지스트리 ProductName은 `Windows 10 Pro`로 표시되지만 빌드 정보를 함께 기준으로 삼아야 함 |
| Secure Boot | 레지스트리 `UEFISecureBootEnabled=1` | 활성화 확인 |
| Windows 디스크 | GPT, Windows boot/system 디스크 확인 | 정상 |
| 추가 디스크 | 별도 GPT 디스크에 EFI System Partition과 Linux filesystem GUID 파티션 존재 | Ubuntu 듀얼부트 구조 확인 |
| EFI System Partition | 총 2개 | Windows ESP와 Ubuntu 측 ESP로 추정되나 관리자 확인 필요 |

`Confirm-SecureBootUEFI`는 비승격 권한으로 거부됐지만, 읽기 가능한 Secure Boot 상태 레지스트리 값으로 활성 상태를 교차 확인했다.

### 3.3 BCD·Ubuntu firmware entry·BitLocker

| 확인 항목 | 결과 | 상태 |
|---|---|---|
| `bcdedit /enum firmware /v` | Access denied | 미확정 |
| `bcdedit /enum all /v`에 필요한 시스템 BCD 접근 | 레지스트리 접근 거부 | 미확정 |
| EFI 볼륨의 `EFI` 디렉터리 읽기 | Access denied | Ubuntu EFI 경로 미확정 |
| `manage-bde -status` | 관리자 권한 필요로 실패 | 사용자가 BitLocker 꺼짐을 알려줬으나 독립 검증 미완료 |
| 현재 기본 부팅 대상 | 확인 불가 | Windows Boot Manager/GRUB 여부 미확정 |
| Ubuntu firmware entry GUID | 확인 불가 | **구현 전 필수 차단 항목** |

두 EFI 파티션과 Linux 파티션은 존재하지만, 이것만으로 F12의 Ubuntu 항목과 특정 GUID/EFI 파일을 안전하게 연결할 수 없다. 추정 GUID를 사용하면 안 된다.

### 3.4 최대 절전·빠른 시작

| 항목 | 결과 | 판정 |
|---|---|---|
| `HibernateEnabled` | `0` | 최대 절전 비활성 |
| `HiberbootEnabled` | `0` | 빠른 시작 비활성 |
| `powercfg /availablesleepstates` | 최대 절전과 빠른 시작 사용 불가 | WOL/듀얼부트 관점에서 유리 |

현재 상태에서는 Windows 빠른 시작이 Ubuntu 파일시스템 접근이나 완전 종료를 방해할 위험이 낮다.

## 4. Windows OpenSSH와 `wolsvc` 조사

### 4.1 서비스·네트워크

| 항목 | 결과 |
|---|---|
| OpenSSH 버전 | `OpenSSH_for_Windows_9.5p2` |
| `sshd` 서비스 | Running, Automatic, LocalSystem |
| 수신 주소 | IPv4 `0.0.0.0:22`, IPv6 `[::]:22` |
| 방화벽 규칙 | Inbound Allow, Profile Any, Local/Remote address Any, TCP 22 |

현재 22번 포트는 모든 로컬 인터페이스와 모든 원격 주소에 허용된다. 실제 운영 요구가 WOL 서버 한 대 또는 Tailnet으로 제한된다면 방화벽의 원격 주소/프로필 범위를 줄여야 한다.

### 4.2 계정과 권한

| 항목 | 결과 | 해석 |
|---|---|---|
| `wolsvc` | Enabled, local account | 사용 중 |
| 로컬 Administrators 구성원 | 예 | 높은 권한 계정 |
| 마지막 로그인 | 기록 있음 | 과거 원격 제어 사용 정황 |
| `PasswordRequired` | False | 계정 정책 플래그이며 암호가 비어 있다는 증거는 아님; `PasswordLastSet`은 존재 |
| UAC | 활성 |
| `LocalAccountTokenFilterPolicy` | 명시값 없음 | 실제 SSH 세션의 관리자 토큰/BCD 접근은 별도 실증 필요 |

관리자 그룹 구성원이라는 사실만으로 SSH 명령이 BCD를 변경할 수 있다고 단정할 수 없다. WOL 서버에서 사용하는 정확한 키와 `wolsvc`로 접속한 세션에서 `whoami /all` 및 읽기 전용 `bcdedit /enum firmware /v`가 성공해야 권한이 입증된다.

### 4.3 SSH 설정과 authorized key

활성 `sshd_config`에서 확인된 주요 항목:

```text
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
StrictModes no
LogLevel DEBUG3
```

추가로 `AllowUsers`, `AllowGroups`, `DenyUsers`, `DenyGroups`, `Match`, `ForceCommand`, `PasswordAuthentication`의 명시 설정은 없었다.

Microsoft 공식 문서에 따르면 Windows OpenSSH에서 사용자가 Administrators 그룹 구성원이면 사용자 프로필의 `authorized_keys` 대신 `%ProgramData%\ssh\administrators_authorized_keys`를 사용한다. 해당 파일은 존재하지만 현재 비승격 토큰으로 내용과 ACL을 읽을 수 없었다. 따라서 다음 항목은 미확정이다.

- 실제 WOL 서버 public key가 이 파일에 있는지
- key 옵션에 `command=`, `restrict`, `from=`, `no-pty`, `no-port-forwarding` 같은 제한이 있는지
- 관리자 그룹의 다른 key와 권한이 공유되는지
- SSH 로그인 후 임의 관리자 명령 실행이 가능한지

`StrictModes`는 Microsoft 문서상 Windows 기본 OpenSSH에서 지원되지 않는 설정이므로 보안 완화 효과를 기대하면 안 되고, 혼동 방지를 위해 제거 후보로 분류한다. `LogLevel DEBUG3`는 운영 환경에 과도하게 상세하므로 인증 문제 해결이 끝났다면 낮추는 편이 안전하다.

`sshd.exe -T` 유효 설정 조회는 현재 토큰이 host private key를 읽지 못해 `no hostkeys available`로 실패했다. 이는 서비스 장애가 아니라 비승격 진단 세션의 권한 제한이다.

## 5. 저장소 코드와 실제 환경 대조

### 5.1 일치하는 부분

- `app/targets.json`의 `mainpc` IP와 현재 PC의 LAN IP가 일치한다.
- 대상의 shutdown/reboot 명령은 `wolsvc`와 SSH private key 경로를 사용하며, 실제 Windows에는 `wolsvc`와 실행 중인 OpenSSH 서버가 있다.
- Windows 빠른 시작과 최대 절전은 이미 꺼져 있어 완전 종료 후 WOL 흐름에 적합하다.
- 듀얼부트 디스크 구조와 UEFI 모드는 일회성 선택 부팅 자동화 전제에 부합한다.

### 5.2 구현상 부족한 부분

| 영역 | 현재 상태 | 필요한 상태 |
|---|---|---|
| API 인증 | `app/api/routes.py`의 관리·전원 API에 인증 dependency 없음 | Tailnet identity 또는 애플리케이션 토큰 검증, 권한 분리 |
| 요청 처리 | shutdown/reboot가 HTTP 요청 안에서 동기 실행 | 백그라운드 job + `202` + job 조회 |
| 제한 시간 | `app/services/power.py` 기본 15초 | 단계별/전체 제한 시간과 재시도 |
| 중복 방지 | 로그/targets 파일 lock만 존재 | 대상별 boot job lock |
| OS 판별 | ping 또는 TCP 3389/445/22 중 하나 | Windows 전용 SSH 확인 + Ubuntu 전용 서비스/host key 확인 |
| BootNext | API·서비스 없음 | 검증된 GUID를 쓰는 제한된 일회성 명령 |
| 작업 복구 | job 영속 상태 없음 | 서버 재시작 시 진행 job을 failed/recoverable로 정리 |
| 로그 | 명령 설명·stdout·stderr를 그대로 기록/응답 가능 | 키 경로·GUID·토큰·명령 세부 정제, 안전한 오류 코드만 노출 |
| 프런트엔드 | `PowerAction`이 wake/shutdown/reboot로 고정 | Ubuntu boot action, 확인창, 단계 진행/취소/오류 표시 |
| 종료 확인 | delete만 확인 모달 | shutdown/reboot/Ubuntu boot에 명시적 확인 |

특히 `app/services/power.py`는 렌더링된 명령 설명과 stdout/stderr를 로그 및 API 응답에 포함한다. 새 부팅 명령을 같은 경로에 단순 추가하면 firmware GUID, 내부 경로 또는 운영 세부 정보가 노출될 수 있으므로 boot job용 제한 실행기와 로그 정제가 필요하다.

### 5.3 배포 차이

- `systemd/wol-web.service`는 `/srv/wol-core`, `User=ubuntu`로 고정돼 있다.
- `scripts/setup_ubuntu.sh` 원격 기본 경로는 `~/wol-web`이고 README 예시는 `/opt/wol-web`이다.
- systemd와 Docker 모두 `0.0.0.0:8000`을 사용하므로 동시에 실행할 수 없다.
- Docker production volume에는 `.env`와 logs만 있고 Windows 제어용 SSH key/known_hosts가 없다.

운영 방식과 설치 경로를 확정하기 전에는 부팅 자동화 기능의 파일/키 위치도 확정할 수 없다.

## 6. 위험 목록과 우선순위

### 긴급/높음

1. **인증 없는 전원·대상 관리 API**: 포트 접근자는 target 수정·삭제와 전원 명령을 호출할 수 있다.
2. **`wolsvc`가 로컬 관리자**: authorized key 제한이 없으면 키 보유자가 광범위한 관리자 명령을 실행할 수 있다.
3. **Ubuntu firmware GUID 미확정**: 잘못된 entry 사용 시 원치 않는 부팅 또는 실패가 발생한다.
4. **실제 SSH 토큰 권한 미확정**: BootNext 성공 여부를 알 수 없고, 실패 후 재부팅하면 기본 Windows로 돌아갈 수 있다.
5. **작업 상태/잠금 부재**: 버튼 중복 실행과 여러 BootNext 요청 경합 가능성이 있다.
6. **OS 판별 부정확**: TCP 22는 Windows와 Ubuntu 모두에서 열릴 수 있어 성공 판별에 사용할 수 없다.

### 중간

1. OpenSSH 방화벽이 모든 프로필·모든 원격 주소에 열려 있다.
2. 운영 SSH 로그가 `DEBUG3`다.
3. systemd 설치 경로와 설치 스크립트 기본값이 다르다.
4. Docker 배포에는 원격 Windows 제어 키/host key 검증 구성이 없다.
5. 실제 장비 식별 정보와 SSH key 경로가 포함된 `app/targets.json`이 Git에 추적된다.
6. 두 EFI 파티션이 있어 GUID와 파일 경로의 명시적 매핑이 필수다.

## 7. 구현 전 필수 관리자 확인

관리자 PowerShell에서 먼저 아래 **읽기 전용** 항목을 확인하고 결과를 별도 보관한다.

```powershell
bcdedit /enum firmware /v
bcdedit /enum all /v
manage-bde -status
Confirm-SecureBootUEFI
```

확인 기준:

1. F12 화면의 Ubuntu 설명과 firmware entry 설명·GUID·device/path를 연결한다.
2. 해당 경로가 실제 Ubuntu ESP의 `shimx64.efi`, `grubx64.efi` 등과 일치하는지 확인하되 파일을 변경하지 않는다.
3. 현재 기본 boot manager/order를 기록한다.
4. BitLocker가 모든 관련 볼륨에서 실제로 꺼져 있는지 확인한다.
5. `%ProgramData%\ssh\administrators_authorized_keys`의 키 본문을 복사하지 말고, WOL 서버 키 한 줄에 강제 명령·source 제한·PTY/forwarding 제한이 있는지만 확인한다.
6. WOL 서버에서 정확한 `wolsvc` 키로 접속해 `whoami /all`과 읽기 전용 BCD enum이 성공하는지 확인한다.
7. Ubuntu 부팅 후 확인할 고유 서비스, SSH host key 또는 제한 health endpoint를 확정한다.

이 7개가 끝나기 전에는 구현을 시작하지 않는 것이 안전하다.

## 8. 권장 권한 모델

권장 순서는 다음과 같다.

1. 전체 관리자 shell을 직접 허용하지 않는다.
2. `wolsvc` key는 WOL 서버의 고정 주소에서만 허용한다.
3. key에 강제 명령을 연결해 허용된 동작을 `probe-windows`, `set-ubuntu-once`, `reboot`처럼 좁힌다.
4. 강제 명령 스크립트는 고정된 검증 완료 GUID만 사용하고, 호출자가 GUID나 임의 command를 전달할 수 없게 한다.
5. `set-ubuntu-once`가 BCD 결과를 재조회해 성공을 확인한 경우에만 reboot를 허용한다.
6. stdout에는 상태 코드만 반환하고 GUID, 경로, key, token을 출력하지 않는다.
7. API 쪽에서도 대상별 동시 작업을 하나로 제한하고 재부팅 전까지만 취소를 허용한다.

JEA를 사용할 수 있다면 제한 endpoint로 구성하고, 그렇지 않으면 관리자 소유·일반 사용자 쓰기 금지 ACL의 전용 PowerShell wrapper와 authorized key 강제 명령 조합을 권장한다.

## 9. 예상 변경 파일

### 백엔드

- `app/api/routes.py`: boot job 생성/조회/취소 API 및 인증 dependency
- `app/main.py`: job manager 시작·종료 lifecycle
- `app/core/settings.py`: 인증·시간 제한·Windows/Ubuntu probe 설정
- `app/services/power.py`: 일반 전원 명령과 제한 boot 실행 분리, 로그 정제
- `app/services/logs.py`: 민감 필드 redaction
- `app/services/boot_jobs.py`(신규 권장): 상태 머신, 대상별 lock, timeout, cancel, 재시도, 재시작 복구
- `app/services/os_probe.py`(신규 권장): Windows/Ubuntu 고유 판별
- `app/targets.example.json`(신규 권장): 실제 장비 정보 없는 예제
- `tests/test_boot_jobs.py`, `tests/test_auth.py`, `tests/test_os_probe.py`: 신규 테스트

### 프런트엔드

- `web/app/(management)/wol/_lib/types.ts`: boot action/job 타입
- `web/app/(management)/wol/_lib/constants.ts`: API endpoint
- `web/app/(management)/wol/page.tsx`: job 생성·polling·cancel
- `web/app/(management)/wol/_components/TargetsCard.tsx`: Ubuntu로 켜기 버튼
- boot 확인/진행 modal 신규 컴포넌트
- `web/app/_i18n/translations/ko.json`, `en.json`: 라벨·단계·오류 번역

### 배포·문서

- `systemd/wol-web.service`: 경로/사용자 템플릿화 및 hardening
- `scripts/setup_ubuntu.sh`: 실제 설치 경로와 service 파일 일치
- `docker/compose.prod.yml`: Docker 선택 시 read-only key/known_hosts 구성 또는 기능 비활성화
- `.env.example`, `README.md`: 인증, 운영 모드, Ubuntu probe, rollback 문서화
- Windows 측 제한 wrapper/JEA 구성은 별도 배포 디렉터리에서 관리하고 private key나 실제 GUID는 Git에 넣지 않는다.

## 10. 단계별 검증 계획

### 단계 A — 변경 없는 기준선

1. 관리자 BCD/firmware/BitLocker 출력 보관
2. OpenSSH 관리자 key 제한과 ACL 확인
3. WOL 서버 → `wolsvc` 읽기 전용 BCD enum 확인
4. 현재 Windows 기본 부팅과 F12 Ubuntu entry 매핑
5. Ubuntu 고유 health 판별 수단 확정

### 단계 B — 코드 검증

1. API 인증 없는 요청이 `401/403`인지 확인
2. boot job 상태 전이·timeout·cancel·대상별 lock 단위 테스트
3. 모든 로그/API 응답에서 GUID·키 경로·토큰·명령 본문이 제거됐는지 확인
4. `pytest -q`, 프런트엔드 lint/test/build 실행
5. systemd 또는 Docker 하나만 선택해 서비스 시작 및 health 확인

현재 로컬 환경에는 Python과 Node.js가 있으나 `pytest` 모듈이 설치되지 않아 기존 Python 테스트는 실행하지 못했다. 이번 점검은 코드 변경이 없는 감사이므로 의존성을 설치하지 않았다.

### 단계 C — 승인 후 제한 시험

1. Windows가 켜진 상태에서 제한 wrapper의 읽기 전용 probe
2. 사용자 승인 후 검증된 GUID에만 일회성 boot sequence 설정
3. 재부팅 전 BCD를 재조회해 one-time sequence가 정확한지 확인
4. 승인 후 재부팅하고 Ubuntu 고유 health가 성공하는지 확인
5. 다음 부팅에서 원래 기본 OS로 복귀하는지 확인
6. 마지막으로 전원 OFF 상태에서 WOL부터 전체 흐름 검증

Microsoft 문서상 후보 명령 형식은 다음과 같지만, `{검증된-Ubuntu-GUID}`가 관리자 조사로 확정되고 사용자가 실제 시험을 승인한 뒤에만 사용한다.

```text
bcdedit /bootsequence {검증된-Ubuntu-GUID}
```

`/bootsequence`는 다음 한 번에만 쓰이고 이후 원래 display order로 돌아가는 명령이다. `/default`나 `/displayorder`를 바꾸지 않는다.

## 11. 실패·롤백 절차

1. 변경 전에 `bcdedit /export`로 시스템 BCD를 백업하고 enum 출력을 보관한다.
2. 일회성 sequence 설정 후 재부팅 전 검증이 실패하면 재부팅하지 않는다.
3. 검증된 GUID를 one-time sequence에서 제거할 때는 Microsoft가 문서화한 `/remove` 형식을 사용한다.

```text
bcdedit /bootsequence {검증된-Ubuntu-GUID} /remove
```

4. 애플리케이션 job은 `setting_uefi_bootnext` 성공 확인 전에는 `rebooting`으로 넘어가지 않는다.
5. API/서비스 문제는 기존 wake/shutdown/reboot 경로를 기능 flag로 유지해 boot 기능만 끌 수 있게 한다.
6. systemd 배포는 이전 unit/.env/코드 백업으로 복귀하고 `daemon-reload` 후 기존 버전을 재시작한다.
7. Docker 배포는 이전 image tag와 compose 파일로 되돌린다.
8. 예상하지 못한 부팅 실패 시 firmware F12 메뉴에서 기존 Windows entry를 수동 선택한다. 기본 순서는 영구 변경하지 않았으므로 다음 부팅 정상 복귀를 우선 확인한다.

## 12. 최종 판정과 다음 승인 지점

### 확인 완료

- 실제 대상 PC 식별
- UEFI 모드와 Secure Boot 활성
- Ubuntu 듀얼부트 디스크 구조
- 빠른 시작·최대 절전 비활성
- OpenSSH 서비스, 방화벽, `wolsvc` 관리자 그룹 구성
- 현재 코드의 인증/장기 작업/OS 판별/배포 공백

### 아직 확인 필요

- BitLocker 실제 상태
- F12 Ubuntu entry의 정확한 GUID·설명·EFI 경로
- 현재 기본 부팅 대상과 firmware order
- 관리자 authorized key의 제한 옵션과 ACL
- `wolsvc` SSH 세션에서 읽기 전용 BCD 접근 및 향후 제한 명령 수행 가능 여부
- Ubuntu 고유 성공 판별 방법
- API 인증 방식과 systemd/Docker 운영 방식

따라서 현재 승인 가능한 다음 작업은 **관리자 권한의 읽기 전용 확인과 그 결과 검토**까지다. BCD 변경, 실제 재부팅 또는 애플리케이션 구현은 위 미확정 사항을 해소한 보고서를 검토한 후 별도 승인받아 진행해야 한다.

## 13. 공식 참고 자료

- Microsoft Learn — BCDEdit `/bootsequence`: https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/bcdedit--bootsequence
- Microsoft Learn — BCDEdit command-line options: https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/bcdedit-command-line-options?view=windows-11
- Microsoft Learn — OpenSSH Server Configuration for Windows: https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-server-configuration
- Microsoft Learn — Key-Based Authentication in OpenSSH for Windows: https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement
