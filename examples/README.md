# Examples

面向开发、测试和演示的非生产示例。

`job-scripts/` 用于保存脱敏的 Slurm 作业脚本示例，不存放用户真实作业、账号信息或敏感路径。

`test-projects/` 保存单账号真实验收使用的低资源 Python 项目模板。部署时将其复制到
107 用户目录的 `~/dashboard-test-projects/`；Dashboard 只读取登记的 manifest，并在每次
提交时把入口文件复制到独立 submission 快照。测试源码始终通过 `sbatch` 在计算节点运行。
