<#
.SYNOPSIS
Run PDF extraction, a selected model, and a Notion preview or publication.
.EXAMPLE
.\review.ps1 -Pdf '.\input\paper.pdf' -Provider gpt
.EXAMPLE
.\review.ps1 -Extract '.\output\paper_extract_2026-10-28' -Provider ollama -Model 'qwen3.5:9b'
.EXAMPLE
.\review.ps1 -Summary '.\output\paper_summary.md' -Publish
#>
[CmdletBinding(DefaultParameterSetName = 'Pdf')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Pdf')]
    [string]$Pdf,
    [Parameter(Mandatory = $true, ParameterSetName = 'Extract')]
    [string]$Extract,
    [Parameter(Mandatory = $true, ParameterSetName = 'Summary')]
    [string]$Summary,
    [ValidateSet('gpt', 'claude', 'ollama')]
    [string]$Provider = 'claude',
    [string]$Model,
    [ValidateRange(1, 2147483647)]
    [int]$MaxTokens = 40000,
    [ValidateRange(1, 2147483647)]
    [int]$NumCtx = 16384,
    [switch]$Think,
    [switch]$Publish,
    [switch]$Compare,
    [switch]$DryRun,
    [string]$Python
)

$ErrorActionPreference = 'Stop'
# Explicit configuration wins; avoid Windows' Store alias before checking Conda.
$configuredPython = if ($Python) { $Python } else { $env:PAPER_REVIEW_PYTHON }
$candidates = if ($configuredPython) {
    @($configuredPython)
} else {
    @(
        (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
        (Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe'),
        (Join-Path $env:USERPROFILE 'Anaconda3\python.exe'),
        (Join-Path $env:USERPROFILE 'miniconda3\python.exe'),
        'python'
    )
}

$pythonExecutable = $null
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $pythonExecutable = (Resolve-Path -LiteralPath $candidate).ProviderPath
        break
    }
    $command = Get-Command -Name $candidate -CommandType Application -ErrorAction SilentlyContinue
    if ($command) {
        $pythonExecutable = $command.Source
        break
    }
}
if (-not $pythonExecutable) {
    throw 'Python was not found. Use -Python with the full path to python.exe.'
}

# Resolve against the PowerShell location without wildcard expansion ([ ] stay literal).
function Resolve-InputPath([string]$Path) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
}

$scriptArgs = @('--provider', $Provider.ToLowerInvariant(), '--max-tokens', "$MaxTokens", '--num-ctx', "$NumCtx")
switch ($PSCmdlet.ParameterSetName) {
    'Pdf' { $scriptArgs += @('--pdf', (Resolve-InputPath $Pdf)) }
    'Extract' { $scriptArgs += @('--extract', (Resolve-InputPath $Extract)) }
    'Summary' { $scriptArgs += @('--summary', (Resolve-InputPath $Summary)) }
}
if ($Model) { $scriptArgs += @('--model', $Model) }
if ($Think) { $scriptArgs += '--think' }
if ($Publish) { $scriptArgs += '--publish' }
if ($Compare) { $scriptArgs += '--compare' }
if ($DryRun) { $scriptArgs += '--dry-run' }

# Argument arrays preserve spaces, square brackets and Korean file names.
$previousEncoding = [Console]::OutputEncoding
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    & $pythonExecutable -X utf8 (Join-Path $PSScriptRoot 'src\review_paper.py') @scriptArgs
    $reviewExitCode = $LASTEXITCODE
} finally {
    [Console]::OutputEncoding = $previousEncoding
}
exit $reviewExitCode
