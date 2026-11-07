#Requires -Version 7.0
<#
.SYNOPSIS
    在迁移点前后备份 KnowFlow PostgreSQL（pg_dump 自定义格式 + 版本/校验和）。

.DESCRIPTION
    从运行中的 postgres 容器导出整库，记录当前 Flyway 版本、SHA-256 与时间。
    备份文件与同名 .json 侧车文件写入 -OutDir（默认 D:\konwflow-prod-drill\backups）。
    不要提交备份文件到仓库；生产中按保留策略转存到受控存储。

.EXAMPLE
    pwsh -File deploy/scripts/db-backup.ps1 -ProjectName knowflow-prod -Label pre-migrate

.EXAMPLE
    pwsh -File deploy/scripts/db-backup.ps1 -ProjectName knowflow-migtest -Label before-v3
#>
[CmdletBinding()]
param(
    [string]$ProjectName = "knowflow-prod",
    [string]$Database = "knowflow",
    [string]$Label = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [string]$OutDir = "D:\konwflow-prod-drill\backups"
)

$ErrorActionPreference = "Stop"

if ($Database -notmatch '^[A-Za-z0-9_]+$') { throw "非法数据库名：$Database" }
if ($Label -notmatch '^[A-Za-z0-9._-]+$') { throw "非法 Label：$Label" }

$container = (@(& docker ps --filter "label=com.docker.compose.project=$ProjectName" `
        --filter "label=com.docker.compose.service=postgres" --format "{{.Names}}") -join '').Trim()
if (-not $container) { throw "找不到项目 $ProjectName 的 postgres 容器；栈是否已启动？" }

$health = (& docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" $container).Trim()
if ($health -ne "healthy") { throw "postgres 容器 $container 状态为 $health，需先 healthy" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$remotePath = "/tmp/knowflow-$Label.dump"
$localPath = Join-Path $OutDir "$Database-$Label.dump"

& docker exec $container pg_dump -U postgres -d $Database -Fc -f $remotePath
if ($LASTEXITCODE -ne 0) { throw "pg_dump 失败（exit $LASTEXITCODE）" }
& docker cp "${container}:$remotePath" $localPath
if ($LASTEXITCODE -ne 0) { throw "docker cp 失败（exit $LASTEXITCODE）" }
& docker exec $container rm -f $remotePath | Out-Null

$version = (& docker exec $container psql -U postgres -d $Database -tAc `
        "SELECT version FROM knowflow_flyway.flyway_schema_history WHERE success ORDER BY installed_rank DESC LIMIT 1").Trim()
if ($LASTEXITCODE -ne 0) { throw "读取 Flyway 版本失败（exit $LASTEXITCODE）" }

$sha256 = (Get-FileHash -LiteralPath $localPath -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item -LiteralPath $localPath).Length
$sidecar = [ordered]@{
    project = $ProjectName
    database = $Database
    label = $Label
    flyway_version = if ($version) { $version } else { $null }
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    sha256 = $sha256
    bytes = $size
    file = $localPath
}
$metadataPath = "$localPath.json"
$sidecar | ConvertTo-Json -Depth 3 | Set-Content -Path $metadataPath -Encoding utf8

Write-Host "备份完成：$localPath"
Write-Host "  Flyway 版本：$version"
Write-Host "  SHA-256：$sha256"
Write-Host "  大小：$([math]::Round($size / 1MB, 2)) MB"
Write-Host "  侧车：$metadataPath"
