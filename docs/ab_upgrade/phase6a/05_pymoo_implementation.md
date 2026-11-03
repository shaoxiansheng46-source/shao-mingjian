# pymoo 混合变量实现

当前安装版本为 pymoo 0.6.2。该版本没有 `MixedVariableProblem`；实现采用：

```python
Problem(vars=space.variables(), elementwise=True, n_obj=2,
        n_ieq_constr=constraint_count)
NSGA2(
    sampling=MixedVariableSampling(),
    mating=MixedVariableMating(...),
    eliminate_duplicates=MixedVariableDuplicateElimination(),
    survival=RankAndCrowding(),
)
```

`Integer`、`Real`、`Choice` 分别由 pymoo 的混合采样/交叉/变异处理；没有将候选目录索引编码为一个大整数。随机种子、种群规模、代数、最大评估次数、超时和取消事件均在 `Phase6AConfig`/优化入口中可追溯。

非支配排序在优化结束后再次对台账中的 `research_feasible` 唯一记录执行；因此只有实际评估且满足研究约束的候选才可能进入 Pareto，异常/缺失值不会形成假前沿。
