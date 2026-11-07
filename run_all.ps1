# Caly lancuch jednym poleceniem: dane -> modele -> symulacja (H3) -> metryki i hipotezy -> eksport 3D.
#
#   ./run_all.ps1                 # pelny przebieg (30 replikacji, 1000 permutacji modeli zerowych)
#   ./run_all.ps1 -Quick          # sprawdzenie calego lancucha przed prezentacja (~10-15 min)
#   ./run_all.ps1 -Day 2026-11-19 -SkipModels -Unity
#
# Rozbudowa run_milestone.ps1 (Osoba 3). Wyniki:
#   processed/                    dane + dane dla agentow + MANIFEST.json
#   processed/model/              modele popytu, OD, czasu jazdy, sim_params.json (Osoba 2)
#   results/h3_<dzien>/           eksperyment H3 (REPORT.md, wykresy, przebiegi)
#   docs/wyniki/                  hipotezy H2, A, B, C i raport emergencji (dane vs model)
#   unity/Assets/StreamingAssets/veturilo/   dane wizualizacji 3D (dni + wybrane przebiegi modelu)
param(
    [switch]$Quick,
    [string]$Day = '2026-11-05',
    [int]$Replications = 30,
    [int]$Jobs = 4,
    [switch]$SkipBuild,
    [switch]$SkipModels,
    [switch]$SkipExperiment,
    [switch]$Unity
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$started = Get-Date

function Step([string]$Name) {
    $elapsed = [int]((Get-Date) - $started).TotalSeconds
    Write-Host ""
    Write-Host "=== [$elapsed s] $Name ===" -ForegroundColor Yellow
}

function Py {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $python -X utf8 @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python zakonczyl sie kodem $LASTEXITCODE ($($Arguments -join ' '))" }
}

if ($Quick) { $Replications = 3 }
$perm = if ($Quick) { 100 } else { 1000 }
$inputs = "results/inputs_$Day"
$h3 = "results/h3_$Day"

if (-not (Test-Path -LiteralPath $python)) {
    Step 'Srodowisko .venv'
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Nie udalo sie utworzyc .venv' }
    Py -m pip install -r requirements.txt
}

Step 'Testy'
Py -m pytest -q -p no:cacheprovider

if (-not $SkipBuild) {
    Step 'Dane: processed/ + dane dla agentow'
    Py -m src.data.build
    Py -m src.data.manifest
}

if (-not $SkipModels) {
    Step 'Modele popytu, OD i czasu jazdy (Osoba 2)'
    if ($Quick) { Py -m src.model.pipeline --quick } else { Py -m src.model.pipeline }
}

if (-not $SkipExperiment) {
    Step "Symulacja: dane wejsciowe na $Day"
    Py -m src.simulation prepare --out $inputs --day $Day
    Step "Eksperyment H3: $Replications replikacji"
    Py -m src.simulation experiment --inputs $inputs --out $h3 --replications $Replications --jobs $Jobs
    Py -m src.simulation.verify --results $h3
}

Step 'Hipotezy H2, A, B, C i regula operatora'
Py -m src.metrics.hypotheses
$simRun = "$h3/runs/operator_2/seed_1000"
Step "Emergencja: dane vs model ($perm permutacji)"
if (Test-Path -LiteralPath "$simRun/station_timeseries.parquet") {
    Py -m src.metrics processed --sim $simRun --perm $perm --out docs/wyniki
} else {
    Py -m src.metrics processed --perm $perm --out docs/wyniki
}

Step 'Eksport do wizualizacji 3D'
Py -m src.viz.export
$runs = @('none_1', 'operator_2', 'threshold_2', 'threshold_4') |
    ForEach-Object { "$h3/runs/$_/seed_1000" } | Where-Object { Test-Path -LiteralPath "$_/kpis.json" }
if ($runs.Count -gt 0) { Py -m src.viz.export_sim @runs }

if ($Unity) {
    Step 'Unity: aplikacja Windows'
    $editor = 'D:\Unity\Editors\6000.0.85f1\Editor\Unity.exe'
    if (-not (Test-Path -LiteralPath $editor)) { throw "Brak edytora Unity: $editor" }
    & $editor -batchmode -quit -projectPath unity -executeMethod Veturilo.Viz.Editor.VeturiloBuild.BatchBuild -logFile unity/Logs/batch_build.log
    if ($LASTEXITCODE -ne 0) { throw 'Budowanie Unity nie powiodlo sie (unity/Logs/batch_build.log)' }
}

$total = [int]((Get-Date) - $started).TotalMinutes
Write-Host ""
Write-Host "Gotowe w $total min." -ForegroundColor Green
Write-Host "  H3:          $h3/REPORT.md"
Write-Host "  hipotezy:    docs/wyniki/hipotezy_osoba1.md"
Write-Host "  emergencja:  docs/wyniki/emergencja.md"
Write-Host "  3D:          unity/Build/Veturilo.exe (z -Unity) albo Play w edytorze"
