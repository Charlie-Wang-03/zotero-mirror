# zotero-mirror

[English](README.md)

**以隐私保护为默认设计的 Zotero ↔ GitHub 文献镜像，用于 AI 辅助学术研究。**

> 这是公开的通用模板，而不是任何用户的真实文献库；项目并非 Zotero 官方服务，
> 也不是需要安装到 Zotero Desktop 的扩展。真实镜像只能部署在 **Private GitHub 仓库**。

Zotero 仍是文献数据的权威来源。GitHub Actions 通过单独的只读密钥同步文献元数据、
笔记、批注、附件元数据与可索引全文；AI 助手读取你授权的**私有实例仓库**，无需接触 Zotero API 密钥。

## 快速开始

1. 点击 [Use this template](https://github.com/Charlie-Wang-03/zotero-mirror/generate)，创建 **Private** 仓库（不建议使用公开 Fork 承载真实数据）。
2. 在 [Zotero API Keys](https://www.zotero.org/settings/keys) 创建**不带写权限**的专用密钥，并确认 Zotero User ID。
3. 在新仓库 **Settings → Secrets and variables → Actions** 中设置变量 `ZOTERO_USER_ID` 与 Secret `ZOTERO_API_KEY_READONLY`；不要把密钥提交到 Git 或发送给 AI。
4. 运行 **Actions → First Run**。成功后检查 `library/STATUS.md` 与数据一致性结果。
5. 仅在首次运行成功后，将仓库变量 `ZOTERO_MIRROR_ENABLED` 设为 `true`，开启手动及周期同步。
6. 给 AI 客户端授权访问**私有实例仓库**，让其先读取 `AGENTS.md`，再进行检索与文献问答。

普通部署无需在本地克隆项目，运行所依赖的 Python 代码使用标准库。更多细节见 [Quickstart](docs/QUICKSTART.md) 和 [配置说明](docs/CONFIGURATION.md)。

## 功能与验证边界

| 功能 | 当前状态 |
| --- | --- |
| 文献、笔记、批注及全文索引镜像 | 已实现；私有实例首次同步验证通过 |
| 文献版本与数量一致性校验 | 已实现；私有实例首次运行验证通过 |
| 带版本保护的限时写入 | 已实现；隔离环境 create/read/patch/delete 验证通过 |
| PDF 上传到 Zotero Storage | 已实现；离线回归检查，不代表所有账号的完整实测 |
| PDF 批注、批注关联富文本笔记 | 部分支持，受准确 PDF 坐标和 Zotero 语义限制 |
| Saved Search 元数据增删改查 | 已实现；Web API 不执行保存的搜索结果 |
| 原生重复条目合并 | 不支持 Web API 原生合并；需 Zotero Desktop |

此前 Canary 测试通过首次同步和两轮隔离读写测试，但**未**覆盖所有工作流与高级功能的真实端到端路径。详情见 [验证记录与限制](docs/VALIDATION.md)。

## 本地离线验证

使用 Python 3.13，无需额外安装第三方依赖：

```bash
python scripts/validate_project.py
```

该命令执行语法、公开源码隐私边界、部署规范与合成数据测试；**不会连接真实 Zotero，也不能代替实际读写验收**。

## 安全原则

- `read_only` 为默认模式，`allow_destructive=false`；写入需要独立密钥及有时限的显式授权。
- 真实文献镜像、笔记、全文和写入回执不得出现在公开仓库。
- 公开通用模板与私有用户实例分离；Zotero 仍是数据源。

其他资料：[架构](docs/ARCHITECTURE.md) · [安全政策](SECURITY.md) · [贡献说明](CONTRIBUTING.md) · [发布检查](docs/RELEASE_CHECKLIST.md)。

项目采用 [MIT License](LICENSE)。
