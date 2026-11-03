# Git 状态与恢复说明

## 当前状态

- 当前分支：`codex/phase4a-leakage`
- HEAD：`791fffc6fbc295107ec2093f3813d911bb01f7ca`
- 最近基线：`791fffc feat: add SST V1.1 transformer extensions`
- 上一基线：`b965b04 chore: baseline SST demo v1.0.0`
- `codex/phase4b-litz` 创建曾因 Git ref lock 权限不足失败；本次没有伪称分支已创建。
- 当前没有发现 `.git/index.lock`；没有删除或覆盖任何 lock 文件。

## 工作区

原有 Phase 2–4A 内容以及本次 Phase 4B/4B+ 内容主要以未跟踪文件存在，`git status --short --branch` 已在开发前保存并在开发后复核。没有执行 reset、clean、checkout 覆盖或远程推送。

本次新增/修改的 Phase 4B+ 文件包括：

- `backend/app/providers/openmagnetics/provider.py`
- `examples/phase4b_plus_verification.py`
- `backend/tests/test_winding_loss_phase4b.py`（既有 Phase 4B 测试文件）
- `docs/ab_upgrade/phase4b/verification/` 下六份报告和 JSON 结果

## 本地备份

开发前已备份明确范围内的 102 个文件：

`.runtime/phase4b-plus-backup-20261103`

备份校验：102 个文件、964914 bytes，所有文件均可读取；已输出 SHA-256 样例哈希。`.runtime/` 被 `.gitignore` 忽略，不会进入待提交集合。

完成本次校核后又生成了包含当前最终工作区内容的备份：

`.runtime/phase4b-plus-final-backup-20261103`

该备份包含 131 个文件、1528001 bytes，未发现不可读取文件，并已验证其中包含 `phase4b_plus_results.json`。

在最后一次测试补充后又生成了最终同步备份：

`.runtime/phase4b-plus-final-backup-20261103-r2`

该备份包含 131 个文件、1530940 bytes，未发现不可读取文件，并已验证包含当前 Phase 4B 测试文件。

## 建议的安全基线流程

1. 用户确认后，先解决 `.git/refs/heads` 的写权限或由仓库管理员创建 `codex/phase4b-litz`。
2. 只将 Phase 2–4B 明确文件加入暂存区，先查看 staged diff 和文件清单。
3. 在新分支上运行本报告列出的回归命令。
4. 由用户确认后再提交；本次没有自动提交或推送。
