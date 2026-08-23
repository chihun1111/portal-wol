# Ubuntu 선택 부팅 자동화 구현 목표

## 목표

`mainpc`가 꺼져 있으면 WOL로 Windows를 시작한 뒤 다음 1회 부팅을 Ubuntu로 지정하고 재부팅한다. 이미 Windows가 실행 중이면 WOL 단계를 생략하고, 이미 Ubuntu가 실행 중이면 재부팅 없이 성공 처리한다. 최종 성공은 Ubuntu SSH에서 `uname -s`가 `Linux`를 반환할 때만 인정한다.

## 안전 경계

- 실제 BootNext 설정과 재부팅 시험은 Windows 관리자 점검이 끝난 뒤에만 수행한다.
- 기능은 `UBUNTU_BOOT_ENABLED=false`가 기본이며 명시적으로 활성화하기 전에는 API와 UI에서 사용할 수 없다.
- 애플리케이션은 firmware GUID나 임의 PowerShell 명령을 전달하지 않는다.
- Windows는 `probe-windows`, `set-ubuntu-once`, `clear-ubuntu-once`, `reboot` 네 명령만 허용하는 제한 wrapper를 사용한다.
- 기존 기본 부팅 순서는 변경하지 않고 다음 1회 부팅만 지정한다.
- SSH 명령, firmware GUID, 키 경로, stdout/stderr는 부팅 작업 로그와 API 응답에 기록하지 않는다.

## 실행 흐름

```text
queued
→ detecting_os
→ waking
→ waiting_for_windows
→ setting_bootnext
→ rebooting
→ waiting_for_ubuntu
→ succeeded | failed | timed_out | cancelled
```

- Ubuntu SSH를 먼저 확인하고 Windows SSH를 다음으로 확인한다.
- 둘 다 응답하지 않으면 WOL을 한 번 전송하고 5초 간격으로 최대 180초 기다린다.
- BootNext 설정 성공 표식을 확인한 뒤에만 재부팅한다.
- 재부팅 후 Ubuntu SSH를 최대 300초 기다리고 전체 작업은 480초를 넘기지 않는다.
- 대상별 활성 작업은 하나만 허용하고 BootNext 설정 전까지만 취소할 수 있다.
- 서버 재시작 시 진행 중 작업은 재개하지 않고 `service_restarted`로 실패 처리한다.

## 외부 계약

Windows SSH 명령과 정확한 성공 출력은 다음과 같다.

| 명령 | 성공 출력 |
| --- | --- |
| `probe-windows` | `WINDOWS_READY_V1` |
| `set-ubuntu-once` | `BOOTNEXT_SET_V1` |
| `clear-ubuntu-once` | `BOOTNEXT_CLEARED_V1` |
| `reboot` | `REBOOT_ACCEPTED_V1` |

Ubuntu SSH는 OS별 alias와 고정 host key를 사용하며 `uname -s`의 정확한 출력 `Linux`를 확인한다.

## 배포 원칙

- Docker Compose host network를 사용하되 FastAPI는 `127.0.0.1:8000`에만 바인딩한다.
- Tailscale Serve가 도메인 루트에서 localhost 백엔드를 프록시한다.
- 모든 `/api/*` 요청은 Serve가 추가하는 `Tailscale-User-Login` header가 있어야 한다.
- SSH 설정과 키는 read-only, 작업 데이터는 영속 볼륨으로 컨테이너에 연결한다.

## 완료 기준

- 인증, 작업 상태 머신, 중복 방지, 취소, timeout, 재시작 복구와 안전한 로그가 테스트된다.
- UI에서 확인 후 작업을 시작하고 진행 상태를 복원·표시할 수 있다.
- Docker가 비루트로 실행되고 localhost 밖에서 8000 포트에 직접 접근할 수 없다.
- Windows 준비가 끝난 뒤 Windows 실행, Ubuntu 실행, 전원 OFF의 세 시작 상태를 실제로 검증한다.
