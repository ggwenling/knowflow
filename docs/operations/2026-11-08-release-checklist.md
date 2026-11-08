# 发行清单（2026-11-08）

状态：**草案；发行合规签收未完成**。

## 1. 发行前置

- [ ] 契约冻结 `0.2.0`，Schema SHA-256 记录在案。
- [ ] 当前 SHA 的 Java / Python / Web CI 全绿（记录 run URL）。
- [ ] 三端完整消费签收与 M 人工签收完成（见 `contracts/consumer-draft10-checklist.md`）。
- [ ] 真人引用审阅完成（见 `docs/acceptance/2026-11-08-citation-human-review.md`）。
- [ ] PRICE/POLICY 与预算签核完成（见 `docs/acceptance/2026-11-08-price-policy-signoff.md`）。
- [ ] 版权主体确认，`LICENSE`/`NOTICE` 同步。
- [ ] 第三方许可清单与 SBOM 覆盖 Python、Java、`apps/web`、`apps/web-v2`。
- [ ] 生产环境承接项与回滚演练完成。

## 2. SBOM 与许可

| 栈 | 清单 | 现状 |
|---|---|---|
| Python | `services/ai/uv.lock` | 已在根清单覆盖历史基线 |
| Java | `services/api/pom.xml` | 已在根清单覆盖历史基线 |
| Web（旧） | `apps/web/package-lock.json` | 已在根清单覆盖 |
| Web v2 | `apps/web-v2/package-lock.json` | 已生成 `apps/web-v2/THIRD-PARTY-LICENSES.md`；**尚未合并进根清单/SBOM** |

建议命令（工具需先安装/确认）：

```powershell
cd apps/web-v2
npm sbom --sbom-format cyclonedx > ../../eval-out/sbom-web-v2.cdx.json
node scripts/generate-licenses.mjs
```

缺口：

- 根 `scripts/audit-dependencies.py` 只读取 `apps/web`，需扩展为多 Node lockfile。
- Maven/Python 的 CycloneDX 生成器尚未接入发布流水线。
- 第三方许可证**全文**尚未随镜像分发。

## 3. 构建与签名

1. 在干净工作树构建 `api`、`ai`、`web` 三个镜像。
2. 使用不可变 tag（内容摘要或 release SHA），禁止 `latest` 生产发布。
3. 生成校验和与签名：

```powershell
Get-FileHash .\release\* -Algorithm SHA256 | Out-File .\release\SHA256SUMS.txt
# cosign sign / 校验步骤按发行环境补充
```

4. 记录三个镜像 digest 与拉取后 digest 一致性。

## 4. 发布说明

发布说明至少包含：

- 版本、日期、契约版本与 Schema SHA；
- 变更摘要与已知问题；
- 升级/回滚步骤与数据迁移；
- 验证证据链接（CI、E2E、人工签收）；
- 第三方许可与 SBOM 位置。

## 5. 签字

| 项 | 负责人 | 日期 | 证据 |
|---|---|---|---|
| 代码/契约冻结 |  |  |  |
| 质量与人工签收 |  |  |  |
| 许可/SBOM |  |  |  |
| 构建/签名/校验和 |  |  |  |
| 发行批准 |  |  |  |

签字栏为空，直到实际发行完成。
