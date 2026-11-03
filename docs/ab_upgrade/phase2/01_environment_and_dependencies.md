# Phase 2：环境与依赖验证

## 结论

OpenMagnetics 在当前 Windows 开发环境可以实际运行。PyOpenMagnetics 使用独立虚拟环境安装，没有修改根目录 `requirements.txt`，也没有接入现有 Demo 的生产计算链。

## 实际环境

| 项目 | 实际值 |
|---|---|
| 平台 | Windows，AMD64 |
| Python | 3.13.12 |
| 隔离环境 | `.runtime/openmagnetics-venv` |
| PyOpenMagnetics | 1.7.35，`cp313-win_amd64` wheel |
| MKF commit | `39b59172268f55fbcd72037b948622f21382b5c1` |
| MAS commit | `0a7ba58f542049fd073041b3b5e4bac431ed6292` |
| 安装结果 | 成功，无本地 C++ 编译失败 |

实际安装命令：

```powershell
python -m venv .runtime/openmagnetics-venv
.runtime/openmagnetics-venv/Scripts/python.exe -m pip install PyOpenMagnetics
```

实际初始化代码调用了 `PyOpenMagnetics.load_databases({})`。初始化后数据库数量为：

- 1073 个 core material；
- 2107 个 core shape；
- 4340 个 wire。

PyOpenMagnetics 的安装包中包含 `AGENTS.md`、`PyOpenMagnetics.pyi` 和 `llms.txt`，本阶段已阅读其调用约束：直接传 Python `dict`，不使用 `json.dumps()`；初始化数据库后再调用查询和计算函数；第三方异常必须保留为诊断。

## 许可证记录

本阶段确认的上游许可证：

- [MKF LICENSE](https://raw.githubusercontent.com/OpenMagnetics/MKF/main/LICENSE.md)：MIT；
- [PyOpenMagnetics LICENSE](https://raw.githubusercontent.com/OpenMagnetics/PyOpenMagnetics/main/LICENSE)：MIT；
- [MVB LICENSE](https://raw.githubusercontent.com/OpenMagnetics/MVB/main/LICENSE)：MIT；
- [MAS LICENSE](https://raw.githubusercontent.com/OpenMagnetics/MAS/main/LICENSE.md)：Apache-2.0。

数据库内容仍需在实际产品发布前逐条确认商业使用和数据来源条件。本阶段只把它们作为可追溯的外部数据库，不宣称工程认证。

## 不影响现有 Demo 的原因

Provider 使用延迟导入。当前生产 Python 环境未安装 PyOpenMagnetics 时，导入 `backend.app.providers.openmagnetics` 不会破坏现有应用；实际调用会返回 `OPENMAGNETICS_UNAVAILABLE`，不会返回 0，也不会切换到 synthetic 结果。
