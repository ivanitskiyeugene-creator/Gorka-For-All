[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, HelpMessage = 'Path to IntoTheRadius2\Content\Paks')]
    [string]$Paks,

    [string]$Output = '',

    [string]$OodleLibrary = ''
)

$ErrorActionPreference = 'Stop'

function Resolve-Python {
    if (Get-Command 'py' -ErrorAction SilentlyContinue) {
        return @{ Command = 'py'; Prefix = @('-3') }
    }
    if (Get-Command 'python' -ErrorAction SilentlyContinue) {
        return @{ Command = 'python'; Prefix = @() }
    }
    throw 'Python 3 was not found. Install Python 3 from python.org and enable the py launcher/PATH option.'
}

try {
    if (-not $Output) {
        $Output = Join-Path $PSScriptRoot 'gorka-assets'
    }
    $Paks = (Resolve-Path -LiteralPath $Paks).Path
    $Utoc = Join-Path $Paks 'pakchunk0-Windows.utoc'
    $Ucas = Join-Path $Paks 'pakchunk0-Windows.ucas'
    if (-not (Test-Path -LiteralPath $Utoc -PathType Leaf)) {
        throw "UTOC not found: $Utoc"
    }
    if (-not (Test-Path -LiteralPath $Ucas -PathType Leaf)) {
        throw "UCAS not found: $Ucas. The script reads it locally; do not upload it."
    }

    $Output = [System.IO.Path]::GetFullPath($Output)
    if ((Test-Path -LiteralPath $Output) -and
        (Get-ChildItem -LiteralPath $Output -Force | Measure-Object).Count -ne 0) {
        throw "Output directory must be empty: $Output"
    }

    if (-not $OodleLibrary) {
        # Paks is normally IntoTheRadius2\Content\Paks.
        $GameRoot = [System.IO.Path]::GetFullPath((Join-Path $Paks '..\..'))
        $InstallRoot = [System.IO.Path]::GetFullPath((Join-Path $GameRoot '..'))
        $Candidates = @(
            (Join-Path $GameRoot 'Binaries\Win64\oo2core_9_win64.dll'),
            (Join-Path $GameRoot 'Binaries\ThirdParty\Oodle\oo2core_9_win64.dll'),
            (Join-Path $InstallRoot 'Engine\Binaries\ThirdParty\Oodle\oo2core_9_win64.dll'),
            (Join-Path $InstallRoot 'Engine\Binaries\Win64\oo2core_9_win64.dll')
        )
        $OodleLibrary = $Candidates |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1

        if (-not $OodleLibrary -and (Test-Path -LiteralPath $InstallRoot)) {
            $OodleLibrary = Get-ChildItem -LiteralPath $InstallRoot `
                -Filter 'oo2core_9_win64.dll' -File -Recurse -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty FullName
        }
    }
    if (-not $OodleLibrary -or -not (Test-Path -LiteralPath $OodleLibrary -PathType Leaf)) {
        throw 'oo2core_9_win64.dll was not found. Pass -OodleLibrary "C:\full\path\oo2core_9_win64.dll".'
    }
    $OodleLibrary = (Resolve-Path -LiteralPath $OodleLibrary).Path

    $Extractor = Join-Path $PSScriptRoot 'iostore_extract.py'
    $Filters = Join-Path $PSScriptRoot 'gorka-assets.filters'
    if (-not (Test-Path -LiteralPath $Extractor -PathType Leaf) -or
        -not (Test-Path -LiteralPath $Filters -PathType Leaf)) {
        throw 'Keep extract_gorka.ps1, iostore_extract.py, and gorka-assets.filters in the same folder.'
    }

    $Manifest = Join-Path $Output 'selection-manifest.json'
    $Python = Resolve-Python

    Write-Host "Container: $Utoc"
    Write-Host "Oodle:     $OodleLibrary"
    Write-Host "Output:    $Output"
    Write-Host 'Reading only the required blocks locally; the multi-GB UCAS is not copied.'

    $PythonCommand = $Python.Command
    $PythonPrefix = $Python.Prefix
    & $PythonCommand @PythonPrefix $Extractor $Utoc `
        --ucas $Ucas `
        --output $Output `
        --manifest $Manifest `
        --filter-file $Filters `
        --oodle-library $OodleLibrary `
        --list-all
    if ($LASTEXITCODE -ne 0) {
        throw "Extractor exited with code $LASTEXITCODE"
    }

    $Selection = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Selection.selected_entry_count -ne 57) {
        throw "Expected 57 selected assets, got $($Selection.selected_entry_count). The game container version may differ; do not upload a partial set."
    }

    $Zip = "${Output}.zip"
    Compress-Archive -Path (Join-Path $Output '*') -DestinationPath $Zip -Force
    $SizeMiB = [math]::Round((Get-Item -LiteralPath $Zip).Length / 1MB, 2)
    Write-Host ''
    Write-Host "SUCCESS: 57 assets extracted and packed into $Zip ($SizeMiB MiB)." -ForegroundColor Green
    Write-Host 'Upload only this ZIP. Do not upload pakchunk0-Windows.ucas.'
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
