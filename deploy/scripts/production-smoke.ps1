#Requires -Version 7.0
<#
Production-equivalent smoke test, driven through the web edge only.

Covers: web/API/AI health, register + login (token redacted), knowledge base
creation, document upload, indexing completion, answerable question with
citation sources, and an unanswerable question refusal.

Usage:
  pwsh -NoProfile -File deploy/scripts/production-smoke.ps1 `
    -BaseUrl http://127.0.0.1:3100 -ContractVersion 0.2.0 `
    -EvidencePath D:\konwflow-prod-drill\evidence\smoke-deploy.json

  # During the known provider outage, record Q&A as BLOCKED instead of failing:
  ... -AllowProviderBlocked

The script never prints the session token or password. It writes a sanitized
JSON evidence file containing step statuses, IDs, and answer text.
#>
param(
  [string]$BaseUrl = 'http://127.0.0.1:3100',
  [string]$ContractVersion = '0.2.0',
  [string]$Label = 'deploy',
  [string]$EvidencePath = '',
  [switch]$AllowProviderBlocked,
  [switch]$SkipCertificateCheck
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$email = "prod-$Label-$stamp@example.test"
$password = 'Drill-' + ([Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(12)))
$result = [ordered]@{
  label = $Label
  contract_version = $ContractVersion
  started_at = (Get-Date).ToString('o')
  steps = @()
}

function Step($name, $status, $detail) {
  $script:result.steps += [ordered]@{ name = $name; status = $status; detail = $detail; at = (Get-Date).ToString('o') }
}

function Invoke-Json($method, $path, $body, $cookie) {
  $headers = @{ Origin = $BaseUrl }
  if ($cookie) { $headers['Cookie'] = "knowflow_session=$cookie" }
  $params = @{ Uri = "$BaseUrl$path"; Method = $method; Headers = $headers; SkipHttpErrorCheck = $true; TimeoutSec = 45 }
  if ($SkipCertificateCheck) { $params['SkipCertificateCheck'] = $true }
  if ($body) {
    $params['ContentType'] = 'application/json'
    $params['Body'] = ($body | ConvertTo-Json -Compress)
  }
  Invoke-WebRequest @params
}

function Get-SessionToken($response) {
  $setCookie = $response.Headers['Set-Cookie']
  if (-not $setCookie) { throw 'no set-cookie header' }
  $raw = if ($setCookie -is [array]) { $setCookie[0] } else { $setCookie }
  if ($raw -notmatch 'knowflow_session=([^;]+)') { throw 'no session cookie' }
  [uri]::UnescapeDataString($Matches[1])
}

function Assert-QuestionResult($name, $response, $cookie) {
  if ($response.StatusCode -eq 200) {
    $json = $response.Content | ConvertFrom-Json
    Step $name $response.StatusCode ("has_answer={0} sources={1} answer={2}" -f $json.has_answer, @($json.sources).Count, $json.answer)
    if ($name -eq 'answerable question' -and -not $json.has_answer) { throw 'answerable question was refused' }
    if ($name -eq 'answerable question' -and @($json.sources).Count -lt 1) { throw 'no citation sources returned' }
    if ($name -eq 'unanswerable question' -and $json.has_answer) { throw 'unanswerable question was answered' }
    if ($name -eq 'unanswerable question' -and @($json.sources).Count -ne 0) { throw 'refusal returned sources' }
    return
  }
  if ($AllowProviderBlocked -and $response.StatusCode -in @(502, 504) -and $response.Content -match 'AI_PROCESSING_FAILED|PROCESSING_TIMEOUT') {
    Step $name 'BLOCKED' "provider failure status=$($response.StatusCode); recorded as BLOCKED"
    return
  }
  throw "$name status $($response.StatusCode): $($response.Content)"
}

$docPath = $null
try {
  $mode = Invoke-WebRequest -Uri "$BaseUrl/api/mode" -SkipHttpErrorCheck -TimeoutSec 10 -SkipCertificateCheck:$SkipCertificateCheck
  Step 'web mode endpoint' $mode.StatusCode $mode.Content
  if ($mode.StatusCode -ne 200) { throw "web mode status $($mode.StatusCode)" }

  $reg = Invoke-Json 'POST' '/api/v1/auth/register' @{ contract_version = $ContractVersion; email = $email; password = $password }
  if ($reg.StatusCode -ne 201) { throw "register status $($reg.StatusCode): $($reg.Content)" }
  $token = Get-SessionToken $reg
  Step 'register' $reg.StatusCode 'user created; token redacted'

  $login = Invoke-Json 'POST' '/api/v1/auth/login' @{ contract_version = $ContractVersion; email = $email; password = $password }
  if ($login.StatusCode -ne 200) { throw "login status $($login.StatusCode): $($login.Content)" }
  $token = Get-SessionToken $login
  Step 'login' $login.StatusCode 'token issued in HttpOnly cookie (redacted)'

  $me = Invoke-Json 'GET' '/api/v1/me' $null $token
  if ($me.StatusCode -ne 200) { throw "me status $($me.StatusCode)" }
  Step 'authenticated /me' $me.StatusCode "user_id=$((($me.Content | ConvertFrom-Json).user_id))"

  $kb = Invoke-Json 'POST' '/api/v1/knowledge-bases' @{ contract_version = $ContractVersion; name = "prod-$Label-$stamp" } $token
  if ($kb.StatusCode -ne 201) { throw "kb status $($kb.StatusCode): $($kb.Content)" }
  $kbId = ($kb.Content | ConvertFrom-Json).id
  Step 'create knowledge base' $kb.StatusCode "knowledge_base_id=$kbId"

  $docPath = Join-Path $env:TEMP "knowflow-prod-smoke-$stamp.txt"
  "生产演练资料`n项目代号：QL-2026`n项目负责人：林澈`n计划投产日期：2026-12-20`n" | Set-Content -Path $docPath -Encoding utf8NoBOM
  $upload = Invoke-WebRequest -Uri "$BaseUrl/api/v1/knowledge-bases/$kbId/documents" -Method POST `
    -Headers @{ Origin = $BaseUrl; Cookie = "knowflow_session=$token" } `
    -Form @{ file = Get-Item $docPath } -SkipHttpErrorCheck -TimeoutSec 60 -SkipCertificateCheck:$SkipCertificateCheck
  if ($upload.StatusCode -ne 202) { throw "upload status $($upload.StatusCode): $($upload.Content)" }
  $uploadJson = $upload.Content | ConvertFrom-Json
  $taskId = $uploadJson.task_id
  Step 'upload document' $upload.StatusCode "document_id=$($uploadJson.document_id) task_id=$taskId"

  $deadline = (Get-Date).AddSeconds(240)
  $final = $null
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $task = Invoke-Json 'GET' "/api/v1/tasks/$taskId" $null $token
    if ($task.StatusCode -eq 200) {
      $tj = $task.Content | ConvertFrom-Json
      if ($tj.status -in @('SUCCEEDED', 'FAILED')) { $final = $tj; break }
    }
  }
  if (-not $final) { throw 'indexing did not finish within 240s' }
  if ($final.status -ne 'SUCCEEDED') { throw "indexing status $($final.status) failure=$($final.failure_code)" }
  $doc = Invoke-Json 'GET' "/api/v1/documents/$($uploadJson.document_id)" $null $token
  $docJson = $doc.Content | ConvertFrom-Json
  Step 'indexing completed' 200 "task_status=$($final.status) document_status=$($docJson.status) active_index_version=$($docJson.active_index_version_id)"
  if ($docJson.status -ne 'READY') { throw "document status $($docJson.status)" }

  $answerable = Invoke-Json 'POST' "/api/v1/knowledge-bases/$kbId/questions" @{ question = '青岚项目的代号是什么？' } $token
  Assert-QuestionResult 'answerable question' $answerable $token

  $unanswerable = Invoke-Json 'POST' "/api/v1/knowledge-bases/$kbId/questions" @{ question = '火星基地的氧气储量是多少？' } $token
  Assert-QuestionResult 'unanswerable question' $unanswerable $token

  $result.email = $email
  $result.knowledge_base_id = $kbId
  $result.document_id = $uploadJson.document_id
  $result.finished_at = (Get-Date).ToString('o')
  $result.outcome = 'PASS'
} catch {
  $result.outcome = 'FAIL'
  $result.error = $_.Exception.Message
  Step 'failure' 'FAIL' $_.Exception.Message
} finally {
  if ($docPath) { Remove-Item $docPath -ErrorAction SilentlyContinue }
  $out = if ($EvidencePath) { $EvidencePath } else { Join-Path $env:TEMP "knowflow-prod-$Label-$stamp.json" }
  ($result | ConvertTo-Json -Depth 6) | Set-Content -Path $out -Encoding utf8
  Write-Output "evidence=$out"
  Write-Output ($result | ConvertTo-Json -Depth 6)
}
