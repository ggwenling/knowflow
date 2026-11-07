#Requires -Version 7.0
<#
.SYNOPSIS
    用 db-backup.ps1 产出的 pg_dump 备份把 KnowFlow 数据库恢复到备份时的迁移点。

.DESCRIPTION
    Flyway 社区版没有 undo。回滚数据库的可靠方式是“迁移前快照 + 整库恢复”：
      备份（迁移前） → 正向迁移/发布 → 需要回退时执行本脚本 → 校验版本 → 重新启动服务。

    默认先停 api/ai/web/edge 冻结写入，然后删除并重建数据库、pg_restore 恢复、
    校验 flyway_schema_history 版本，最后按依赖顺序拉起服务。该操作会丢弃
    备份之后的所有数据，必须显式 -ConfirmRestore。

.PARAMETER DumpFile
    db-backup.ps1 生成的 .dump 文件路径。

.PARAMETER SkipServiceFreeze
    仅数据库演练时使用：不停止/启动业务容器（例如只启动了 postgres 的隔离项目）。

.EXAMPLE
    pwsh -File deploy/scripts/db-restore.ps1 -DumpFile D:\konwflow-prod-drill\backups\knowflow-pre-migrate.dump -ConfirmRestore

.EXAMPLE
    # 隔离迁移演练（仅 postgres）
    pwsh -File deploy/scripts/db-restore.ps1 -ProjectName knowflow-migtest -DumpFile ... -ConfirmRestore -SkipServiceFreeze
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DumpFile,
    [string]$ProjectName = "knowflow-prod",
    [string]$Database = "knowflow",
    [string]$EnvFile = "deploy/.env.production",
    [string]$ComposeFile = "deploy/compose.production.draft.yml",
    [switch]$ConfirmRestore,
    [switch]$SkipServiceFreeze
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

if (-not $ConfirmRestore) {
    throw "恢复会丢弃备份点之后的所有数据；确认后加 -ConfirmRestore"
}
if (-not (Test-Path -LiteralPath $DumpFile -PathType Leaf)) { throw "找不到备份文件：$DumpFile" }
if ($Database -notmatch '^[A-Za-z0-9_]+$') { throw "非法数据库名：$Database" }

$resolvedDump = (Resolve-Path -LiteralPath $DumpFile).Path
$sidecarPath = "$resolvedDump.json"
$expectedVersion = $null
if (Test-Path -LiteralPath $sidecarPath) {
    $expectedVersion = (Get-Content -Raw -LiteralPath $sidecarPath | ConvertFrom-Json).flyway_version
    $expectedSha = (Get-Content -Raw -LiteralPath $sidecarPath | ConvertFrom-Json).sha256
    $actualSha = (Get-FileHash -LiteralPath $resolvedDump -Algorithm SHA256).Hash.ToLower()
    if ($expectedSha -and $actualSha -ne $expectedSha) {
        throw "备份文件校验和不匹配：期望 $expectedSha，实际 $actualSha"
    }
}

$container = (@(& docker ps --filter "label=com.docker.compose.project=$ProjectName" `
        --filter "label=com.docker.compose.service=postgres" --format "{{.Names}}") -join '').Trim()
if (-not $container) { throw "找不到项目 $ProjectName 的 postgres 容器" }

$resolvedEnv = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $repo $EnvFile }
$composeArguments = @("compose", "-p", $ProjectName, "--env-file", $resolvedEnv, "-f", (Join-Path $repo $ComposeFile))

if (-not $SkipServiceFreeze) {
    Write-Host "冻结业务写入（api/ai/web/edge）…"
    & docker @composeArguments stop api ai web edge | Out-Null
}

$remotePath = "/tmp/knowflow-restore.dump"
& docker cp $resolvedDump "${container}:$remotePath"
if ($LASTEXITCODE -ne 0) { throw "docker cp 失败（exit $LASTEXITCODE）" }

Write-Host "重建数据库 $Database …"
& docker exec $container psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c `
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$Database' AND pid <> pg_backend_pid()" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "终止连接失败（exit $LASTEXITCODE）" }
& docker exec $container psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $Database"
if ($LASTEXITCODE -ne 0) { throw "DROP DATABASE 失败（exit $LASTEXITCODE）" }
& docker exec $container psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Database"
if ($LASTEXITCODE -ne 0) { throw "CREATE DATABASE 失败（exit $LASTEXITCODE）" }

Write-Host "恢复备份 …"
# 保留 owner 与 ACL：后续 Flyway 迁移需要迁移角色对既有对象有 ALTER 权限。
& docker exec $container pg_restore -U postgres -d $Database --exit-on-error $remotePath
if ($LASTEXITCODE -ne 0) { throw "pg_restore 失败（exit $LASTEXITCODE）" }
& docker exec $container rm -f $remotePath | Out-Null

$version = (& docker exec $container psql -U postgres -d $Database -tAc `
        "SELECT version FROM knowflow_flyway.flyway_schema_history WHERE success ORDER BY installed_rank DESC LIMIT 1").Trim()
if ($LASTEXITCODE -ne 0) { throw "读取恢复后的 Flyway 版本失败（exit $LASTEXITCODE）" }
if ($expectedVersion -and $version -ne $expectedVersion) {
    throw "恢复后版本 $version 与备份记录 $expectedVersion 不一致"
}

Write-Host "恢复完成：Flyway 版本 $version"

if (-not $SkipServiceFreeze) {
    Write-Host "按依赖顺序重启服务 …"
    & docker @composeArguments up -d --no-deps api ai web | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "重启 api/ai/web 失败（exit $LASTEXITCODE）" }
    Start-Sleep -Seconds 5
    & docker @composeArguments up -d --no-deps edge | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "重启 edge 失败（exit $LASTEXITCODE）" }
}
