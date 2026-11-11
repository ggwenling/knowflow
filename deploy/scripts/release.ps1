#Requires -Version 7.0
<#
.SYNOPSIS
    KnowFlow 发布构建：不可变 tag + 推送 + digest 记录。

.DESCRIPTION
    从干净提交构建 api/ai/web 三个镜像，统一打 <registry>/<repo>/<component>:<release>，
    推送后记录每个镜像的 RepoDigest 与 compose 所需变量。默认拒绝覆盖已存在的 tag。

    KNOWFLOW_RELEASE 与 KNOWFLOW_IMAGE_REPOSITORY 需与 .env.production 一致；
    回滚时把 KNOWFLOW_RELEASE 改成旧版本并执行 compose pull + up --no-build 即可。

.EXAMPLE
    # 本机 registry + 构建 + 推送（版本默认取 HEAD 短 sha）
    pwsh -File deploy/scripts/release.ps1 -StartRegistry -Push

.EXAMPLE
    # 只构建本地镜像（不推 registry）
    pwsh -File deploy/scripts/release.ps1

.EXAMPLE
    # 用已有本地镜像演练推送（不重新构建）
    pwsh -File deploy/scripts/release.ps1 -Version 2026.11.07 -SkipBuild -Push

.EXITCODE
    0 = 成功；非 0 = 失败（脏工作树、浮动 tag、已存在 tag、构建/推送失败）。
#>
[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$Registry = "127.0.0.1:5001",
    [string]$Repository = "knowflow",
    [string]$RegistryContainer = "knowflow-registry",
    [int]$RegistryPort = 5001,
    [switch]$StartRegistry,
    [switch]$SkipBuild,
    [switch]$Push,
    [switch]$AllowDirty,
    [switch]$AllowOverwrite,
    [string]$ManifestDir = "D:\konwflow-prod-drill\releases"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

function Invoke-Checked([string[]]$arguments, [string]$action) {
    & docker @arguments
    if ($LASTEXITCODE -ne 0) { throw "$action failed (exit $LASTEXITCODE): docker $($arguments -join ' ')" }
}

if (-not $Version) {
    $Version = (& git rev-parse --short=10 HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "无法从 git 读取 HEAD；请显式 -Version" }
}
if ($Version -in @("local", "latest", "dev", "main")) {
    throw "KNOWFLOW_RELEASE=$Version 是浮动标签；发布必须使用提交 sha 或语义版本"
}
if ($Version -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$') {
    throw "Version 需为 6–64 位字母数字/._-：$Version"
}
if (-not $AllowDirty) {
    $dirty = (& git status --porcelain --untracked-files=no | Measure-Object).Count
    if ($dirty -gt 0) { throw "工作树有 $dirty 个已跟踪文件未提交；生产发布必须来自干净提交（或显式 -AllowDirty）" }
}

$prefix = "$Registry/$Repository"
$components = @(
    [pscustomobject]@{ Name = "api"; Context = "services/api"; Dockerfile = "Dockerfile" },
    [pscustomobject]@{ Name = "web"; Context = "apps/web-v2"; Dockerfile = "Dockerfile" },
    [pscustomobject]@{ Name = "ai"; Context = "."; Dockerfile = "services/ai/Dockerfile" }
)

# ── 本机 registry ──────────────────────────────────────────────────────
if ($StartRegistry) {
    $existing = (@(& docker ps -a --filter "name=^/$RegistryContainer$" --format "{{.Names}}") -join '').Trim()
    if ($existing) {
        Invoke-Checked @("start", $RegistryContainer) "start registry"
    } else {
        Invoke-Checked @(
            "run", "-d", "--name", $RegistryContainer, "--restart", "unless-stopped",
            "-p", "127.0.0.1:${RegistryPort}:5000",
            "-v", "knowflow-registry-data:/var/lib/registry",
            "registry@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373"
        ) "start registry"
    }
    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $response = Invoke-WebRequest -Uri "http://$Registry/v2/" -TimeoutSec 3 -SkipHttpErrorCheck
            if ($response.StatusCode -in @(200, 401)) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "registry $Registry 未在 10s 内就绪" }
}

# ── 不可变检查 ─────────────────────────────────────────────────────────
function Get-RegistryTagStatus([string]$name) {
    $uri = "http://$Registry/v2/$Repository/$name/manifests/$Version"
    # Docker 的 containerd 镜像存储会推 OCI index；只声明 schema2 会得到 404。
    $accept = @(
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json"
    ) -join ", "
    try {
        $response = Invoke-WebRequest -Uri $uri -Method Head -TimeoutSec 5 -SkipHttpErrorCheck `
            -Headers @{ Accept = $accept }
        return $response.StatusCode
    } catch { return $null }
}

$planned = @()
foreach ($component in $components) {
    $reference = "$prefix/$($component.Name):$Version"
    if (-not $AllowOverwrite) {
        if ($Registry -match '^(127\.0\.0\.1|localhost)(:\d+)?$') {
            $status = Get-RegistryTagStatus $component.Name
            if ($status -eq 200) { throw "$reference 已存在于 registry；不可变 tag 禁止覆盖（或显式 -AllowOverwrite）" }
        } else {
            # 远端 registry 的覆盖检查需认证，交给发布系统；本地仍按下一条规则防止同名 tag。
        }
        & docker image inspect $reference 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0 -and -not $SkipBuild) {
            throw "$reference 已存在本地镜像；不可变 tag 禁止覆盖（或显式 -AllowOverwrite）"
        }
    }
    $planned += [pscustomobject]@{ Name = $component.Name; Reference = $reference }
}

# ── 构建 / 推送 ────────────────────────────────────────────────────────
$images = @()
foreach ($item in $planned) {
    $component = $components | Where-Object { $_.Name -eq $item.Name }
    if (-not $SkipBuild) {
        Invoke-Checked @(
            "build", "-f", (Join-Path $component.Context $component.Dockerfile),
            "-t", $item.Reference, $component.Context
        ) "build $($component.Name)"
    } else {
        $source = "knowflow-$($component.Name):$Version"
        Invoke-Checked @("tag", $source, $item.Reference) "retag $source"
    }
    if ($Push) {
        Invoke-Checked @("push", $item.Reference) "push $($component.Name)"
    }
    $digest = $null
    if ($Push) {
        $repoReference = $item.Reference.Substring(0, $item.Reference.LastIndexOf(':'))
        $rawDigests = (@(& docker image inspect $item.Reference --format '{{json .RepoDigests}}') -join '').Trim()
        if ($rawDigests) {
            $digests = $rawDigests | ConvertFrom-Json
            $digest = ($digests | Where-Object { $_ -like "$repoReference@sha256:*" } | Select-Object -First 1)
        }
        if (-not $digest) {
            throw "推送成功但未能从本地镜像读取 digest：$($item.Reference)"
        }
    }
    $images += [pscustomobject]@{ component = $component.Name; reference = $item.Reference; digest = $digest }
    Write-Host "  $($item.Reference)  $digest"
}

# ── 发布清单 ───────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $ManifestDir | Out-Null
$manifestPath = Join-Path $ManifestDir "release-$Version.json"
$head = (& git rev-parse HEAD).Trim()
$manifest = [ordered]@{
    release = $Version
    commit = $head
    repository = $prefix
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    images = $images
    compose_env = [ordered]@{
        KNOWFLOW_IMAGE_REPOSITORY = $prefix
        KNOWFLOW_RELEASE = $Version
    }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath -Encoding utf8

Write-Host ""
Write-Host "发布清单：$manifestPath"
Write-Host "compose 变量：KNOWFLOW_IMAGE_REPOSITORY=$prefix KNOWFLOW_RELEASE=$Version"
Write-Host "回滚：改回旧 KNOWFLOW_RELEASE 后 docker compose pull && docker compose up -d --no-build"
