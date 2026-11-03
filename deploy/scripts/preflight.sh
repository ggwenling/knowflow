#!/usr/bin/env bash
# KnowFlow 生产部署预检（只读，Linux 目标机版本）。
#
# 与 preflight.ps1 检查同一组项目。只读：不启动容器、不改文件、不打印密钥值。
#
# 用法：
#   deploy/scripts/preflight.sh [env-file]        # 默认 deploy/.env.production
# 退出码：0 = 无 FAIL；1 = 存在 FAIL。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

ENV_FILE="${1:-deploy/.env.production}"
MIN_DISK_GB="${MIN_DISK_GB:-20}"
EXPECTED_SCHEMA="20121f69098c9fb0c8de59a813a398782070e9f6b9aa5a59e80d30568524883f"

pass=0; warn=0; fail=0
row() { # area check status detail
  printf '%-10s %-24s %-5s %s\n' "$1" "$2" "$3" "$4"
  case "$3" in PASS) pass=$((pass+1));; WARN) warn=$((warn+1));; FAIL) fail=$((fail+1));; esac
}

# ── 1. 仓库状态 ────────────────────────────────────────────────────────
if head_sha="$(git rev-parse HEAD 2>/dev/null)"; then
  branch="$(git rev-parse --abbrev-ref HEAD)"
  dirty="$(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
  row repo HEAD INFO "$branch@${head_sha:0:7}"
  if [ "$dirty" -gt 0 ]; then
    row repo tracked-worktree WARN "$dirty 个已跟踪文件有未提交改动"
  else
    row repo tracked-worktree PASS clean
  fi
else
  row repo HEAD FAIL "无法读取 git 状态"
fi

# ── 2. 契约 schema 指纹 ────────────────────────────────────────────────
schema="contracts/schemas/protocol.schema.json"
if [ -f "$schema" ]; then
  if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$schema" | cut -d' ' -f1)"
  else
    actual="$(shasum -a 256 "$schema" | cut -d' ' -f1)"
  fi
  if [ "$actual" = "$EXPECTED_SCHEMA" ]; then
    row contract schema-sha256 PASS "draft.10 登记值匹配"
  else
    row contract schema-sha256 FAIL "实际 ${actual:0:12}… 与登记值不符"
  fi
else
  row contract schema-sha256 FAIL "缺少 $schema"
fi

# ── 3. 工具链 ──────────────────────────────────────────────────────────
for tool in docker git; do
  if command -v "$tool" >/dev/null 2>&1; then row toolchain "$tool" PASS found; else row toolchain "$tool" FAIL "未安装"; fi
done
if docker compose version >/dev/null 2>&1; then
  row toolchain compose PASS "$(docker compose version --short 2>/dev/null)"
else
  row toolchain compose FAIL "docker compose 不可用"
fi

# ── 4. 环境变量文件 ────────────────────────────────────────────────────
REQUIRED_KEYS="KNOWFLOW_DATABASE_URL KNOWFLOW_DATABASE_USERNAME KNOWFLOW_DATABASE_PASSWORD
KNOWFLOW_MIGRATION_DATABASE_URL KNOWFLOW_MIGRATION_DATABASE_USERNAME KNOWFLOW_MIGRATION_DATABASE_PASSWORD
KNOWFLOW_AI_DATABASE_URL KNOWFLOW_STORAGE_ENDPOINT KNOWFLOW_STORAGE_BUCKET KNOWFLOW_STORAGE_ACCESS_KEY
KNOWFLOW_STORAGE_SECRET_KEY KNOWFLOW_INTERNAL_SHARED_SECRET KNOWFLOW_AI_BASE_URL KNOWFLOW_JAVA_BASE_URL
KNOWFLOW_API_BASE_URL KNOWFLOW_RUNTIME_PROFILE_ID KNOWFLOW_INDEXING_RUNTIME_PROFILE_ID
KNOWFLOW_EMBEDDING_BASE_URL KNOWFLOW_EMBEDDING_MODEL KNOWFLOW_EMBEDDING_DIMENSIONS KNOWFLOW_EMBEDDING_KEY_ENV
KNOWFLOW_LLM_BASE_URL KNOWFLOW_LLM_MODEL KNOWFLOW_LLM_KEY_ENV KNOWFLOW_WEB_MODEL_MODE"
SECRET_KEYS="KNOWFLOW_DATABASE_PASSWORD KNOWFLOW_MIGRATION_DATABASE_PASSWORD KNOWFLOW_STORAGE_SECRET_KEY
KNOWFLOW_INTERNAL_SHARED_SECRET KNOWFLOW_EMBEDDING_API_KEY KNOWFLOW_LLM_API_KEY"

if [ ! -f "$ENV_FILE" ]; then
  row env file FAIL "找不到 $ENV_FILE"
else
  row env file PASS "$(basename "$ENV_FILE")"
  get() { grep -E "^[[:space:]]*$1[[:space:]]*=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }
  missing=""
  for key in $REQUIRED_KEYS; do
    [ -z "$(get "$key")" ] && missing="$missing $key"
  done
  if [ -z "$missing" ]; then
    row env required-keys PASS "全部齐全"
  else
    row env required-keys FAIL "缺失或为空:$missing"
  fi

  for key in $SECRET_KEYS; do
    value="$(get "$key")"
    [ -z "$value" ] && continue
    case "$value" in
      *CHANGE_ME*|*changeme*|*dummy*|*example*|*placeholder*|*your-*|*xxxx*)
        row secret "$key" FAIL "像占位符（长度 ${#value}）" ;;
      *) if [ "${#value}" -lt 24 ]; then row secret "$key" WARN "长度 ${#value} < 24"; else row secret "$key" PASS "长度 ${#value}"; fi ;;
    esac
  done

  ai_profile="$(get KNOWFLOW_RUNTIME_PROFILE_ID)"
  api_profile="$(get KNOWFLOW_INDEXING_RUNTIME_PROFILE_ID)"
  if [ -n "$ai_profile" ] && [ -n "$api_profile" ] && [ "$ai_profile" != "$api_profile" ]; then
    row env runtime-profile FAIL "AI 与 API 的 runtime profile 不一致"
  else
    row env runtime-profile PASS 一致
  fi

  llm_base="$(get KNOWFLOW_LLM_BASE_URL)"
  if [ -n "$llm_base" ] && [ "$llm_base" != "https://api.deepseek.com" ]; then
    row env llm-endpoint FAIL "运行时只接受 https://api.deepseek.com"
  fi

  if [ "$(get KNOWFLOW_WEB_MODEL_MODE)" = "synthetic" ]; then
    row env model-mode WARN "仍是 synthetic：上线前需确认真实模式"
  fi
fi

# ── 5. 已跟踪文件中的密钥形态 ──────────────────────────────────────────
leaks="$(git ls-files -z | xargs -0 grep -lE 'sk-[A-Za-z0-9]{24,}' 2>/dev/null | head -n 5)"
if [ -z "$leaks" ]; then
  row secret tracked-key-scan PASS "无 sk- 形态密钥"
else
  row secret tracked-key-scan FAIL "疑似密钥：$(echo "$leaks" | tr '\n' ' ')"
fi

# ── 6. 镜像 digest 固定 ────────────────────────────────────────────────
unpinned="$(grep -rhE '^FROM[[:space:]]+' --include='Dockerfile*' . 2>/dev/null \
  | awk '{print $2}' | grep -v '@sha256:' | grep -v '^scratch$' | sort -u | tr '\n' ' ')"
if [ -z "$unpinned" ]; then
  row images dockerfile-digest PASS "全部已 pin"
else
  row images dockerfile-digest WARN "未 pin：$unpinned"
fi

# ── 7. 宿主资源 ────────────────────────────────────────────────────────
free_gb="$(df -Pk "$REPO_ROOT" | awk 'NR==2 {printf "%d", $4/1024/1024}')"
if [ "${free_gb:-0}" -ge "$MIN_DISK_GB" ]; then
  row host disk-free PASS "${free_gb} GB 可用（阈值 ${MIN_DISK_GB} GB）"
else
  row host disk-free FAIL "${free_gb} GB 可用，低于阈值 ${MIN_DISK_GB} GB"
fi

web_port="$( [ -f "$ENV_FILE" ] && grep -E '^[[:space:]]*KNOWFLOW_WEB_PORT[[:space:]]*=' "$ENV_FILE" | tail -n1 | cut -d= -f2 | tr -d ' \r' )"
web_port="${web_port:-3000}"
if command -v ss >/dev/null 2>&1; then
  if ss -ltn "sport = :$web_port" 2>/dev/null | grep -q LISTEN; then
    row host "port-$web_port" FAIL "已被占用"
  else
    row host "port-$web_port" PASS 空闲
  fi
else
  row host "port-$web_port" WARN "无 ss，跳过端口检查"
fi

echo
echo "FAIL=$fail WARN=$warn PASS=$pass"
if [ "$fail" -gt 0 ]; then
  echo "预检未通过：先清掉 FAIL 项再继续 PRODUCTION-CHECKLIST.md。"
  exit 1
fi
echo "预检通过（WARN 项需在部署记录里逐条说明）。"
exit 0
