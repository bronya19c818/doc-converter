[CmdletBinding()]
param(
    [string]$PandocPath = "${env:ProgramFiles}\Pandoc\pandoc.exe"
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'frontend'
$webRoot = Join-Path $projectRoot 'src\doc_converter\web'
$releaseAssets = Join-Path $projectRoot '.release-assets\pandoc'
$releaseRoot = Join-Path $projectRoot 'release'
$applicationRoot = Join-Path $releaseRoot 'DocConverter'

if (-not (Test-Path -LiteralPath $PandocPath -PathType Leaf)) {
    throw "未找到 Pandoc：$PandocPath。请安装 Pandoc 或使用 -PandocPath 指定 pandoc.exe。"
}

Push-Location $projectRoot
try {
    & uv sync --group dev
    if ($LASTEXITCODE -ne 0) { throw 'Python 依赖同步失败。' }

    Push-Location $frontendRoot
    try {
        & npm ci
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败。' }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
    }
    finally {
        Pop-Location
    }

    if (Test-Path -LiteralPath $releaseAssets) { Remove-Item -LiteralPath $releaseAssets -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $releaseAssets | Out-Null
    Copy-Item -LiteralPath $PandocPath -Destination (Join-Path $releaseAssets 'pandoc.exe')

    if (Test-Path -LiteralPath $applicationRoot) { Remove-Item -LiteralPath $applicationRoot -Recurse -Force }
    $pyInstallerArgs = @(
        '--noconfirm',
        '--clean',
        '--onedir',
        '--name', 'DocConverter',
        '--paths', 'src',
        '--distpath', $releaseRoot,
        '--workpath', (Join-Path $projectRoot '.release-assets\pyinstaller-work'),
        '--specpath', (Join-Path $projectRoot '.release-assets'),
        '--add-data', "$webRoot;doc_converter/web",
        '--add-binary', "$(Join-Path $releaseAssets 'pandoc.exe');doc_converter/vendor/pandoc",
        'src\doc_converter\launcher.py'
    )
    & uv run pyinstaller @pyInstallerArgs
    if ($LASTEXITCODE -ne 0) { throw 'Windows 发布包构建失败。' }
}
finally {
    Pop-Location
}

Write-Output "已生成：$(Join-Path $applicationRoot 'DocConverter.exe')"
