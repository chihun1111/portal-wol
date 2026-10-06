param([string]$Handler = "$PSScriptRoot\windows-power-actions.ps1")
$ErrorActionPreference = 'Stop'
# Mock BCD and process scheduling; these checks never change boot state or power.
foreach ($case in @(
    @('shutdown', 0, 'SHUTDOWN_ACCEPTED_V1', 0),
    @('reboot-windows', 0, 'REBOOT_ACCEPTED_V1', 0),
    @('shutdown', 1, '', 1),
    @('reboot-windows', 1, '', 1)
)) {
    $temporary = Join-Path $env:TEMP ([guid]::NewGuid().ToString() + '.ps1')
    $template = @'
function Invoke-Bcd { param([string[]]$Arguments); return 'path \EFI\Microsoft\Boot\bootmgfw.efi' }
function Get-FirmwareManager { return 'bootsequence {9dea862c-5cdd-4e70-acc1-f32b344d4795}' }
function Start-Process {
 param($FilePath, $ArgumentList, $WindowStyle, [switch]$Wait, [switch]$PassThru)
 return [pscustomobject]@{ ExitCode = MOCK_EXIT_CODE }
}
$env:SSH_ORIGINAL_COMMAND = 'MOCK_COMMAND'
& 'HANDLER_PATH'
exit $LASTEXITCODE
'@
    $source = $template.Replace('MOCK_EXIT_CODE', [string]$case[1]).Replace('MOCK_COMMAND', $case[0]).Replace('HANDLER_PATH', $Handler.Replace("'", "''"))
    try {
        [IO.File]::WriteAllText($temporary, $source, [Text.UTF8Encoding]::new($false))
        $ErrorActionPreference = 'Continue'
        $output = & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $temporary 2>&1
        $rc = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($rc -ne $case[3]) { throw "Wrong exit code for $($case[0]): $rc" }
        if ($case[1] -eq 0 -and ($output -join "`n").Trim() -cne $case[2]) { throw 'Wrong acknowledgment' }
        Write-Output "PASS $($case[0]) mocked scheduler=$($case[1]) exit=$rc"
    }
    finally { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }
}
