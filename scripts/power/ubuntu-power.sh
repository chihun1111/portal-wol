#!/bin/sh
# Install root-owned at /usr/local/sbin/portal-wol-power.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ "$#" -eq 1 ] || exit 64
case "$1" in
    shutdown) operation=poweroff; token=SHUTDOWN_ACCEPTED_V1 ;;
    reboot-windows)
        operation=reboot; token=REBOOT_ACCEPTED_V1
        efi=$(command -v efibootmgr)
        windows_id=$("$efi" | /usr/bin/awk '$1 ~ /^Boot[[:xdigit:]][[:xdigit:]][[:xdigit:]][[:xdigit:]]\*?$/ && $2 == "Windows" && $3 == "Boot" && $4 == "Manager" { print substr($1, 5, 4) }')
        case "$windows_id" in
            [[:xdigit:]][[:xdigit:]][[:xdigit:]][[:xdigit:]]) ;;
            *) printf '%s\n' 'Expected exactly one Windows Boot Manager entry' >&2; exit 1 ;;
        esac
        "$efi" -n "$windows_id" >/dev/null
        ;;
    *) exit 64 ;;
esac
# Delay the operation so the SSH client receives the acceptance token first.
/usr/bin/systemd-run --quiet --unit="portal-wol-$1" --on-active=3s --collect \
    /usr/bin/systemctl "$operation"
printf '%s\n' "$token"
