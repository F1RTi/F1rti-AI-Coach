$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$cache = Join-Path $root '.work'
New-Item -ItemType Directory -Force $cache | Out-Null
$file = Join-Path $cache 'upstream.dem'
if (-not (Test-Path -LiteralPath $file)) {
    Invoke-WebRequest 'https://raw.githubusercontent.com/LaihoE/demoparser/4131a4fc02fda291b22421c20e1ca33f149535a7/src/parser/test_demo.dem' -OutFile $file
}
if ((Get-FileHash -LiteralPath $file).Hash -ne '84A1A4191302BDD2A3BBB5A727842093744B1FB1A228AEEC630369E44B622CB2') {
    throw 'Unexpected fixture checksum'
}

