# KnowFlow 第三方许可清单

- 生成日期：2026-11-07（Asia/Shanghai）
- 代码基线：`local` 分支 HEAD `f2b5c67`；采集时三份依赖清单（`uv.lock`、`pom.xml`、`package-lock.json`）均无未提交改动
- Web v2 增补（2026-11-08）：`apps/web-v2/package-lock.json`（SHA-256 `24f6022bbf2e2e3794a5215596ab06cffb03103cff85b7c49efa88c487cd61be`）的 221 条生产依赖，追加在 §4 末尾；未与旧版 Node 清单去重。
- 性质：面向对外交付的**发行证据清单**，记录仓库实际声明/解析到的第三方依赖及其许可证元数据；不构成法律意见。

## 1. 取证来源与方法

| 栈 | 依赖清单 | SHA-256 | 许可证取证方式 |
|---|---|---|---|
| Python | `services/ai/uv.lock` | `a9bc533d8a029a6d6c10297bddeaf83cea11420d80427fb824ee790894d357c2` | 本机 `services/ai/.venv` 中各发行包 `dist-info/METADATA` 的 `License-Expression` / `License` / `Classifier` |
| Java | `services/api/pom.xml` + `./mvnw -o dependency:list` | `c6a640e24fe76b28c14f6e3b4c088ef179de32855bd4998dadef047d4afbc60e` | 各 artifact POM 的 `<licenses>` 声明（缺失时沿 `parent` 链上溯） |
| Node / Web | `apps/web/package-lock.json`（lockfileVersion 3） | `cb7bddb85868dd475eee91dbec1c7e9e10609e3a8d1f62b636c66a7589e0b8fe` | lockfile 条目的 `license` 字段 |
| Node / Web v2 | `apps/web-v2/package-lock.json` | `24f6022bbf2e2e3794a5215596ab06cffb03103cff85b7c49efa88c487cd61be` | 运行时闭包（`npm ls --omit=dev --all`）与 `node_modules/*/package.json` 的 `license` |

采集使用仓库内只读脚本 `scripts/audit-dependencies.py`；Java 依赖图由本机离线 Maven 仓库解析（`-o`，不访问网络）。

需要说明的取证边界：

- **Java classifier 行**：采集脚本按 5 段解析 `mvn` 输出，导致 `netty-resolver-dns-native-macos:osx-x86_64` 与 `netty-transport-native-epoll:linux-x86_64` 两条被记为 `UNKNOWN`。本清单按 6 段格式修正为 `4.1.135.Final`，许可证依据 `io.netty:netty-parent:4.1.135.Final` POM 的 Apache-2.0 声明；这两条已计入 Apache-2.0。
- **Node 平台可选依赖**：`@img/sharp-*` 在 lockfile 中登记全部平台变体，安装与镜像只包含目标平台的一个变体。本机为 Windows，仅安装 `@img/sharp-win32-x64@0.35.5`。
- **许可证写法**：上游元数据存在非 SPDX 写法（如 Python 的 `OSI Approved / BSD License`），清单保留原值，除上一条外不做推断性归并；汇总表中的归并仅用于计数，逐条原值见第 4 节。
- **作用域**：Python 作用域按 `uv.lock` 的运行时依赖组与 `dev` 组做依赖闭包推导；Java 作用域取自 `mvn dependency:list`；Node 作用域取自 lockfile 的 `dev` 标记。

## 2. 数量与许可证分布

- 总条目 **704** 条：Python **39**、Java **130**、Node **535**。
- 其中本项目自身 1 条（`knowflow-ai 0.1.0`，许可证未声明），第三方依赖 **703** 条。
- 运行时/开发划分：Java `compile`+`runtime` **87** 条、`test` **43** 条；Node 运行时 **63** 条、开发/构建 **472** 条；Python 运行时 **28** 条、开发/测试 **10** 条、本项目自身 1 条。
- **Web v2 增补**：独立运行时另有 **221** 条生产依赖（见 §4 末尾），上表与总数 **未合并** 这 221 条；发行 SBOM 应统一重算总量，且两版 Web 可并存回退，未按包名去重。

| 许可证 / 声明 | Python | Java | Node | 合计 |
|---|---|---|---|---|
| MIT | 19 | 10 | 423 | 452 |
| Apache-2.0 | 3 | 101 | 41 | 145 |
| ISC | — | — | 19 | 19 |
| MPL-2.0 | 1 | — | 13 | 14 |
| BSD-3-Clause | 7 | 3 | 3 | 13 |
| BSD-2-Clause | 1 | 1 | 9 | 11 |
| LGPL-3.0-or-later | — | — | 10 | 10 |
| EPL-2.0 | — | 6 | — | 6 |
| BlueOak-1.0.0 | — | — | 4 | 4 |
| Apache-2.0 AND LGPL-3.0-or-later | — | — | 3 | 3 |
| MIT-0 | — | 1 | 2 | 3 |
| BSD-3-Clause（上游写法未标版本） | 2 | — | — | 2 |
| CC0-1.0 | — | — | 2 | 2 |
| CC0-1.0 / Public Domain | — | 2 | — | 2 |
| EDL-1.0 | — | 2 | — | 2 |
| EPL-2.0 / LGPL-2.1-only（双许可） | — | 2 | — | 2 |
| LGPL-3.0-only | 2 | — | — | 2 |
| OFL-1.1 | — | — | 2 | 2 |
| 0BSD | — | — | 1 | 1 |
| Apache-2.0 AND LGPL-3.0-or-later AND MIT | — | — | 1 | 1 |
| Apache-2.0 OR BSD-2-Clause | 1 | — | — | 1 |
| CC-BY-4.0 | — | — | 1 | 1 |
| EPL-1.0 | — | 1 | — | 1 |
| EPL-2.0 / GPL-2.0-CPE（双许可） | — | 1 | — | 1 |
| MIT-CMU | 1 | — | — | 1 |
| PSF-2.0 | 1 | — | — | 1 |
| Python-2.0 | — | — | 1 | 1 |
| 本项目自身（未声明） | 1 | — | — | 1 |
| **合计** | **39** | **130** | **535** | **704** |

## 3. 兼容性结论与风险

### 3.1 结论

**未发现与 Apache-2.0 不兼容的必需依赖，可以采用 Apache-2.0 发行。** 全量 703 条第三方依赖中：

- 无 `GPL-2.0-only`、`GPL-3.0-only`、`AGPL`、`SSPL` 等强 copyleft 条目；
- 无“只能按 GPL 使用”的依赖。唯一带 GPL 选项的 `jakarta.annotation-api`（`EPL-2.0 / GPL-2.0-CPE`）按 EPL-2.0 使用，不触发 GPL；
- 弱 copyleft 组件（LGPL / MPL / EPL）均以独立模块或独立动态库方式使用，不要求本项目源码改用其许可证。

### 3.2 需要履行义务的组件（按发行路径）

| 组件 | 版本 | 许可证 | 影响与义务 | 风险 |
|---|---|---|---|---|
| `psycopg` / `psycopg-binary` | 3.3.6 | LGPL-3.0-only | AI 服务运行时依赖。保留版权与许可证声明；说明库可被替换；提供对应源码获取方式。不得把本库静态并入并修改后闭源分发。 | 中 |
| `@img/sharp-libvips-*` | 1.3.4 | LGPL-3.0-or-later | Web 镜像内 libvips 以独立原生库加载。保留声明、保持可替换、提供源码获取方式。 | 中 |
| `@img/sharp-win32-*`、`@img/sharp-wasm32` | 0.35.5 | Apache-2.0 AND LGPL-3.0-or-later（wasm32 另含 MIT） | 与 sharp 平台二进制同包分发，按 LGPL 条款保留声明与源码获取方式。 | 中 |
| `caniuse-lite` | 1.0.30001820 | CC-BY-4.0 | 必须署名数据来源（caniuse.com）；NOTICE 已列署名入口。 | 中 |
| `@fontsource/dm-sans`、`@fontsource/dm-serif-display` | 5.3.0 | OFL-1.1 | 随 Web 分发字体文件；需保留 OFL 全文与版权声明，不得使用保留字体名再发布修改版。 | 低 |
| `certifi` | 2026.10.23 | MPL-2.0 | 文件级 copyleft；未修改时保留声明即可；若修改其文件，需公开被修改文件源码。 | 低 |
| `logback-classic` / `logback-core` | 1.5.34 | EPL-2.0 / LGPL-2.1-only（双许可） | 本项目选择 EPL-2.0：保留声明与许可证全文，无源码开放义务。 | 低 |
| `jakarta.annotation-api` | 2.1.1 | EPL-2.0 / GPL-2.0-CPE（双许可） | 按 EPL-2.0 使用，避免 GPL 选项。 | 低 |
| `org.postgresql:postgresql` | 42.7.11 | BSD-2-Clause | 保留版权与免责声明。 | 低 |
| `HdrHistogram` / `LatencyUtils` | 2.2.2 / 2.0.3 | CC0-1.0 / Public Domain | 无强制署名义务。 | 低 |
| `reactive-streams` | 1.0.4 | MIT-0 | 无署名义务。 | 低 |

仅开发/测试作用域、不随运行时镜像分发的弱 copyleft 组件：`axe-core`（MPL-2.0）、`lightningcss` 及其平台变体（MPL-2.0）、JUnit 4/5 与 JUnit Platform（EPL-1.0 / EPL-2.0）、`jakarta.activation-api` 与 `jakarta.xml.bind-api`（EDL-1.0）、`jna`（Apache-2.0 / LGPL-2.1-or-later 双许可，按 Apache-2.0 使用）。

### 3.3 说明

- Apache-2.0 与 GPL-2.0 存在单向不兼容，因此若将来引入 `GPL-2.0-only` 依赖会构成阻断；当前清单无此情况。
- MPL-2.0、EPL-2.0 与 LGPL 均属弱 copyleft，与 Apache-2.0 项目并存无需改换本项目许可证，但上述署名/声明/可替换义务必须在发行物中落实。
- 本次核对**未替换、未升降级任何依赖**。

## 4. 完整依赖清单

说明：`来源` 列为该条许可证元数据的登记位置所属生态（PyPI / Maven Central / npm）；`作用域` 来自第 1 节所述推导方式。

### Python（39 条）

| 依赖 | 版本 | 作用域 | 许可证 | 来源 |
| --- | --- | --- | --- | --- |
| `annotated-doc` | 0.0.5 | 运行时 | MIT | PyPI |
| `annotated-types` | 0.8.0 | 运行时 | MIT | PyPI |
| `anyio` | 4.15.1 | 运行时 | MIT | PyPI |
| `attrs` | 26.1.0 | 运行时 | MIT | PyPI |
| `certifi` | 2026.10.23 | 运行时 | MPL-2.0 | PyPI |
| `charset-normalizer` | 3.5.2 | 开发/测试 | MIT | PyPI |
| `click` | 8.5.0 | 运行时 | BSD-3-Clause | PyPI |
| `colorama` | 0.4.6 | 开发/测试 | OSI Approved / BSD License | PyPI |
| `fastapi` | 0.162.0 | 运行时 | MIT | PyPI |
| `h11` | 0.16.0 | 运行时 | MIT | PyPI |
| `httpcore` | 1.0.9 | 运行时 | BSD-3-Clause | PyPI |
| `httpx` | 0.28.1 | 运行时 | BSD-3-Clause | PyPI |
| `idna` | 3.20 | 运行时 | BSD-3-Clause | PyPI |
| `iniconfig` | 2.3.1 | 开发/测试 | MIT | PyPI |
| `jsonschema` | 4.26.0 | 运行时 | MIT | PyPI |
| `jsonschema-specifications` | 2025.9.1 | 运行时 | MIT | PyPI |
| `knowflow-ai` | 0.1.0 | 本项目自身 | UNKNOWN | PyPI |
| `opentelemetry-api` | 1.45.2 | 运行时 | Apache-2.0 | PyPI |
| `packaging` | 26.3 | 开发/测试 | Apache-2.0 OR BSD-2-Clause | PyPI |
| `pillow` | 13.0.0 | 开发/测试 | MIT-CMU | PyPI |
| `pluggy` | 1.7.0 | 开发/测试 | MIT | PyPI |
| `psycopg` | 3.3.6 | 运行时 | LGPL-3.0-only | PyPI |
| `psycopg-binary` | 3.3.6 | 运行时 | LGPL-3.0-only | PyPI |
| `pydantic` | 2.14.2 | 运行时 | MIT | PyPI |
| `pydantic-core` | 2.50.2 | 运行时 | MIT | PyPI |
| `pygments` | 2.21.0 | 开发/测试 | BSD-2-Clause | PyPI |
| `pypdf` | 6.21.4 | 运行时 | BSD-3-Clause | PyPI |
| `pytest` | 9.2.0 | 开发/测试 | MIT | PyPI |
| `pytest-asyncio` | 1.4.1 | 开发/测试 | Apache-2.0 | PyPI |
| `referencing` | 0.37.0 | 运行时 | MIT | PyPI |
| `reportlab` | 5.1.0 | 开发/测试 | OSI Approved / BSD License | PyPI |
| `rfc3339-validator` | 0.1.4 | 运行时 | MIT license | PyPI |
| `rpds-py` | 2026.9.1 | 运行时 | MIT | PyPI |
| `six` | 1.17.0 | 运行时 | MIT | PyPI |
| `starlette` | 1.10.0 | 运行时 | BSD-3-Clause | PyPI |
| `typing-extensions` | 4.16.0 | 运行时+开发/测试 | PSF-2.0 | PyPI |
| `typing-inspection` | 0.4.4 | 运行时 | MIT | PyPI |
| `tzdata` | 2026.6 | 运行时 | Apache-2.0 | PyPI |
| `uvicorn` | 0.54.0 | 运行时 | BSD-3-Clause | PyPI |

### Java（130 条）

| 依赖（groupId:artifactId） | 版本 | 作用域 | 许可证 | 来源 |
| --- | --- | --- | --- | --- |
| `ch.qos.logback:logback-classic` | 1.5.34 | compile | EPL-2.0 / LGPL-2.1-only | Maven Central |
| `ch.qos.logback:logback-core` | 1.5.34 | compile | EPL-2.0 / LGPL-2.1-only | Maven Central |
| `com.fasterxml:classmate` | 1.7.3 | compile | Apache License, Version 2.0 | Maven Central |
| `com.fasterxml.jackson.core:jackson-annotations` | 2.21 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `com.fasterxml.jackson.core:jackson-core` | 2.21.4 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `com.fasterxml.jackson.core:jackson-databind` | 2.21.4 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `com.fasterxml.jackson.dataformat:jackson-dataformat-toml` | 2.21.4 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `com.fasterxml.jackson.datatype:jackson-datatype-jdk8` | 2.21.4 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `com.fasterxml.jackson.datatype:jackson-datatype-jsr310` | 2.21.4 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `com.fasterxml.jackson.module:jackson-module-parameter-names` | 2.21.4 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `com.github.docker-java:docker-java-api` | 3.4.2 | test | The Apache Software License, Version 2.0 | Maven Central |
| `com.github.docker-java:docker-java-transport` | 3.4.2 | test | The Apache Software License, Version 2.0 | Maven Central |
| `com.github.docker-java:docker-java-transport-zerodep` | 3.4.2 | test | The Apache Software License, Version 2.0 | Maven Central |
| `com.jayway.jsonpath:json-path` | 2.9.0 | test | The Apache Software License, Version 2.0 | Maven Central |
| `com.vaadin.external.google:android-json` | 0.0.20131108.vaadin1 | test | Apache License 2.0 | Maven Central |
| `com.zaxxer:HikariCP` | 6.3.3 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `commons-logging:commons-logging` | 1.4.0 | compile | Apache-2.0 | Maven Central |
| `io.micrometer:micrometer-commons` | 1.15.12 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `io.micrometer:micrometer-core` | 1.15.12 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `io.micrometer:micrometer-jakarta9` | 1.15.12 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `io.micrometer:micrometer-observation` | 1.15.12 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `io.netty:netty-buffer` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-codec` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-codec-dns` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-codec-http` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-codec-http2` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-codec-socks` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-common` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-handler` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-handler-proxy` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-resolver` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-resolver-dns` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-resolver-dns-classes-macos` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-resolver-dns-native-macos` | 4.1.135.Final | compile（classifier osx-x86_64） | Apache-2.0 | Maven Central |
| `io.netty:netty-transport` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-transport-classes-epoll` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.netty:netty-transport-native-epoll` | 4.1.135.Final | compile（classifier linux-x86_64） | Apache-2.0 | Maven Central |
| `io.netty:netty-transport-native-unix-common` | 4.1.135.Final | compile | Apache License, Version 2.0 | Maven Central |
| `io.projectreactor:reactor-core` | 3.7.19 | compile | Apache License, Version 2.0 | Maven Central |
| `io.projectreactor.netty:reactor-netty-core` | 1.2.18 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `io.projectreactor.netty:reactor-netty-http` | 1.2.18 | compile | The Apache Software License, Version 2.0 | Maven Central |
| `jakarta.activation:jakarta.activation-api` | 2.1.4 | test | EDL 1.0 | Maven Central |
| `jakarta.annotation:jakarta.annotation-api` | 2.1.1 | compile | EPL 2.0 / GPL2 w/ CPE | Maven Central |
| `jakarta.validation:jakarta.validation-api` | 3.0.2 | compile | Apache License 2.0 | Maven Central |
| `jakarta.xml.bind:jakarta.xml.bind-api` | 4.0.5 | test | Eclipse Distribution License - v 1.0 | Maven Central |
| `junit:junit` | 4.13.2 | test | Eclipse Public License 1.0 | Maven Central |
| `net.bytebuddy:byte-buddy` | 1.17.8 | test | Apache License, Version 2.0 | Maven Central |
| `net.bytebuddy:byte-buddy-agent` | 1.17.8 | test | Apache License, Version 2.0 | Maven Central |
| `net.java.dev.jna:jna` | 5.13.0 | test | LGPL-2.1-or-later / Apache-2.0 | Maven Central |
| `net.minidev:accessors-smart` | 2.5.2 | test | The Apache Software License, Version 2.0 | Maven Central |
| `net.minidev:json-smart` | 2.5.2 | test | The Apache Software License, Version 2.0 | Maven Central |
| `org.apache.commons:commons-compress` | 1.24.0 | test | Apache-2.0 | Maven Central |
| `org.apache.logging.log4j:log4j-api` | 2.24.3 | compile | Apache-2.0 | Maven Central |
| `org.apache.logging.log4j:log4j-to-slf4j` | 2.24.3 | compile | Apache-2.0 | Maven Central |
| `org.apache.pdfbox:fontbox` | 3.0.8 | compile | Apache-2.0 | Maven Central |
| `org.apache.pdfbox:pdfbox` | 3.0.8 | compile | Apache-2.0 | Maven Central |
| `org.apache.pdfbox:pdfbox-io` | 3.0.8 | compile | Apache-2.0 | Maven Central |
| `org.apache.tomcat.embed:tomcat-embed-core` | 10.1.55 | compile | Apache License, Version 2.0 | Maven Central |
| `org.apache.tomcat.embed:tomcat-embed-el` | 10.1.55 | compile | Apache License, Version 2.0 | Maven Central |
| `org.apache.tomcat.embed:tomcat-embed-websocket` | 10.1.55 | compile | Apache License, Version 2.0 | Maven Central |
| `org.apiguardian:apiguardian-api` | 1.1.2 | test | The Apache License, Version 2.0 | Maven Central |
| `org.assertj:assertj-core` | 3.27.7 | test | Apache-2.0 | Maven Central |
| `org.awaitility:awaitility` | 4.2.2 | test | Apache 2.0 | Maven Central |
| `org.flywaydb:flyway-core` | 11.7.2 | compile | Apache License, Version 2.0 | Maven Central |
| `org.flywaydb:flyway-database-postgresql` | 11.7.2 | compile | Apache License, Version 2.0 | Maven Central |
| `org.hamcrest:hamcrest` | 3.0 | test | BSD-3-Clause | Maven Central |
| `org.hamcrest:hamcrest-core` | 3.0 | test | BSD-3-Clause | Maven Central |
| `org.hdrhistogram:HdrHistogram` | 2.2.2 | runtime | Public Domain, per Creative Commons CC0 / BSD-2-Clause | Maven Central |
| `org.hibernate.validator:hibernate-validator` | 8.0.3.Final | compile | Apache License 2.0 | Maven Central |
| `org.jboss.logging:jboss-logging` | 3.6.3.Final | compile | Apache License 2.0 | Maven Central |
| `org.jetbrains:annotations` | 17.0.0 | test | The Apache Software License, Version 2.0 | Maven Central |
| `org.junit.jupiter:junit-jupiter` | 5.12.2 | test | Eclipse Public License v2.0 | Maven Central |
| `org.junit.jupiter:junit-jupiter-api` | 5.12.2 | test | Eclipse Public License v2.0 | Maven Central |
| `org.junit.jupiter:junit-jupiter-engine` | 5.12.2 | test | Eclipse Public License v2.0 | Maven Central |
| `org.junit.jupiter:junit-jupiter-params` | 5.12.2 | test | Eclipse Public License v2.0 | Maven Central |
| `org.junit.platform:junit-platform-commons` | 1.12.2 | test | Eclipse Public License v2.0 | Maven Central |
| `org.junit.platform:junit-platform-engine` | 1.12.2 | test | Eclipse Public License v2.0 | Maven Central |
| `org.latencyutils:LatencyUtils` | 2.0.3 | runtime | Public Domain, per Creative Commons CC0 | Maven Central |
| `org.mockito:mockito-core` | 5.17.0 | test | MIT | Maven Central |
| `org.mockito:mockito-junit-jupiter` | 5.17.0 | test | MIT | Maven Central |
| `org.objenesis:objenesis` | 3.3 | test | Apache License, Version 2.0 | Maven Central |
| `org.opentest4j:opentest4j` | 1.3.0 | test | The Apache License, Version 2.0 | Maven Central |
| `org.ow2.asm:asm` | 9.7.1 | test | BSD-3-Clause | Maven Central |
| `org.postgresql:postgresql` | 42.7.11 | runtime | BSD-2-Clause | Maven Central |
| `org.reactivestreams:reactive-streams` | 1.0.4 | compile | MIT-0 | Maven Central |
| `org.rnorth.duct-tape:duct-tape` | 1.0.8 | test | MIT | Maven Central |
| `org.skyscreamer:jsonassert` | 1.5.3 | test | The Apache Software License, Version 2.0 | Maven Central |
| `org.slf4j:jul-to-slf4j` | 2.0.18 | compile | MIT | Maven Central |
| `org.slf4j:slf4j-api` | 2.0.18 | compile | MIT | Maven Central |
| `org.springframework:spring-aop` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-beans` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-context` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-core` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-expression` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-jcl` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-jdbc` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-test` | 6.2.19 | test | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-tx` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-web` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-webflux` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework:spring-webmvc` | 6.2.19 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-actuator` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-actuator-autoconfigure` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-autoconfigure` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-actuator` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-jdbc` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-json` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-logging` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-reactor-netty` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-security` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-test` | 3.5.16 | test | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-tomcat` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-validation` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-web` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-starter-webflux` | 3.5.16 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-test` | 3.5.16 | test | Apache License, Version 2.0 | Maven Central |
| `org.springframework.boot:spring-boot-test-autoconfigure` | 3.5.16 | test | Apache License, Version 2.0 | Maven Central |
| `org.springframework.security:spring-security-config` | 6.5.11 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.security:spring-security-core` | 6.5.11 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.security:spring-security-crypto` | 6.5.11 | compile | Apache License, Version 2.0 | Maven Central |
| `org.springframework.security:spring-security-web` | 6.5.11 | compile | Apache License, Version 2.0 | Maven Central |
| `org.testcontainers:database-commons` | 1.21.4 | test | MIT | Maven Central |
| `org.testcontainers:jdbc` | 1.21.4 | test | MIT | Maven Central |
| `org.testcontainers:junit-jupiter` | 1.21.4 | test | MIT | Maven Central |
| `org.testcontainers:postgresql` | 1.21.4 | test | MIT | Maven Central |
| `org.testcontainers:testcontainers` | 1.21.4 | test | MIT | Maven Central |
| `org.xmlunit:xmlunit-core` | 2.10.4 | test | The Apache Software License, Version 2.0 | Maven Central |
| `org.yaml:snakeyaml` | 2.4 | compile | Apache License, Version 2.0 | Maven Central |

### Node / Web（535 条）

| 依赖 | 版本 | 作用域 | 许可证 | 来源 |
| --- | --- | --- | --- | --- |
| `@acemir/cssom` | 0.9.32 | 开发/构建 | MIT | npm |
| `@adobe/css-tools` | 4.5.0 | 开发/构建 | MIT | npm |
| `@asamuzakjp/css-color` | 4.1.2 | 开发/构建 | MIT | npm |
| `@asamuzakjp/dom-selector` | 6.8.1 | 开发/构建 | MIT | npm |
| `@asamuzakjp/nwsapi` | 2.3.9 | 开发/构建 | MIT | npm |
| `@babel/code-frame` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/compat-data` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/core` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/generator` | 7.29.12 | 开发/构建 | MIT | npm |
| `@babel/helper-compilation-targets` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/helper-globals` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/helper-module-imports` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/helper-module-transforms` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/helper-string-parser` | 7.29.11 | 开发/构建 | MIT | npm |
| `@babel/helper-validator-identifier` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/helper-validator-option` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/helpers` | 7.29.10 | 开发/构建 | MIT | npm |
| `@babel/parser` | 7.29.12 | 开发/构建 | MIT | npm |
| `@babel/runtime` | 7.29.10 | 开发/构建 | MIT | npm |
| `@babel/template` | 7.29.7 | 开发/构建 | MIT | npm |
| `@babel/traverse` | 7.29.12 | 开发/构建 | MIT | npm |
| `@babel/types` | 7.29.11 | 开发/构建 | MIT | npm |
| `@csstools/color-helpers` | 6.1.2 | 开发/构建 | MIT-0 | npm |
| `@csstools/css-calc` | 3.4.3 | 开发/构建 | MIT | npm |
| `@csstools/css-color-parser` | 4.2.7 | 开发/构建 | MIT | npm |
| `@csstools/css-parser-algorithms` | 4.0.2 | 开发/构建 | MIT | npm |
| `@csstools/css-syntax-patches-for-csstree` | 1.1.16 | 开发/构建 | MIT-0 | npm |
| `@csstools/css-tokenizer` | 4.0.2 | 开发/构建 | MIT | npm |
| `@dimforge/rapier3d-compat` | 0.12.0 | 开发/构建 | Apache-2.0 | npm |
| `@emnapi/runtime` | 1.11.3 | 运行时 | MIT | npm |
| `@eslint-community/eslint-utils` | 4.10.1 | 开发/构建 | MIT | npm |
| `@eslint-community/eslint-utils` | 4.9.1 | 开发/构建 | MIT | npm |
| `@eslint-community/regexpp` | 4.12.2 | 开发/构建 | MIT | npm |
| `@eslint/config-array` | 0.21.2 | 开发/构建 | Apache-2.0 | npm |
| `@eslint/config-helpers` | 0.4.2 | 开发/构建 | Apache-2.0 | npm |
| `@eslint/core` | 0.17.0 | 开发/构建 | Apache-2.0 | npm |
| `@eslint/eslintrc` | 3.3.7 | 开发/构建 | MIT | npm |
| `@eslint/js` | 9.39.4 | 开发/构建 | MIT | npm |
| `@eslint/object-schema` | 2.1.7 | 开发/构建 | Apache-2.0 | npm |
| `@eslint/plugin-kit` | 0.4.1 | 开发/构建 | Apache-2.0 | npm |
| `@exodus/bytes` | 1.16.0 | 开发/构建 | MIT | npm |
| `@fontsource/dm-sans` | 5.3.0 | 运行时 | OFL-1.1 | npm |
| `@fontsource/dm-serif-display` | 5.3.0 | 运行时 | OFL-1.1 | npm |
| `@humanfs/core` | 0.19.2 | 开发/构建 | Apache-2.0 | npm |
| `@humanfs/node` | 0.16.8 | 开发/构建 | Apache-2.0 | npm |
| `@humanfs/types` | 0.15.0 | 开发/构建 | Apache-2.0 | npm |
| `@humanwhocodes/module-importer` | 1.0.1 | 开发/构建 | Apache-2.0 | npm |
| `@humanwhocodes/retry` | 0.4.3 | 开发/构建 | Apache-2.0 | npm |
| `@img/colour` | 1.1.0 | 运行时 | MIT | npm |
| `@img/sharp-darwin-arm64` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-darwin-x64` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-freebsd-wasm32` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-libvips-darwin-arm64` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-libvips-darwin-x64` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-libvips-linux-arm` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-libvips-linux-arm64` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-libvips-linux-ppc64` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-libvips-linux-riscv64` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-libvips-linux-s390x` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-libvips-linux-x64` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-libvips-linuxmusl-arm64` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-libvips-linuxmusl-x64` | 1.3.4 | 运行时 | LGPL-3.0-or-later | npm |
| `@img/sharp-linux-arm` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-linux-arm64` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-linux-ppc64` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-linux-riscv64` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-linux-s390x` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-linux-x64` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-linuxmusl-arm64` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-linuxmusl-x64` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-wasm32` | 0.35.5 | 运行时 | Apache-2.0 AND LGPL-3.0-or-later AND MIT | npm |
| `@img/sharp-webcontainers-wasm32` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `@img/sharp-win32-arm64` | 0.35.5 | 运行时 | Apache-2.0 AND LGPL-3.0-or-later | npm |
| `@img/sharp-win32-ia32` | 0.35.5 | 运行时 | Apache-2.0 AND LGPL-3.0-or-later | npm |
| `@img/sharp-win32-x64` | 0.35.5 | 运行时 | Apache-2.0 AND LGPL-3.0-or-later | npm |
| `@jridgewell/gen-mapping` | 0.3.13 | 开发/构建 | MIT | npm |
| `@jridgewell/remapping` | 2.3.5 | 开发/构建 | MIT | npm |
| `@jridgewell/resolve-uri` | 3.1.2 | 开发/构建 | MIT | npm |
| `@jridgewell/sourcemap-codec` | 1.6.0 | 开发/构建 | MIT | npm |
| `@jridgewell/trace-mapping` | 0.3.31 | 开发/构建 | MIT | npm |
| `@next/env` | 16.4.3 | 运行时 | MIT | npm |
| `@next/eslint-plugin-next` | 16.4.3 | 开发/构建 | MIT | npm |
| `@next/swc-darwin-arm64` | 16.4.3 | 运行时 | MIT | npm |
| `@next/swc-darwin-x64` | 16.4.3 | 运行时 | MIT | npm |
| `@next/swc-linux-arm64-gnu` | 16.4.3 | 运行时 | MIT | npm |
| `@next/swc-linux-arm64-musl` | 16.4.3 | 运行时 | MIT | npm |
| `@next/swc-linux-x64-gnu` | 16.4.3 | 运行时 | MIT | npm |
| `@next/swc-linux-x64-musl` | 16.4.3 | 运行时 | MIT | npm |
| `@next/swc-win32-arm64-msvc` | 16.4.3 | 运行时 | MIT | npm |
| `@next/swc-win32-x64-msvc` | 16.4.3 | 运行时 | MIT | npm |
| `@nodelib/fs.scandir` | 2.1.5 | 开发/构建 | MIT | npm |
| `@nodelib/fs.stat` | 2.0.5 | 开发/构建 | MIT | npm |
| `@nodelib/fs.walk` | 1.2.8 | 开发/构建 | MIT | npm |
| `@nolyfill/is-core-module` | 1.0.39 | 开发/构建 | MIT | npm |
| `@oxc-project/types` | 0.156.0 | 开发/构建 | MIT | npm |
| `@playwright/test` | 1.64.1 | 运行时 | Apache-2.0 | npm |
| `@rolldown/binding-android-arm-eabi` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-android-arm64` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-darwin-arm64` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-darwin-x64` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-freebsd-x64` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-linux-arm-gnueabihf` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-linux-arm64-gnu` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-linux-arm64-musl` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-linux-ppc64-gnu` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-linux-s390x-gnu` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-linux-x64-gnu` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-linux-x64-musl` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-openharmony-arm64` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-win32-arm64-msvc` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/binding-win32-x64-msvc` | 1.2.16 | 开发/构建 | MIT | npm |
| `@rolldown/pluginutils` | 1.0.1 | 开发/构建 | MIT | npm |
| `@rtsao/scc` | 1.1.0 | 开发/构建 | MIT | npm |
| `@standard-schema/spec` | 1.1.0 | 开发/构建 | MIT | npm |
| `@swc/helpers` | 0.5.23 | 运行时 | Apache-2.0 | npm |
| `@testing-library/dom` | 10.4.2 | 开发/构建 | MIT | npm |
| `@testing-library/jest-dom` | 6.9.1 | 开发/构建 | MIT | npm |
| `@testing-library/react` | 16.3.3 | 开发/构建 | MIT | npm |
| `@tweenjs/tween.js` | 23.1.3 | 开发/构建 | MIT | npm |
| `@types/aria-query` | 5.0.4 | 开发/构建 | MIT | npm |
| `@types/chai` | 5.2.3 | 开发/构建 | MIT | npm |
| `@types/deep-eql` | 4.0.2 | 开发/构建 | MIT | npm |
| `@types/estree` | 1.0.10 | 开发/构建 | MIT | npm |
| `@types/json-schema` | 7.0.15 | 开发/构建 | MIT | npm |
| `@types/json5` | 0.0.29 | 开发/构建 | MIT | npm |
| `@types/node` | 24.19.2 | 开发/构建 | MIT | npm |
| `@types/react` | 19.3.0 | 运行时 | MIT | npm |
| `@types/react-dom` | 19.3.0 | 开发/构建 | MIT | npm |
| `@types/stats.js` | 0.17.4 | 开发/构建 | MIT | npm |
| `@types/three` | 0.187.0 | 开发/构建 | MIT | npm |
| `@types/webxr` | 0.5.24 | 开发/构建 | MIT | npm |
| `@typescript-eslint/eslint-plugin` | 8.72.1 | 开发/构建 | MIT | npm |
| `@typescript-eslint/parser` | 8.72.1 | 开发/构建 | MIT | npm |
| `@typescript-eslint/project-service` | 8.72.1 | 开发/构建 | MIT | npm |
| `@typescript-eslint/scope-manager` | 8.72.1 | 开发/构建 | MIT | npm |
| `@typescript-eslint/tsconfig-utils` | 8.72.1 | 开发/构建 | MIT | npm |
| `@typescript-eslint/type-utils` | 8.72.1 | 开发/构建 | MIT | npm |
| `@typescript-eslint/types` | 8.72.1 | 开发/构建 | MIT | npm |
| `@typescript-eslint/typescript-estree` | 8.72.1 | 开发/构建 | MIT | npm |
| `@typescript-eslint/utils` | 8.72.1 | 开发/构建 | MIT | npm |
| `@typescript-eslint/visitor-keys` | 8.72.1 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-android-arm-eabi` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-android-arm64` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-darwin-arm64` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-darwin-x64` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-freebsd-x64` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-arm-gnueabihf` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-arm-musleabihf` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-arm64-gnu` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-arm64-musl` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-loong64-gnu` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-loong64-musl` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-ppc64-gnu` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-riscv64-gnu` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-riscv64-musl` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-s390x-gnu` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-x64-gnu` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-linux-x64-musl` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-openharmony-arm64` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-win32-arm64-msvc` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-win32-ia32-msvc` | 1.13.0 | 开发/构建 | MIT | npm |
| `@unrs/resolver-binding-win32-x64-msvc` | 1.13.0 | 开发/构建 | MIT | npm |
| `@vitest/expect` | 4.1.12 | 开发/构建 | MIT | npm |
| `@vitest/mocker` | 4.1.12 | 开发/构建 | MIT | npm |
| `@vitest/pretty-format` | 4.1.12 | 开发/构建 | MIT | npm |
| `@vitest/runner` | 4.1.12 | 开发/构建 | MIT | npm |
| `@vitest/snapshot` | 4.1.12 | 开发/构建 | MIT | npm |
| `@vitest/spy` | 4.1.12 | 开发/构建 | MIT | npm |
| `@vitest/utils` | 4.1.12 | 开发/构建 | MIT | npm |
| `acorn` | 8.19.0 | 开发/构建 | MIT | npm |
| `acorn-jsx` | 5.3.2 | 开发/构建 | MIT | npm |
| `agent-base` | 7.1.4 | 开发/构建 | MIT | npm |
| `ajv` | 6.15.0 | 开发/构建 | MIT | npm |
| `ansi-regex` | 5.0.1 | 开发/构建 | MIT | npm |
| `ansi-styles` | 4.3.0 | 开发/构建 | MIT | npm |
| `ansi-styles` | 5.2.0 | 开发/构建 | MIT | npm |
| `argparse` | 2.0.1 | 开发/构建 | Python-2.0 | npm |
| `aria-query` | 5.3.0 | 开发/构建 | Apache-2.0 | npm |
| `aria-query` | 5.3.2 | 开发/构建 | Apache-2.0 | npm |
| `array-buffer-byte-length` | 1.0.2 | 开发/构建 | MIT | npm |
| `array-includes` | 3.2.0 | 开发/构建 | MIT | npm |
| `array.prototype.findlast` | 1.2.5 | 开发/构建 | MIT | npm |
| `array.prototype.findlastindex` | 1.2.6 | 开发/构建 | MIT | npm |
| `array.prototype.flat` | 1.3.3 | 开发/构建 | MIT | npm |
| `array.prototype.flatmap` | 1.3.3 | 开发/构建 | MIT | npm |
| `array.prototype.tosorted` | 1.1.4 | 开发/构建 | MIT | npm |
| `arraybuffer.prototype.slice` | 1.0.4 | 开发/构建 | MIT | npm |
| `assertion-error` | 2.0.1 | 开发/构建 | MIT | npm |
| `ast-types-flow` | 0.0.8 | 开发/构建 | MIT | npm |
| `async-function` | 1.0.0 | 开发/构建 | MIT | npm |
| `available-typed-arrays` | 1.0.7 | 开发/构建 | MIT | npm |
| `axe-core` | 4.14.0 | 开发/构建 | MPL-2.0 | npm |
| `axobject-query` | 4.1.0 | 开发/构建 | Apache-2.0 | npm |
| `balanced-match` | 1.0.2 | 开发/构建 | MIT | npm |
| `balanced-match` | 4.0.4 | 开发/构建 | MIT | npm |
| `baseline-browser-mapping` | 2.11.34 | 运行时 | Apache-2.0 | npm |
| `bidi-js` | 1.1.0 | 开发/构建 | MIT | npm |
| `brace-expansion` | 1.1.21 | 开发/构建 | MIT | npm |
| `brace-expansion` | 5.0.12 | 开发/构建 | MIT | npm |
| `braces` | 3.0.3 | 开发/构建 | MIT | npm |
| `browserslist` | 4.29.5 | 开发/构建 | MIT | npm |
| `call-bind` | 1.0.9 | 开发/构建 | MIT | npm |
| `call-bind-apply-helpers` | 1.0.2 | 开发/构建 | MIT | npm |
| `call-bound` | 1.0.4 | 开发/构建 | MIT | npm |
| `callsites` | 3.1.0 | 开发/构建 | MIT | npm |
| `caniuse-lite` | 1.0.30001820 | 运行时 | CC-BY-4.0 | npm |
| `chai` | 6.3.0 | 开发/构建 | MIT | npm |
| `chalk` | 4.1.2 | 开发/构建 | MIT | npm |
| `client-only` | 0.0.1 | 运行时 | MIT | npm |
| `color-convert` | 2.0.1 | 开发/构建 | MIT | npm |
| `color-name` | 1.1.4 | 开发/构建 | MIT | npm |
| `concat-map` | 0.0.1 | 开发/构建 | MIT | npm |
| `convert-source-map` | 2.0.0 | 开发/构建 | MIT | npm |
| `cross-spawn` | 7.0.6 | 开发/构建 | MIT | npm |
| `css-tree` | 3.2.1 | 开发/构建 | MIT | npm |
| `css.escape` | 1.5.1 | 开发/构建 | MIT | npm |
| `cssstyle` | 5.3.7 | 开发/构建 | MIT | npm |
| `csstype` | 3.2.3 | 运行时 | MIT | npm |
| `damerau-levenshtein` | 1.0.8 | 开发/构建 | BSD-2-Clause | npm |
| `data-urls` | 6.0.1 | 开发/构建 | MIT | npm |
| `data-view-buffer` | 1.0.2 | 开发/构建 | MIT | npm |
| `data-view-byte-length` | 1.0.2 | 开发/构建 | MIT | npm |
| `data-view-byte-offset` | 1.0.1 | 开发/构建 | MIT | npm |
| `debug` | 3.2.7 | 开发/构建 | MIT | npm |
| `debug` | 3.2.7 | 开发/构建 | MIT | npm |
| `debug` | 3.2.7 | 开发/构建 | MIT | npm |
| `debug` | 4.4.3 | 开发/构建 | MIT | npm |
| `decimal.js` | 10.6.0 | 开发/构建 | MIT | npm |
| `deep-is` | 0.1.4 | 开发/构建 | MIT | npm |
| `define-data-property` | 1.1.4 | 开发/构建 | MIT | npm |
| `define-properties` | 1.2.1 | 开发/构建 | MIT | npm |
| `dequal` | 2.0.3 | 开发/构建 | MIT | npm |
| `detect-libc` | 2.1.2 | 运行时 | Apache-2.0 | npm |
| `doctrine` | 2.1.0 | 开发/构建 | Apache-2.0 | npm |
| `dom-accessibility-api` | 0.5.16 | 开发/构建 | MIT | npm |
| `dom-accessibility-api` | 0.6.3 | 开发/构建 | MIT | npm |
| `dunder-proto` | 1.0.1 | 开发/构建 | MIT | npm |
| `electron-to-chromium` | 1.5.472 | 开发/构建 | ISC | npm |
| `emoji-regex` | 9.2.2 | 开发/构建 | MIT | npm |
| `entities` | 8.1.0 | 开发/构建 | BSD-2-Clause | npm |
| `es-abstract` | 1.24.2 | 开发/构建 | MIT | npm |
| `es-abstract-get` | 1.0.0 | 开发/构建 | MIT | npm |
| `es-define-property` | 1.0.1 | 开发/构建 | MIT | npm |
| `es-errors` | 1.3.0 | 开发/构建 | MIT | npm |
| `es-iterator-helpers` | 1.4.0 | 开发/构建 | MIT | npm |
| `es-module-lexer` | 2.3.2 | 开发/构建 | MIT | npm |
| `es-object-atoms` | 1.1.2 | 开发/构建 | MIT | npm |
| `es-set-tostringtag` | 2.1.0 | 开发/构建 | MIT | npm |
| `es-shim-unscopables` | 1.1.0 | 开发/构建 | MIT | npm |
| `es-to-primitive` | 1.3.4 | 开发/构建 | MIT | npm |
| `escalade` | 3.2.0 | 开发/构建 | MIT | npm |
| `escape-string-regexp` | 4.0.0 | 开发/构建 | MIT | npm |
| `eslint` | 9.39.4 | 开发/构建 | MIT | npm |
| `eslint-config-next` | 16.4.3 | 开发/构建 | MIT | npm |
| `eslint-import-resolver-node` | 0.3.10 | 开发/构建 | MIT | npm |
| `eslint-import-resolver-typescript` | 3.10.1 | 开发/构建 | ISC | npm |
| `eslint-module-utils` | 2.14.0 | 开发/构建 | MIT | npm |
| `eslint-plugin-import` | 2.32.0 | 开发/构建 | MIT | npm |
| `eslint-plugin-jsx-a11y` | 6.10.2 | 开发/构建 | MIT | npm |
| `eslint-plugin-react` | 7.37.5 | 开发/构建 | MIT | npm |
| `eslint-plugin-react-hooks` | 7.1.1 | 开发/构建 | MIT | npm |
| `eslint-scope` | 8.4.0 | 开发/构建 | BSD-2-Clause | npm |
| `eslint-visitor-keys` | 3.4.3 | 开发/构建 | Apache-2.0 | npm |
| `eslint-visitor-keys` | 3.4.3 | 开发/构建 | Apache-2.0 | npm |
| `eslint-visitor-keys` | 4.2.1 | 开发/构建 | Apache-2.0 | npm |
| `eslint-visitor-keys` | 5.0.1 | 开发/构建 | Apache-2.0 | npm |
| `espree` | 10.4.0 | 开发/构建 | BSD-2-Clause | npm |
| `esquery` | 1.7.0 | 开发/构建 | BSD-3-Clause | npm |
| `esrecurse` | 4.3.0 | 开发/构建 | BSD-2-Clause | npm |
| `estraverse` | 5.3.0 | 开发/构建 | BSD-2-Clause | npm |
| `estree-walker` | 3.0.3 | 开发/构建 | MIT | npm |
| `esutils` | 2.0.3 | 开发/构建 | BSD-2-Clause | npm |
| `expect-type` | 1.4.0 | 开发/构建 | Apache-2.0 | npm |
| `fast-deep-equal` | 3.1.3 | 开发/构建 | MIT | npm |
| `fast-glob` | 3.3.1 | 开发/构建 | MIT | npm |
| `fast-json-stable-stringify` | 2.1.0 | 开发/构建 | MIT | npm |
| `fast-levenshtein` | 2.0.6 | 开发/构建 | MIT | npm |
| `fastq` | 1.20.3 | 开发/构建 | ISC | npm |
| `fdir` | 6.5.0 | 开发/构建 | MIT | npm |
| `fflate` | 0.8.3 | 开发/构建 | MIT | npm |
| `file-entry-cache` | 8.0.0 | 开发/构建 | MIT | npm |
| `fill-range` | 7.1.1 | 开发/构建 | MIT | npm |
| `find-up` | 5.0.0 | 开发/构建 | MIT | npm |
| `flat-cache` | 4.0.1 | 开发/构建 | MIT | npm |
| `flatted` | 3.4.4 | 开发/构建 | ISC | npm |
| `for-each` | 0.3.5 | 开发/构建 | MIT | npm |
| `fsevents` | 2.3.3 | 开发/构建 | MIT | npm |
| `function-bind` | 1.1.2 | 开发/构建 | MIT | npm |
| `function.prototype.name` | 1.2.0 | 开发/构建 | MIT | npm |
| `functions-have-names` | 1.2.3 | 开发/构建 | MIT | npm |
| `generator-function` | 2.0.1 | 开发/构建 | MIT | npm |
| `gensync` | 1.0.0-beta.2 | 开发/构建 | MIT | npm |
| `get-intrinsic` | 1.3.0 | 开发/构建 | MIT | npm |
| `get-proto` | 1.0.1 | 开发/构建 | MIT | npm |
| `get-symbol-description` | 1.1.0 | 开发/构建 | MIT | npm |
| `get-tsconfig` | 4.14.3 | 开发/构建 | MIT | npm |
| `glob-parent` | 5.1.2 | 开发/构建 | ISC | npm |
| `glob-parent` | 6.0.2 | 开发/构建 | ISC | npm |
| `globals` | 14.0.0 | 开发/构建 | MIT | npm |
| `globals` | 16.4.0 | 开发/构建 | MIT | npm |
| `globalthis` | 1.0.4 | 开发/构建 | MIT | npm |
| `gopd` | 1.2.0 | 开发/构建 | MIT | npm |
| `has-bigints` | 1.1.0 | 开发/构建 | MIT | npm |
| `has-flag` | 4.0.0 | 开发/构建 | MIT | npm |
| `has-property-descriptors` | 1.0.2 | 开发/构建 | MIT | npm |
| `has-proto` | 1.2.0 | 开发/构建 | MIT | npm |
| `has-symbols` | 1.1.0 | 开发/构建 | MIT | npm |
| `has-tostringtag` | 1.0.2 | 开发/构建 | MIT | npm |
| `hasown` | 2.0.4 | 开发/构建 | MIT | npm |
| `hermes-estree` | 0.25.1 | 开发/构建 | MIT | npm |
| `hermes-parser` | 0.25.1 | 开发/构建 | MIT | npm |
| `html-encoding-sniffer` | 6.0.0 | 开发/构建 | MIT | npm |
| `http-proxy-agent` | 7.0.2 | 开发/构建 | MIT | npm |
| `https-proxy-agent` | 7.0.6 | 开发/构建 | MIT | npm |
| `ignore` | 5.3.2 | 开发/构建 | MIT | npm |
| `ignore` | 7.0.14 | 开发/构建 | MIT | npm |
| `import-fresh` | 3.3.1 | 开发/构建 | MIT | npm |
| `imurmurhash` | 0.1.4 | 开发/构建 | MIT | npm |
| `indent-string` | 4.0.0 | 开发/构建 | MIT | npm |
| `internal-slot` | 1.1.0 | 开发/构建 | MIT | npm |
| `is-array-buffer` | 3.0.5 | 开发/构建 | MIT | npm |
| `is-async-function` | 2.1.1 | 开发/构建 | MIT | npm |
| `is-bigint` | 1.1.0 | 开发/构建 | MIT | npm |
| `is-boolean-object` | 1.2.2 | 开发/构建 | MIT | npm |
| `is-bun-module` | 2.0.0 | 开发/构建 | MIT | npm |
| `is-callable` | 1.2.7 | 开发/构建 | MIT | npm |
| `is-core-module` | 2.17.0 | 开发/构建 | MIT | npm |
| `is-data-view` | 1.0.2 | 开发/构建 | MIT | npm |
| `is-date-object` | 1.1.0 | 开发/构建 | MIT | npm |
| `is-document.all` | 1.0.0 | 开发/构建 | MIT | npm |
| `is-extglob` | 2.1.1 | 开发/构建 | MIT | npm |
| `is-finalizationregistry` | 1.1.1 | 开发/构建 | MIT | npm |
| `is-generator-function` | 1.1.2 | 开发/构建 | MIT | npm |
| `is-glob` | 4.0.3 | 开发/构建 | MIT | npm |
| `is-map` | 2.0.3 | 开发/构建 | MIT | npm |
| `is-negative-zero` | 2.0.3 | 开发/构建 | MIT | npm |
| `is-number` | 7.0.0 | 开发/构建 | MIT | npm |
| `is-number-object` | 1.1.1 | 开发/构建 | MIT | npm |
| `is-potential-custom-element-name` | 1.0.1 | 开发/构建 | MIT | npm |
| `is-regex` | 1.2.1 | 开发/构建 | MIT | npm |
| `is-set` | 2.0.3 | 开发/构建 | MIT | npm |
| `is-shared-array-buffer` | 1.0.4 | 开发/构建 | MIT | npm |
| `is-string` | 1.1.1 | 开发/构建 | MIT | npm |
| `is-symbol` | 1.1.1 | 开发/构建 | MIT | npm |
| `is-typed-array` | 1.1.15 | 开发/构建 | MIT | npm |
| `is-weakmap` | 2.0.2 | 开发/构建 | MIT | npm |
| `is-weakref` | 1.1.1 | 开发/构建 | MIT | npm |
| `is-weakset` | 2.0.4 | 开发/构建 | MIT | npm |
| `isarray` | 2.0.5 | 开发/构建 | MIT | npm |
| `isexe` | 2.0.0 | 开发/构建 | ISC | npm |
| `iterator.prototype` | 1.1.5 | 开发/构建 | MIT | npm |
| `js-tokens` | 4.0.0 | 开发/构建 | MIT | npm |
| `js-yaml` | 4.3.2 | 开发/构建 | MIT | npm |
| `jsdom` | 27.4.0 | 开发/构建 | MIT | npm |
| `jsesc` | 3.1.0 | 开发/构建 | MIT | npm |
| `json-buffer` | 3.0.1 | 开发/构建 | MIT | npm |
| `json-schema-traverse` | 0.4.1 | 开发/构建 | MIT | npm |
| `json-stable-stringify-without-jsonify` | 1.0.1 | 开发/构建 | MIT | npm |
| `json5` | 1.0.2 | 开发/构建 | MIT | npm |
| `json5` | 2.2.3 | 开发/构建 | MIT | npm |
| `jsx-ast-utils` | 3.3.5 | 开发/构建 | MIT | npm |
| `keyv` | 4.5.4 | 开发/构建 | MIT | npm |
| `language-subtag-registry` | 0.3.23 | 开发/构建 | CC0-1.0 | npm |
| `language-tags` | 1.0.9 | 开发/构建 | MIT | npm |
| `levn` | 0.4.1 | 开发/构建 | MIT | npm |
| `lightningcss` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-android-arm64` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-darwin-arm64` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-darwin-x64` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-freebsd-x64` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-linux-arm-gnueabihf` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-linux-arm64-gnu` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-linux-arm64-musl` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-linux-x64-gnu` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-linux-x64-musl` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-win32-arm64-msvc` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `lightningcss-win32-x64-msvc` | 1.33.0 | 开发/构建 | MPL-2.0 | npm |
| `locate-path` | 6.0.0 | 开发/构建 | MIT | npm |
| `lodash.merge` | 4.6.2 | 开发/构建 | MIT | npm |
| `loose-envify` | 1.4.0 | 开发/构建 | MIT | npm |
| `lru-cache` | 11.5.3 | 开发/构建 | BlueOak-1.0.0 | npm |
| `lru-cache` | 11.5.3 | 开发/构建 | BlueOak-1.0.0 | npm |
| `lru-cache` | 11.5.3 | 开发/构建 | BlueOak-1.0.0 | npm |
| `lru-cache` | 5.1.1 | 开发/构建 | ISC | npm |
| `lucide-react` | 1.67.0 | 运行时 | ISC | npm |
| `lz-string` | 1.5.0 | 开发/构建 | MIT | npm |
| `magic-string` | 0.30.21 | 开发/构建 | MIT | npm |
| `math-intrinsics` | 1.1.0 | 开发/构建 | MIT | npm |
| `mdn-data` | 2.27.1 | 开发/构建 | CC0-1.0 | npm |
| `merge2` | 1.4.1 | 开发/构建 | MIT | npm |
| `meshoptimizer` | 1.1.1 | 开发/构建 | MIT | npm |
| `micromatch` | 4.0.8 | 开发/构建 | MIT | npm |
| `min-indent` | 1.0.1 | 开发/构建 | MIT | npm |
| `minimatch` | 10.2.6 | 开发/构建 | BlueOak-1.0.0 | npm |
| `minimatch` | 3.1.5 | 开发/构建 | ISC | npm |
| `minimist` | 1.2.8 | 开发/构建 | MIT | npm |
| `ms` | 2.1.3 | 开发/构建 | MIT | npm |
| `nanoid` | 3.3.20 | 运行时 | MIT | npm |
| `napi-postinstall` | 0.3.7 | 开发/构建 | MIT | npm |
| `natural-compare` | 1.4.0 | 开发/构建 | MIT | npm |
| `next` | 16.4.3 | 运行时 | MIT | npm |
| `node-exports-info` | 1.6.2 | 开发/构建 | MIT | npm |
| `node-releases` | 2.0.63 | 开发/构建 | MIT | npm |
| `object-assign` | 4.1.1 | 开发/构建 | MIT | npm |
| `object-inspect` | 1.13.4 | 开发/构建 | MIT | npm |
| `object-keys` | 1.1.1 | 开发/构建 | MIT | npm |
| `object.assign` | 4.1.7 | 开发/构建 | MIT | npm |
| `object.entries` | 1.1.9 | 开发/构建 | MIT | npm |
| `object.fromentries` | 2.0.8 | 开发/构建 | MIT | npm |
| `object.groupby` | 1.0.3 | 开发/构建 | MIT | npm |
| `object.values` | 1.2.1 | 开发/构建 | MIT | npm |
| `obug` | 2.2.1 | 开发/构建 | MIT | npm |
| `optionator` | 0.9.4 | 开发/构建 | MIT | npm |
| `own-keys` | 1.0.2 | 开发/构建 | MIT | npm |
| `p-limit` | 3.1.0 | 开发/构建 | MIT | npm |
| `p-locate` | 5.0.0 | 开发/构建 | MIT | npm |
| `parent-module` | 1.0.1 | 开发/构建 | MIT | npm |
| `parse5` | 8.0.1 | 开发/构建 | MIT | npm |
| `path-exists` | 4.0.0 | 开发/构建 | MIT | npm |
| `path-key` | 3.1.1 | 开发/构建 | MIT | npm |
| `path-parse` | 1.0.7 | 开发/构建 | MIT | npm |
| `pathe` | 2.0.3 | 开发/构建 | MIT | npm |
| `picocolors` | 1.1.1 | 运行时 | ISC | npm |
| `picomatch` | 2.3.2 | 开发/构建 | MIT | npm |
| `picomatch` | 4.0.7 | 开发/构建 | MIT | npm |
| `picomatch` | 4.0.7 | 开发/构建 | MIT | npm |
| `picomatch` | 4.0.7 | 开发/构建 | MIT | npm |
| `playwright` | 1.64.1 | 运行时 | Apache-2.0 | npm |
| `playwright-core` | 1.64.1 | 运行时 | Apache-2.0 | npm |
| `possible-typed-array-names` | 1.1.0 | 开发/构建 | MIT | npm |
| `postcss` | 8.5.23 | 运行时 | MIT | npm |
| `postcss` | 8.5.32 | 开发/构建 | MIT | npm |
| `prelude-ls` | 1.2.1 | 开发/构建 | MIT | npm |
| `pretty-format` | 27.5.1 | 开发/构建 | MIT | npm |
| `prop-types` | 15.8.1 | 开发/构建 | MIT | npm |
| `punycode` | 2.3.1 | 开发/构建 | MIT | npm |
| `queue-microtask` | 1.2.3 | 开发/构建 | MIT | npm |
| `react` | 19.2.4 | 运行时 | MIT | npm |
| `react-dom` | 19.2.4 | 运行时 | MIT | npm |
| `react-is` | 16.13.1 | 开发/构建 | MIT | npm |
| `react-is` | 17.0.2 | 开发/构建 | MIT | npm |
| `redent` | 3.0.0 | 开发/构建 | MIT | npm |
| `reflect.getprototypeof` | 1.0.10 | 开发/构建 | MIT | npm |
| `regexp.prototype.flags` | 1.5.4 | 开发/构建 | MIT | npm |
| `require-from-string` | 2.0.2 | 开发/构建 | MIT | npm |
| `resolve` | 2.0.0-next.7 | 开发/构建 | MIT | npm |
| `resolve-from` | 4.0.0 | 开发/构建 | MIT | npm |
| `resolve-pkg-maps` | 1.0.0 | 开发/构建 | MIT | npm |
| `reusify` | 1.1.0 | 开发/构建 | MIT | npm |
| `rolldown` | 1.2.16 | 开发/构建 | MIT | npm |
| `run-parallel` | 1.2.0 | 开发/构建 | MIT | npm |
| `safe-array-concat` | 1.1.4 | 开发/构建 | MIT | npm |
| `safe-push-apply` | 1.0.0 | 开发/构建 | MIT | npm |
| `safe-regex-test` | 1.1.0 | 开发/构建 | MIT | npm |
| `saxes` | 6.0.0 | 开发/构建 | ISC | npm |
| `scheduler` | 0.27.0 | 运行时 | MIT | npm |
| `semver` | 6.3.1 | 开发/构建 | ISC | npm |
| `semver` | 7.8.5 | 开发/构建 | ISC | npm |
| `semver` | 7.8.5 | 开发/构建 | ISC | npm |
| `semver` | 7.8.5 | 运行时 | ISC | npm |
| `set-function-length` | 1.2.2 | 开发/构建 | MIT | npm |
| `set-function-name` | 2.0.2 | 开发/构建 | MIT | npm |
| `set-proto` | 1.0.0 | 开发/构建 | MIT | npm |
| `sharp` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `shebang-command` | 2.0.0 | 开发/构建 | MIT | npm |
| `shebang-regex` | 3.0.0 | 开发/构建 | MIT | npm |
| `side-channel` | 1.1.1 | 开发/构建 | MIT | npm |
| `side-channel-list` | 1.0.1 | 开发/构建 | MIT | npm |
| `side-channel-map` | 1.0.1 | 开发/构建 | MIT | npm |
| `side-channel-weakmap` | 1.0.2 | 开发/构建 | MIT | npm |
| `siginfo` | 2.0.0 | 开发/构建 | ISC | npm |
| `source-map-js` | 1.2.2 | 运行时 | BSD-3-Clause | npm |
| `stable-hash` | 0.0.5 | 开发/构建 | MIT | npm |
| `stackback` | 0.0.2 | 开发/构建 | MIT | npm |
| `std-env` | 4.3.0 | 开发/构建 | MIT | npm |
| `stop-iteration-iterator` | 1.1.0 | 开发/构建 | MIT | npm |
| `string.prototype.includes` | 2.0.1 | 开发/构建 | MIT | npm |
| `string.prototype.matchall` | 4.1.0 | 开发/构建 | MIT | npm |
| `string.prototype.repeat` | 1.0.0 | 开发/构建 | MIT | npm |
| `string.prototype.trim` | 1.2.11 | 开发/构建 | MIT | npm |
| `string.prototype.trimend` | 1.0.10 | 开发/构建 | MIT | npm |
| `string.prototype.trimstart` | 1.0.8 | 开发/构建 | MIT | npm |
| `strip-bom` | 3.0.0 | 开发/构建 | MIT | npm |
| `strip-indent` | 3.0.0 | 开发/构建 | MIT | npm |
| `strip-json-comments` | 3.1.1 | 开发/构建 | MIT | npm |
| `styled-jsx` | 5.1.6 | 运行时 | MIT | npm |
| `supports-color` | 7.2.0 | 开发/构建 | MIT | npm |
| `supports-preserve-symlinks-flag` | 1.0.0 | 开发/构建 | MIT | npm |
| `symbol-tree` | 3.2.4 | 开发/构建 | MIT | npm |
| `three` | 0.187.0 | 运行时 | MIT | npm |
| `tinybench` | 2.9.0 | 开发/构建 | MIT | npm |
| `tinyexec` | 1.3.1 | 开发/构建 | MIT | npm |
| `tinyglobby` | 0.2.17 | 开发/构建 | MIT | npm |
| `tinyrainbow` | 3.2.0 | 开发/构建 | MIT | npm |
| `tldts` | 7.4.19 | 开发/构建 | MIT | npm |
| `tldts-core` | 7.4.20 | 开发/构建 | MIT | npm |
| `to-regex-range` | 5.0.1 | 开发/构建 | MIT | npm |
| `tough-cookie` | 6.0.2 | 开发/构建 | BSD-3-Clause | npm |
| `tr46` | 6.0.0 | 开发/构建 | MIT | npm |
| `ts-api-utils` | 2.5.0 | 开发/构建 | MIT | npm |
| `tsconfig-paths` | 3.15.0 | 开发/构建 | MIT | npm |
| `tslib` | 2.9.1 | 运行时 | 0BSD | npm |
| `type-check` | 0.4.0 | 开发/构建 | MIT | npm |
| `typed-array-buffer` | 1.0.3 | 开发/构建 | MIT | npm |
| `typed-array-byte-length` | 1.0.3 | 开发/构建 | MIT | npm |
| `typed-array-byte-offset` | 1.0.5 | 开发/构建 | MIT | npm |
| `typed-array-length` | 1.0.8 | 开发/构建 | MIT | npm |
| `typescript` | 5.9.3 | 开发/构建 | Apache-2.0 | npm |
| `typescript-eslint` | 8.72.1 | 开发/构建 | MIT | npm |
| `unbox-primitive` | 1.1.0 | 开发/构建 | MIT | npm |
| `undici-types` | 7.24.6 | 开发/构建 | MIT | npm |
| `unrs-resolver` | 1.13.0 | 开发/构建 | MIT | npm |
| `update-browserslist-db` | 1.3.4 | 开发/构建 | MIT | npm |
| `uri-js` | 4.4.1 | 开发/构建 | BSD-2-Clause | npm |
| `vite` | 8.3.5 | 开发/构建 | MIT | npm |
| `vitest` | 4.1.12 | 开发/构建 | MIT | npm |
| `w3c-xmlserializer` | 5.0.0 | 开发/构建 | MIT | npm |
| `webidl-conversions` | 8.0.1 | 开发/构建 | BSD-2-Clause | npm |
| `whatwg-mimetype` | 4.0.0 | 开发/构建 | MIT | npm |
| `whatwg-mimetype` | 5.0.0 | 开发/构建 | MIT | npm |
| `whatwg-url` | 15.1.0 | 开发/构建 | MIT | npm |
| `which` | 2.0.2 | 开发/构建 | ISC | npm |
| `which-boxed-primitive` | 1.1.1 | 开发/构建 | MIT | npm |
| `which-builtin-type` | 1.2.1 | 开发/构建 | MIT | npm |
| `which-collection` | 1.0.2 | 开发/构建 | MIT | npm |
| `which-typed-array` | 1.1.24 | 开发/构建 | MIT | npm |
| `why-is-node-running` | 2.3.0 | 开发/构建 | MIT | npm |
| `word-wrap` | 1.2.5 | 开发/构建 | MIT | npm |
| `ws` | 8.22.1 | 开发/构建 | MIT | npm |
| `xml-name-validator` | 5.0.0 | 开发/构建 | Apache-2.0 | npm |
| `xmlchars` | 2.2.0 | 开发/构建 | MIT | npm |
| `yallist` | 3.1.1 | 开发/构建 | ISC | npm |
| `yocto-queue` | 0.1.0 | 开发/构建 | MIT | npm |
| `zod` | 4.6.7 | 开发/构建 | MIT | npm |
| `zod-validation-error` | 4.0.2 | 开发/构建 | MIT | npm |

<!-- WEB_V2_LICENSES_START -->

### Node / Web v2（221 条，运行时）

> `apps/web-v2` 是 Compose 默认工作台，与旧版 `apps/web` 可并存回退。以下依赖来自 `npm ls --omit=dev --all`，**未与旧版 Node 清单去重**；完整仓库字段见 `apps/web-v2/THIRD-PARTY-LICENSES.md`。发行 SBOM 应统一重算总量。

| 包 | 版本 | 作用域 | 许可证 | 来源 |
|---|---|---|---|---|
| `@floating-ui/core` | 1.8.0 | 运行时 | MIT | npm |
| `@floating-ui/dom` | 1.8.0 | 运行时 | MIT | npm |
| `@floating-ui/react-dom` | 2.1.9 | 运行时 | MIT | npm |
| `@floating-ui/utils` | 0.2.12 | 运行时 | MIT | npm |
| `@fontsource/dm-sans` | 5.3.0 | 运行时 | OFL-1.1 | npm |
| `@fontsource/dm-serif-display` | 5.3.0 | 运行时 | OFL-1.1 | npm |
| `@img/colour` | 1.1.0 | 运行时 | MIT | npm |
| `@img/sharp-win32-x64` | 0.35.5 | 运行时 | Apache-2.0 AND LGPL-3.0-or-later | npm |
| `@next/env` | 16.4.3 | 运行时 | MIT | npm |
| `@next/swc-win32-x64-msvc` | 16.4.3 | 运行时 | MIT | npm |
| `@playwright/test` | 1.64.1 | 运行时 | Apache-2.0 | npm |
| `@radix-ui/number` | 1.1.3 | 运行时 | MIT | npm |
| `@radix-ui/primitive` | 1.2.0 | 运行时 | MIT | npm |
| `@radix-ui/react-accessible-icon` | 1.2.0 | 运行时 | MIT | npm |
| `@radix-ui/react-accordion` | 1.3.1 | 运行时 | MIT | npm |
| `@radix-ui/react-alert-dialog` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-arrow` | 1.1.17 | 运行时 | MIT | npm |
| `@radix-ui/react-aspect-ratio` | 1.2.0 | 运行时 | MIT | npm |
| `@radix-ui/react-avatar` | 1.3.1 | 运行时 | MIT | npm |
| `@radix-ui/react-checkbox` | 1.4.1 | 运行时 | MIT | npm |
| `@radix-ui/react-collapsible` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-collection` | 1.2.0 | 运行时 | MIT | npm |
| `@radix-ui/react-compose-refs` | 1.1.5 | 运行时 | MIT | npm |
| `@radix-ui/react-context` | 1.3.0 | 运行时 | MIT | npm |
| `@radix-ui/react-context-menu` | 2.4.1 | 运行时 | MIT | npm |
| `@radix-ui/react-dialog` | 1.3.1 | 运行时 | MIT | npm |
| `@radix-ui/react-direction` | 1.2.0 | 运行时 | MIT | npm |
| `@radix-ui/react-dismissable-layer` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-dropdown-menu` | 2.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-focus-guards` | 1.2.0 | 运行时 | MIT | npm |
| `@radix-ui/react-focus-scope` | 1.3.1 | 运行时 | MIT | npm |
| `@radix-ui/react-form` | 0.3.0 | 运行时 | MIT | npm |
| `@radix-ui/react-hover-card` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-id` | 1.1.4 | 运行时 | MIT | npm |
| `@radix-ui/react-label` | 2.1.17 | 运行时 | MIT | npm |
| `@radix-ui/react-menu` | 2.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-menubar` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-navigation-menu` | 1.4.1 | 运行时 | MIT | npm |
| `@radix-ui/react-one-time-password-field` | 0.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-password-toggle-field` | 0.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-popover` | 1.3.1 | 运行时 | MIT | npm |
| `@radix-ui/react-popper` | 1.4.0 | 运行时 | MIT | npm |
| `@radix-ui/react-portal` | 1.2.0 | 运行时 | MIT | npm |
| `@radix-ui/react-presence` | 1.1.11 | 运行时 | MIT | npm |
| `@radix-ui/react-primitive` | 2.2.0 | 运行时 | MIT | npm |
| `@radix-ui/react-progress` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-radio-group` | 1.5.1 | 运行时 | MIT | npm |
| `@radix-ui/react-roving-focus` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-scroll-area` | 1.4.0 | 运行时 | MIT | npm |
| `@radix-ui/react-select` | 2.4.1 | 运行时 | MIT | npm |
| `@radix-ui/react-separator` | 1.2.0 | 运行时 | MIT | npm |
| `@radix-ui/react-slider` | 1.6.1 | 运行时 | MIT | npm |
| `@radix-ui/react-slot` | 1.5.0 | 运行时 | MIT | npm |
| `@radix-ui/react-switch` | 1.4.1 | 运行时 | MIT | npm |
| `@radix-ui/react-tabs` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-toast` | 1.3.1 | 运行时 | MIT | npm |
| `@radix-ui/react-toggle` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-toggle-group` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-toolbar` | 1.2.1 | 运行时 | MIT | npm |
| `@radix-ui/react-tooltip` | 1.4.1 | 运行时 | MIT | npm |
| `@radix-ui/react-use-callback-ref` | 1.1.5 | 运行时 | MIT | npm |
| `@radix-ui/react-use-controllable-state` | 1.3.0 | 运行时 | MIT | npm |
| `@radix-ui/react-use-effect-event` | 0.0.5 | 运行时 | MIT | npm |
| `@radix-ui/react-use-escape-keydown` | 1.1.6 | 运行时 | MIT | npm |
| `@radix-ui/react-use-is-hydrated` | 0.1.3 | 运行时 | MIT | npm |
| `@radix-ui/react-use-layout-effect` | 1.1.4 | 运行时 | MIT | npm |
| `@radix-ui/react-use-previous` | 1.1.4 | 运行时 | MIT | npm |
| `@radix-ui/react-use-rect` | 1.1.4 | 运行时 | MIT | npm |
| `@radix-ui/react-use-size` | 1.1.5 | 运行时 | MIT | npm |
| `@radix-ui/react-visually-hidden` | 1.2.13 | 运行时 | MIT | npm |
| `@radix-ui/rect` | 1.1.3 | 运行时 | MIT | npm |
| `@reduxjs/toolkit` | 2.14.0 | 运行时 | MIT | npm |
| `@standard-schema/spec` | 1.1.0 | 运行时 | MIT | npm |
| `@standard-schema/utils` | 0.3.0 | 运行时 | MIT | npm |
| `@swc/helpers` | 0.5.23 | 运行时 | Apache-2.0 | npm |
| `@types/debug` | 4.1.13 | 运行时 | MIT | npm |
| `@types/estree` | 1.0.10 | 运行时 | MIT | npm |
| `@types/estree-jsx` | 1.0.5 | 运行时 | MIT | npm |
| `@types/hast` | 3.0.5 | 运行时 | MIT | npm |
| `@types/mdast` | 4.0.4 | 运行时 | MIT | npm |
| `@types/ms` | 2.1.0 | 运行时 | MIT | npm |
| `@types/react` | 19.3.0 | 运行时 | MIT | npm |
| `@types/react-dom` | 19.3.0 | 运行时 | MIT | npm |
| `@types/unist` | 3.0.3 | 运行时 | MIT | npm |
| `@types/unist` | 2.0.11 | 运行时 | MIT | npm |
| `@types/use-sync-external-store` | 0.0.6 | 运行时 | MIT | npm |
| `@ungap/structured-clone` | 1.4.0 | 运行时 | ISC | npm |
| `aria-hidden` | 1.2.6 | 运行时 | MIT | npm |
| `bail` | 2.0.2 | 运行时 | MIT | npm |
| `baseline-browser-mapping` | 2.11.35 | 运行时 | Apache-2.0 | npm |
| `caniuse-lite` | 1.0.30001823 | 运行时 | CC-BY-4.0 | npm |
| `ccount` | 2.0.1 | 运行时 | MIT | npm |
| `character-entities` | 2.0.2 | 运行时 | MIT | npm |
| `character-entities-html4` | 2.1.0 | 运行时 | MIT | npm |
| `character-entities-legacy` | 3.0.0 | 运行时 | MIT | npm |
| `character-reference-invalid` | 2.0.1 | 运行时 | MIT | npm |
| `client-only` | 0.0.1 | 运行时 | MIT | npm |
| `clsx` | 2.1.1 | 运行时 | MIT | npm |
| `comma-separated-tokens` | 2.0.3 | 运行时 | MIT | npm |
| `csstype` | 3.2.3 | 运行时 | MIT | npm |
| `debug` | 4.4.3 | 运行时 | MIT | npm |
| `decode-named-character-reference` | 1.3.0 | 运行时 | MIT | npm |
| `dequal` | 2.0.3 | 运行时 | MIT | npm |
| `detect-libc` | 2.1.2 | 运行时 | Apache-2.0 | npm |
| `detect-node-es` | 1.1.0 | 运行时 | MIT | npm |
| `devlop` | 1.1.0 | 运行时 | MIT | npm |
| `escape-string-regexp` | 5.0.0 | 运行时 | MIT | npm |
| `estree-util-is-identifier-name` | 3.0.0 | 运行时 | MIT | npm |
| `extend` | 3.0.2 | 运行时 | MIT | npm |
| `framer-motion` | 12.43.0 | 运行时 | MIT | npm |
| `get-nonce` | 1.0.1 | 运行时 | MIT | npm |
| `hast-util-to-jsx-runtime` | 2.3.7 | 运行时 | MIT | npm |
| `hast-util-whitespace` | 3.0.0 | 运行时 | MIT | npm |
| `html-url-attributes` | 3.0.1 | 运行时 | MIT | npm |
| `immer` | 11.2.9 | 运行时 | MIT | npm |
| `inline-style-parser` | 0.2.9 | 运行时 | MIT | npm |
| `is-alphabetical` | 2.0.1 | 运行时 | MIT | npm |
| `is-alphanumerical` | 2.0.1 | 运行时 | MIT | npm |
| `is-decimal` | 2.0.1 | 运行时 | MIT | npm |
| `is-hexadecimal` | 2.0.1 | 运行时 | MIT | npm |
| `is-plain-obj` | 4.1.0 | 运行时 | MIT | npm |
| `longest-streak` | 3.1.0 | 运行时 | MIT | npm |
| `lucide-react` | 1.70.0 | 运行时 | ISC | npm |
| `markdown-table` | 3.1.0 | 运行时 | MIT | npm |
| `mdast-util-find-and-replace` | 3.0.4 | 运行时 | MIT | npm |
| `mdast-util-from-markdown` | 2.1.0 | 运行时 | MIT | npm |
| `mdast-util-gfm` | 3.1.0 | 运行时 | MIT | npm |
| `mdast-util-gfm-autolink-literal` | 2.1.0 | 运行时 | MIT | npm |
| `mdast-util-gfm-footnote` | 2.1.0 | 运行时 | MIT | npm |
| `mdast-util-gfm-strikethrough` | 2.0.1 | 运行时 | MIT | npm |
| `mdast-util-gfm-table` | 2.0.1 | 运行时 | MIT | npm |
| `mdast-util-gfm-task-list-item` | 2.0.1 | 运行时 | MIT | npm |
| `mdast-util-mdx-expression` | 2.0.1 | 运行时 | MIT | npm |
| `mdast-util-mdx-jsx` | 3.2.1 | 运行时 | MIT | npm |
| `mdast-util-mdxjs-esm` | 2.0.1 | 运行时 | MIT | npm |
| `mdast-util-phrasing` | 4.1.0 | 运行时 | MIT | npm |
| `mdast-util-to-hast` | 13.2.1 | 运行时 | MIT | npm |
| `mdast-util-to-markdown` | 2.2.3 | 运行时 | MIT | npm |
| `mdast-util-to-string` | 4.0.0 | 运行时 | MIT | npm |
| `micromark` | 4.0.3 | 运行时 | MIT | npm |
| `micromark-core-commonmark` | 2.0.4 | 运行时 | MIT | npm |
| `micromark-extension-gfm` | 3.0.0 | 运行时 | MIT | npm |
| `micromark-extension-gfm-autolink-literal` | 2.1.0 | 运行时 | MIT | npm |
| `micromark-extension-gfm-footnote` | 2.1.0 | 运行时 | MIT | npm |
| `micromark-extension-gfm-strikethrough` | 2.1.0 | 运行时 | MIT | npm |
| `micromark-extension-gfm-table` | 2.1.2 | 运行时 | MIT | npm |
| `micromark-extension-gfm-tagfilter` | 2.0.0 | 运行时 | MIT | npm |
| `micromark-extension-gfm-task-list-item` | 2.1.0 | 运行时 | MIT | npm |
| `micromark-factory-destination` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-factory-label` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-factory-space` | 2.1.0 | 运行时 | MIT | npm |
| `micromark-factory-title` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-factory-whitespace` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-character` | 2.1.1 | 运行时 | MIT | npm |
| `micromark-util-chunked` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-classify-character` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-combine-extensions` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-decode-numeric-character-reference` | 2.0.2 | 运行时 | MIT | npm |
| `micromark-util-decode-string` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-edit-map` | 1.0.0 | 运行时 | MIT | npm |
| `micromark-util-encode` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-html-tag-name` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-normalize-identifier` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-resolve-all` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-sanitize-uri` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-subtokenize` | 2.1.0 | 运行时 | MIT | npm |
| `micromark-util-symbol` | 2.0.1 | 运行时 | MIT | npm |
| `micromark-util-types` | 2.0.3 | 运行时 | MIT | npm |
| `motion` | 12.43.0 | 运行时 | MIT | npm |
| `motion-dom` | 12.43.0 | 运行时 | MIT | npm |
| `motion-utils` | 12.39.0 | 运行时 | MIT | npm |
| `ms` | 2.1.3 | 运行时 | MIT | npm |
| `nanoid` | 3.3.20 | 运行时 | MIT | npm |
| `next` | 16.4.3 | 运行时 | MIT | npm |
| `parse-entities` | 4.0.2 | 运行时 | MIT | npm |
| `picocolors` | 1.1.1 | 运行时 | ISC | npm |
| `playwright` | 1.64.1 | 运行时 | Apache-2.0 | npm |
| `playwright-core` | 1.64.1 | 运行时 | Apache-2.0 | npm |
| `postcss` | 8.5.23 | 运行时 | MIT | npm |
| `property-information` | 7.2.0 | 运行时 | MIT | npm |
| `radix-ui` | 1.8.1 | 运行时 | MIT | npm |
| `react` | 19.2.4 | 运行时 | MIT | npm |
| `react-dom` | 19.2.4 | 运行时 | MIT | npm |
| `react-markdown` | 10.1.0 | 运行时 | MIT | npm |
| `react-redux` | 9.3.1 | 运行时 | MIT | npm |
| `react-remove-scroll` | 2.7.2 | 运行时 | MIT | npm |
| `react-remove-scroll-bar` | 2.3.8 | 运行时 | MIT | npm |
| `react-style-singleton` | 2.2.3 | 运行时 | MIT | npm |
| `redux` | 5.0.1 | 运行时 | MIT | npm |
| `redux-thunk` | 3.1.0 | 运行时 | MIT | npm |
| `remark-gfm` | 4.0.1 | 运行时 | MIT | npm |
| `remark-parse` | 11.0.0 | 运行时 | MIT | npm |
| `remark-rehype` | 11.1.2 | 运行时 | MIT | npm |
| `remark-stringify` | 11.0.0 | 运行时 | MIT | npm |
| `reselect` | 5.3.0 | 运行时 | MIT | npm |
| `scheduler` | 0.27.0 | 运行时 | MIT | npm |
| `semver` | 7.8.6 | 运行时 | ISC | npm |
| `sharp` | 0.35.5 | 运行时 | Apache-2.0 | npm |
| `sonner` | 2.0.8 | 运行时 | MIT | npm |
| `source-map-js` | 1.2.2 | 运行时 | BSD-3-Clause | npm |
| `space-separated-tokens` | 2.0.2 | 运行时 | MIT | npm |
| `stringify-entities` | 4.0.4 | 运行时 | MIT | npm |
| `style-to-object` | 2.0.2 | 运行时 | MIT | npm |
| `styled-jsx` | 5.1.6 | 运行时 | MIT | npm |
| `tailwind-merge` | 3.7.0 | 运行时 | MIT | npm |
| `three` | 0.187.0 | 运行时 | MIT | npm |
| `trim-lines` | 3.0.1 | 运行时 | MIT | npm |
| `trough` | 2.2.0 | 运行时 | MIT | npm |
| `tslib` | 2.9.1 | 运行时 | 0BSD | npm |
| `unified` | 11.0.5 | 运行时 | MIT | npm |
| `unist-util-is` | 6.0.1 | 运行时 | MIT | npm |
| `unist-util-position` | 5.0.0 | 运行时 | MIT | npm |
| `unist-util-stringify-position` | 4.0.0 | 运行时 | MIT | npm |
| `unist-util-visit` | 5.2.0 | 运行时 | MIT | npm |
| `unist-util-visit-parents` | 6.1.0 | 运行时 | MIT | npm |
| `use-callback-ref` | 1.3.3 | 运行时 | MIT | npm |
| `use-sidecar` | 1.1.3 | 运行时 | MIT | npm |
| `use-sync-external-store` | 1.7.0 | 运行时 | MIT | npm |
| `vfile` | 6.0.3 | 运行时 | MIT | npm |
| `vfile-message` | 4.0.4 | 运行时 | MIT | npm |
| `zwitch` | 2.0.4 | 运行时 | MIT | npm |

<!-- WEB_V2_LICENSES_END -->

## 5. 未覆盖范围与待核实

- **OS / 基础镜像层**：`python:3.12-slim`、`eclipse-temurin:21-jre-jammy`、Node 基础镜像内的发行版软件包不在本清单范围，其许可证与声明尚未采集（待核实）。
- **Apache 组件的 NOTICE 文本**：Apache-2.0 依赖若自带 `NOTICE`，分发时应随附其内容；当前仅记录 SPDX 标识，尚未逐份汇总上游 NOTICE（待核实）。
- **平台专属变体**：Node 的 `@img/sharp-*` 全部变体按 lockfile 登记，实际安装/镜像仅包含目标平台一个；Linux 镜像内最终落入的变体需在构建产物上复核（待核实）。
- **Python 平台 wheel**：39 条均来自本机已安装发行包；其他平台的 wheel 未安装、未单独核对（待核实）。
- **非 SPDX 写法**：Python 的 `colorama`、`reportlab` 元数据为 `OSI Approved / BSD License`，未标注 BSD 版本号，按上游原样保留（待核实具体版本）。
- **许可证全文**：本清单只记录标识与来源，不粘贴全文；发行物应随附第 3.2 节涉及的许可证全文与署名材料。
- 本清单是依赖与许可证元数据证据，不构成法律意见，也不替代法务与负责人的发行签收。
