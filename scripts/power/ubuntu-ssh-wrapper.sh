#!/bin/sh
# Forced command for the source-restricted WOL SSH key.
set -eu
case "${SSH_ORIGINAL_COMMAND-}" in
    'uname -s') exec /usr/bin/uname -s ;;
    shutdown|reboot-windows)
        exec /usr/bin/sudo -n /usr/local/sbin/portal-wol-power "$SSH_ORIGINAL_COMMAND"
        ;;
    *) printf '%s\n' 'Unsupported WOL command' >&2; exit 64 ;;
esac
