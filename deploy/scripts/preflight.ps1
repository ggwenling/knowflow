#Requires -Version 7.0
<#
.SYNOPSIS
    KnowFlow 生产部署预检（只读）。

.DESCRIPTION
    在真正执行 `docker compose up` 之前跑一遍。只读：不启动容器、不改文件、不打印任何密钥值
    （只输出长度、是否存在、是否像占位符）。

.PARAMETER EnvFile
    生产环境变量文件，默认 deploy/.env.production。

.PARAMETER MinDiskGb
    目标盘最少剩余空间，默认 20。

.EXAMPLE
    pwsh -File deploy/scripts/preflight.ps1 -EnvFile deploy/.env.production

.EXITCODE
    0 = 全部 PASS 或有 WARN；1 = 存在 FAIL。
#>
[CmdletBinding()]
param(
    [string]$EnvFile = "deploy/.env.production",
    [int]$MinDiskGb = 20
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$results = [System.Collections.Generic.List[object]]::new()
function Add-Result([string]$Area, [string]$Check, [string]$Status, [string]$Detail) {
    $results.Add([pscustomobject]@{ Area = $Area; Check = $Check; Status = $Status; Detail = $Detail })
}

# ── 1. 仓库状态 ────────────────────────────────────────────────────────
try {
    $head = (git rev-parse HEAD).Trim()
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    $dirty = (git status --porcelain --untracked-files=no | Measure-Object).Count
    Add-Result "repo" "HEAD" "INFO" "$branch@$($head.Substring(0,7))"
    if ($dirty -gt 0) {
        Add-Result "repo" "tracked-worktree" "WARN" "$dirty 个已跟踪文件有未提交改动；生产构建必须来自干净提交"
    } else {
        Add-Result "repo" "tracked-worktree" "PASS" "clean"
    }
} catch {
    Add-Result "repo" "HEAD" "FAIL" "无法读取 git 状态：$($_.Exception.Message)"
}

# ── 2. 契约 schema 指纹 ────────────────────────────────────────────────
$expectedSchema = "20121f69098c9fb0c8de59a813a398782070e9f6b9aa5a59e80d30568524883f"
$schemaPath = Join-Path $repo "contracts/schemas/protocol.schema.json"
if (Test-Path $schemaPath) {
    $actual = (Get-FileHash $schemaPath -Algorithm SHA256).Hash.ToLower()
    if ($actual -eq $expectedSchema) {
        Add-Result "contract" "schema-sha256" "PASS" "draft.10 登记值匹配"
    } else {
        Add-Result "contract" "schema-sha256" "FAIL" "期望 $($expectedSchema.Substring(0,12))…，实际 $($actual.Substring(0,12))…；契约已变更，需重新登记"
    }
} else {
    Add-Result "contract" "schema-sha256" "FAIL" "缺少 $schemaPath"
}

# ── 3. 容器工具链 ──────────────────────────────────────────────────────
foreach ($tool in @("docker", "git")) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) {
        Add-Result "toolchain" $tool "PASS" "found"
    } else {
        Add-Result "toolchain" $tool "FAIL" "未安装或不在 PATH"
    }
}
if (Get-Command docker -ErrorAction SilentlyContinue) {
    $composeVersion = (docker compose version --short 2>$null)
    if ($LASTEXITCODE -eq 0 -and $composeVersion) {
        Add-Result "toolchain" "compose" "PASS" "v$composeVersion"
    } else {
        Add-Result "toolchain" "compose" "FAIL" "docker compose 不可用"
    }
}

# ── 4. 环境变量文件 ────────────────────────────────────────────────────
$required = @(
    "KNOWFLOW_DATABASE_URL", "KNOWFLOW_DATABASE_USERNAME", "KNOWFLOW_DATABASE_PASSWORD",
    "KNOWFLOW_MIGRATION_DATABASE_URL", "KNOWFLOW_MIGRATION_DATABASE_USERNAME", "KNOWFLOW_MIGRATION_DATABASE_PASSWORD",
    "KNOWFLOW_AI_DATABASE_URL",
    "KNOWFLOW_STORAGE_ENDPOINT", "KNOWFLOW_STORAGE_BUCKET", "KNOWFLOW_STORAGE_ACCESS_KEY", "KNOWFLOW_STORAGE_SECRET_KEY",
    "KNOWFLOW_INTERNAL_SHARED_SECRET",
    "KNOWFLOW_AI_BASE_URL", "KNOWFLOW_JAVA_BASE_URL", "KNOWFLOW_API_BASE_URL",
    "KNOWFLOW_RUNTIME_PROFILE_ID", "KNOWFLOW_INDEXING_RUNTIME_PROFILE_ID",
    "KNOWFLOW_EMBEDDING_BASE_URL", "KNOWFLOW_EMBEDDING_MODEL", "KNOWFLOW_EMBEDDING_DIMENSIONS", "KNOWFLOW_EMBEDDING_KEY_ENV",
    "KNOWFLOW_LLM_BASE_URL", "KNOWFLOW_LLM_MODEL", "KNOWFLOW_LLM_KEY_ENV",
    "KNOWFLOW_WEB_MODEL_MODE"
)
$secrets = @(
    "KNOWFLOW_DATABASE_PASSWORD", "KNOWFLOW_MIGRATION_DATABASE_PASSWORD",
    "KNOWFLOW_STORAGE_SECRET_KEY", "KNOWFLOW_INTERNAL_SHARED_SECRET",
    "KNOWFLOW_EMBEDDING_API_KEY", "KNOWFLOW_LLM_API_KEY"
)
$placeholders = @("CHANGE_ME", "changeme", "dummy", "example", "placeholder", "your-", "<", "xxxx")

$envMap = @{}
$resolvedEnv = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $repo $EnvFile }
if (-not (Test-Path $resolvedEnv)) {
    Add-Result "env" "file" "FAIL" "找不到 $EnvFile（从 deploy/env/production.env.example 复制后填写）"
} else {
    Add-Result "env" "file" "PASS" (Split-Path $resolvedEnv -Leaf)
    foreach ($line in Get-Content $resolvedEnv) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
        if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
            $envMap[$Matches[1]] = $Matches[2].Trim()
        }
    }
    $missing = $required | Where-Object { -not $envMap.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($envMap[$_]) }
    if ($missing.Count -eq 0) {
        Add-Result "env" "required-keys" "PASS" "$($required.Count) 项齐全"
    } else {
        Add-Result "env" "required-keys" "FAIL" "缺失或为空：$($missing -join ', ')"
    }
    foreach ($name in $secrets) {
        if (-not $envMap.ContainsKey($name)) { continue }
        $value = $envMap[$name]
        if ([string]::IsNullOrWhiteSpace($value)) { continue }
        $isPlaceholder = $placeholders | Where-Object { $value -like "*$_*" }
        if ($isPlaceholder) {
            Add-Result "secret" $name "FAIL" "像占位符（长度 $($value.Length)），不是真实值"
        } elseif ($value.Length -lt 24) {
            Add-Result "secret" $name "WARN" "长度 $($value.Length) < 24"
        } else {
            Add-Result "secret" $name "PASS" "长度 $($value.Length)"
        }
    }
    # 跨字段一致性
    if ($envMap["KNOWFLOW_RUNTIME_PROFILE_ID"] -and $envMap["KNOWFLOW_INDEXING_RUNTIME_PROFILE_ID"] -and
        $envMap["KNOWFLOW_RUNTIME_PROFILE_ID"] -ne $envMap["KNOWFLOW_INDEXING_RUNTIME_PROFILE_ID"]) {
        Add-Result "env" "runtime-profile" "FAIL" "AI 与 API 的 runtime profile 不一致，派工会被拒"
    } else {
        Add-Result "env" "runtime-profile" "PASS" "一致"
    }
    if ($envMap["KNOWFLOW_LLM_BASE_URL"] -and $envMap["KNOWFLOW_LLM_BASE_URL"] -ne "https://api.deepseek.com") {
        Add-Result "env" "llm-endpoint" "FAIL" "运行时只接受 https://api.deepseek.com"
    }
    if ($envMap["KNOWFLOW_WEB_MODEL_MODE"] -eq "synthetic") {
        Add-Result "env" "model-mode" "WARN" "仍是 synthetic：生产上线前需确认真实模式，或明确这是演示环境"
    }
}

# ── 5. 密钥未落入版本控制 ──────────────────────────────────────────────
$leaks = @()
foreach ($f in (git ls-files)) {
    if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { continue }
    $hit = Select-String -LiteralPath $f -Pattern 'sk-[A-Za-z0-9]{24,}' -ErrorAction SilentlyContinue
    if ($hit) { $leaks += $f }
}
if ($leaks.Count -eq 0) {
    Add-Result "secret" "tracked-key-scan" "PASS" "已跟踪文件中无 sk- 形态密钥"
} else {
    Add-Result "secret" "tracked-key-scan" "FAIL" "疑似密钥出现在：$($leaks -join ', ')"
}

# ── 6. 镜像可复现性 ────────────────────────────────────────────────────
$unpinned = @()
foreach ($dockerfile in (Get-ChildItem -Path $repo -Recurse -Filter "Dockerfile*" -File |
        Where-Object { $_.FullName -notmatch '\\node_modules\\|\\\.venv\\' })) {
    foreach ($line in (Select-String -Path $dockerfile.FullName -Pattern '^FROM\s+(\S+)')) {
        $ref = $line.Matches[0].Groups[1].Value
        if ($ref -notmatch '@sha256:' -and $ref -ne 'scratch') {
            $unpinned += "$($dockerfile.Name): $ref"
        }
    }
}
if ($unpinned.Count -eq 0) {
    Add-Result "images" "dockerfile-digest" "PASS" "全部基础镜像已 pin digest"
} else {
    Add-Result "images" "dockerfile-digest" "WARN" "$($unpinned.Count) 处未 pin digest：$($unpinned -join '; ')"
}

# ── 7. 宿主资源 ────────────────────────────────────────────────────────
$drive = (Get-Item $repo).PSDrive
$freeGb = [math]::Round((Get-PSDrive $drive.Name).Free / 1GB, 1)
if ($freeGb -ge $MinDiskGb) {
    Add-Result "host" "disk-free" "PASS" "$freeGb GB 可用（阈值 $MinDiskGb GB）"
} else {
    Add-Result "host" "disk-free" "FAIL" "$freeGb GB 可用，低于阈值 $MinDiskGb GB"
}

$webPort = if ($envMap["KNOWFLOW_WEB_PORT"]) { [int]$envMap["KNOWFLOW_WEB_PORT"] } else { 3000 }
try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $webPort)
    $listener.Start()
    $listener.Stop()
    Add-Result "host" "port-$webPort" "PASS" "空闲"
} catch {
    Add-Result "host" "port-$webPort" "FAIL" "已被占用"
}

# ── 8. 输出 ────────────────────────────────────────────────────────────
$results | Format-Table -AutoSize Area, Check, Status, Detail
$fails = ($results | Where-Object Status -eq "FAIL").Count
$warns = ($results | Where-Object Status -eq "WARN").Count
Write-Host ""
Write-Host "FAIL=$fails WARN=$warns PASS=$(($results | Where-Object Status -eq 'PASS').Count)"
if ($fails -gt 0) {
    Write-Host "预检未通过：先清掉 FAIL 项再继续 PRODUCTION-CHECKLIST.md。" -ForegroundColor Red
    exit 1
}
Write-Host "预检通过（WARN 项需在部署记录里逐条说明）。" -ForegroundColor Green
exit 0
