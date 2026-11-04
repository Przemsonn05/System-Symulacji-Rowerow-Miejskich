param(
    [int]$Replications = 30,
    [int]$Jobs = 4,
    [switch]$Example,
    [switch]$ApproximateRoads,
    [switch]$RebuildInputs
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

function Invoke-ProjectPython {
    param([string[]]$Arguments)
    & $projectPython @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python exited with code $LASTEXITCODE" }
}

if (-not (Test-Path -LiteralPath $projectPython)) {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv' }
    Invoke-ProjectPython -Arguments @('-m', 'pip', 'install', '-r', 'requirements-simulation.txt')
}

$inputDirectory = if ($Example) { 'results/example_inputs' } else { 'results/inputs' }
$experimentDirectory = if ($Example) { 'results/example_h3' } else { 'results/h3' }
if (-not $Example -and -not (Test-Path -LiteralPath 'processed/stations.parquet')) {
    Invoke-ProjectPython -Arguments @('-X', 'utf8', '-m', 'src.data.build', '--no-features')
}
if (-not $Example -and -not $ApproximateRoads -and -not (Test-Path -LiteralPath 'data/static/osm/graph_drive.graphml')) {
    Invoke-ProjectPython -Arguments @('-X', 'utf8', '-c', "import geopandas as gpd; from src.data.osm import _setup, fetch_graphs; from src.data.config import OSM_DIR; fetch_graphs(_setup(), gpd.read_file(OSM_DIR / 'boundary.geojson').geometry.iloc[0], print)")
}
if ($RebuildInputs -or $ApproximateRoads -or -not (Test-Path -LiteralPath "$inputDirectory/metadata.json")) {
    $prepareArguments = @('-X', 'utf8', '-m', 'src.simulation', 'prepare', '--out', $inputDirectory)
    if ($Example) { $prepareArguments += '--example' }
    if ($ApproximateRoads) { $prepareArguments += '--approximate-roads' }
    Invoke-ProjectPython -Arguments $prepareArguments
}
Invoke-ProjectPython -Arguments @('-X', 'utf8', '-m', 'pytest', '-q', '--junitxml=results/verification.xml')
Invoke-ProjectPython -Arguments @('-X', 'utf8', '-m', 'src.simulation', 'experiment', '--inputs', $inputDirectory,
    '--out', $experimentDirectory, '--replications', "$Replications", '--jobs', "$Jobs")
Invoke-ProjectPython -Arguments @('-X', 'utf8', '-m', 'src.simulation.verify', '--results', $experimentDirectory)
Write-Host "Ready: $experimentDirectory/REPORT.md"
