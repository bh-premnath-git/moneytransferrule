<#
.SYNOPSIS
    Compile every .proto file in $ProtoDir (default 'proto')
    into Python stubs under $OutDir (default 'app\proto_gen').
#>
param(
    [string]$ProtoDir = "proto",
    [string]$OutDir   = "app\proto_gen"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

$protoFiles = Get-ChildItem -Path $ProtoDir -Recurse -Filter *.proto |
              ForEach-Object { $_.FullName }

# Build the argument array: easier than quoting a gigantic one‑liner
$args = @(
    "-m", "grpc_tools.protoc",
    "-I", $ProtoDir,
    "--python_out=$OutDir",
    "--grpc_python_out=$OutDir"
) + $protoFiles

python @args  # splat array ⇒ python -m grpc_tools.protoc ...

# Ensure package initialiser exists
$init = Join-Path $OutDir "__init__.py"
if (-not (Test-Path $init)) { New-Item -ItemType File -Path $init | Out-Null }

Write-Host "✅ Protobufs compiled to $OutDir"
