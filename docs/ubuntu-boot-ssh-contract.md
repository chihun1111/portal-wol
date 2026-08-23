# Ubuntu 선택 부팅 SSH 계약

이 문서는 WOL 서버 컨테이너와 듀얼부트 `mainpc` 사이의 SSH 인터페이스만 정의한다. Windows wrapper, firmware GUID, ACL과 authorized key 적용은 Windows 관리자가 담당한다.

## WOL 서버 SSH 설정

컨테이너는 호스트의 `secrets/ssh/`를 `/run/wol-ssh:ro`로 읽는다. 이 디렉터리는 Git에 포함하지 않으며 최소한 `config`, OS별 known_hosts와 필요한 private key를 가진다.

Windows와 Ubuntu가 같은 IP를 사용하므로 각 alias에 별도의 host key 저장소를 사용한다.

```sshconfig
Host mainpc-windows
    HostName 192.0.2.10
    User wolsvc
    IdentityFile /run/wol-ssh/windows_ed25519
    UserKnownHostsFile /run/wol-ssh/known_hosts_windows
    HostKeyAlias mainpc-windows
    IdentitiesOnly yes
    BatchMode yes
    StrictHostKeyChecking yes
    ConnectTimeout 5

Host mainpc-ubuntu
    HostName 192.0.2.10
    User ubuntu-user
    IdentityFile /run/wol-ssh/ubuntu_ed25519
    UserKnownHostsFile /run/wol-ssh/known_hosts_ubuntu
    HostKeyAlias mainpc-ubuntu
    IdentitiesOnly yes
    BatchMode yes
    StrictHostKeyChecking yes
    ConnectTimeout 5
```

예시 IP와 사용자명은 실제 값으로 바꾸되 키, 실제 주소, firmware GUID를 저장소에 기록하지 않는다. 파일은 컨테이너 실행 UID만 읽을 수 있게 설정한다.

## Windows 고정 명령

Windows authorized key 또는 JEA/관리자 소유 wrapper는 아래 명령만 허용해야 한다. 호출자가 GUID나 임의 인수를 전달할 수 있으면 안 된다.

| 명령 | 정확한 성공 출력 | 요구 동작 |
| --- | --- | --- |
| `probe-windows` | `WINDOWS_READY_V1` | Windows와 제한 wrapper가 준비됐는지 확인 |
| `set-ubuntu-once` | `BOOTNEXT_SET_V1` | 검증된 Ubuntu entry를 다음 1회 부팅으로 설정하고 재조회 검증 |
| `clear-ubuntu-once` | `BOOTNEXT_CLEARED_V1` | 재부팅 실패 시 일회성 설정 제거 후 재조회 검증 |
| `reboot` | `REBOOT_ACCEPTED_V1` | 성공 표식을 먼저 반환한 뒤 비동기로 재부팅 |

성공 출력은 표식 한 줄만 반환한다. stderr, BCD 출력, GUID와 경로는 반환하지 않는다. 실패 시 non-zero exit code만 사용한다.

## Ubuntu 판별

Ubuntu alias는 다음 명령이 exit code 0과 정확한 출력 `Linux`를 반환해야 한다.

```bash
ssh -F /run/wol-ssh/config mainpc-ubuntu 'uname -s'
```

## 활성화 전 수동 확인

컨테이너 또는 동일한 read-only SSH 구성에서 다음을 확인한다.

```bash
ssh -F /run/wol-ssh/config mainpc-windows probe-windows
ssh -F /run/wol-ssh/config mainpc-ubuntu 'uname -s'
```

각 OS가 실행 중일 때 해당 alias만 성공해야 한다. Windows에서 `set-ubuntu-once`와 `reboot`는 관리자 BCD 백업과 사용자 승인 전에는 호출하지 않는다. 모든 확인이 끝난 뒤 `.env`의 `UBUNTU_BOOT_ENABLED=true`를 적용한다.
