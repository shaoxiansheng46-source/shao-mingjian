# Phase 2：已知限制

1. 本阶段只是独立 Provider 和基准验证，OpenMagnetics 尚未进入现有候选生成、NSGA-II、Pareto 结果或报告流程。
2. PyOpenMagnetics 安装在独立 `.runtime/openmagnetics-venv`；生产 Demo 仍保持原依赖，默认不能直接调用外部 Provider。
3. MAS 适配器要求完整的端电压和电流波形。它不会根据直流母线电压、匝比或移相角自动生成工程波形；下一阶段需要接入已验证的 DAB 波形/电路求解输入。
4. 独立 `calculate_skin_effect_losses` / `calculate_proximity_effect_losses` 路径还要求 MKF 的 harmonics 和磁场中间数据。当前基准用紧凑波形验证了错误诊断，完整 `calculate_winding_losses` 已实际成功；下一阶段需要把 `process_inputs` 和完整波形链路适配进来。
5. 当前 PyOpenMagnetics 版本的 `calculate_gapping_from_number_turns_and_inductance` 已实际调用，但用本阶段精简 MAS 输入返回 `Bad optional access`；适配器保留 `GAP_SOLVER_FAILED`，不把它改写成零气隙。需要根据完整 MAS 设计需求补齐缺失字段后再作为工程气隙反求入口。
6. 当前 Provider 返回统一摘要，不向优化器暴露第三方原始 JSON；尚未建立材料、磁芯、导线数据库到现有四类 Demo 数据库的版本化映射表。
7. 本阶段没有实现组合磁芯、结构参数化绕组、P-S-P 专用几何和 SST 的漏感工程模型接入；这些仍属于 B 类后续工作。
8. 未使用 MVB 生成参数化三维文件，也未完成 COMSOL/实物温升和损耗校核。
9. PyOpenMagnetics、MKF、MAS 的版本和 commit 已写入结果追溯，但第三方数据库本身仍需在商业发布前进行许可证和数据来源审核。
10. 真实第三方计算成功只说明接口和运行链路可用，不等于当前 SST 设计结果已达到工程认证精度。
