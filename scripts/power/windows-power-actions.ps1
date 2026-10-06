# Invoke after existing function definitions using & and exit $LASTEXITCODE.
# The caller dispatches only shutdown/reboot-windows to this handler.
if (@('shutdown', 'reboot-windows') -ccontains $env:SSH_ORIGINAL_COMMAND) {
    try {
        $shutdownExe = Join-Path $env:SystemRoot 'System32\shutdown.exe'
        if (-not (Test-Path -LiteralPath $shutdownExe -PathType Leaf)) {
            throw 'shutdown_executable_missing'
        }
        if ($env:SSH_ORIGINAL_COMMAND -ceq 'reboot-windows') {
            $windowsGuid = '{9dea862c-5cdd-4e70-acc1-f32b344d4795}'
            $entry = Invoke-Bcd -Arguments @('/enum', '{bootmgr}', '/v')
            if ($entry -notmatch '(?im)^\s*path\s+\\EFI\\Microsoft\\Boot\\bootmgfw\.efi\s*$') {
                throw 'invalid_windows_boot_path'
            }
            [void](Invoke-Bcd -Arguments @('/set', '{fwbootmgr}', 'bootsequence', '{bootmgr}'))
            $firmware = Get-FirmwareManager
            $pattern = '(?im)^\s*bootsequence\s+' + [regex]::Escape($windowsGuid) + '\s*$'
            if ($firmware -notmatch $pattern) { throw 'windows_bootnext_verification_failed' }
            $arguments = '/r /t 10 /d p:0:0 /c "portal-wol Windows reboot"'
            $token = 'REBOOT_ACCEPTED_V1'
        }
        else {
            $arguments = '/s /t 10 /d p:0:0 /c "portal-wol shutdown"'
            $token = 'SHUTDOWN_ACCEPTED_V1'
        }
        $process = Start-Process -FilePath $shutdownExe -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw 'power_schedule_failed' }
        [Console]::Out.WriteLine($token)
        exit 0
    }
    catch {
        [Console]::Error.WriteLine($_.Exception.Message)
        exit 1
    }
}
