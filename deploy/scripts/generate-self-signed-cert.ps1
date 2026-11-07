#Requires -Version 7.0
<#
.SYNOPSIS
    为生产形态入口生成自签 TLS 证书（仅本地/演练用）。

.DESCRIPTION
    输出 fullchain.pem（证书）与 privkey.pem（私钥）到 -OutDir，文件名与
    deploy/tls/nginx.conf 中固定路径一致。证书含 SAN：DNS:<CommonName>、
    DNS:localhost、IP:127.0.0.1。

    *.pem / *.key 已被 .gitignore 覆盖，不会进入版本控制。
    生产必须替换为正式 CA 证书（fullchain 与私钥同名覆盖），不要使用本脚本产物。

.PARAMETER OutDir
    证书输出目录，默认 deploy/tls。

.PARAMETER Days
    有效期天数，默认 365。

.PARAMETER CommonName
    证书 CN，默认 localhost。

.PARAMETER Force
    已存在证书时是否覆盖。

.EXAMPLE
    pwsh -NoProfile -File deploy/scripts/generate-self-signed-cert.ps1
#>
[CmdletBinding()]
param(
    [string]$OutDir = "deploy/tls",
    [int]$Days = 365,
    [string]$CommonName = "localhost",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$resolved = if ([System.IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path $repo $OutDir }
if (-not (Test-Path $resolved)) { New-Item -ItemType Directory -Path $resolved | Out-Null }
$resolved = (Resolve-Path $resolved).Path

$certPath = Join-Path $resolved "fullchain.pem"
$keyPath = Join-Path $resolved "privkey.pem"
if (((Test-Path $certPath) -or (Test-Path $keyPath)) -and -not $Force) {
    throw "证书已存在：$resolved；如需重新生成请加 -Force"
}

$image = "nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"
$mount = "${resolved}:/certs"
$subject = "/CN=$CommonName"
$san = "subjectAltName=DNS:$CommonName,DNS:localhost,IP:127.0.0.1"
$command = "apk add --no-cache openssl >/dev/null && " +
    "openssl req -x509 -nodes -newkey rsa:2048 -sha256 -days $Days " +
    "-subj '$subject' -addext '$san' " +
    "-keyout /certs/privkey.pem -out /certs/fullchain.pem && " +
    "chmod 600 /certs/privkey.pem && chmod 644 /certs/fullchain.pem"

docker run --rm -v $mount $image sh -c $command
if ($LASTEXITCODE -ne 0) { throw "证书生成失败（exit=$LASTEXITCODE）" }

Write-Host "cert=$certPath"
Write-Host "key=$keyPath (未打印内容)"
