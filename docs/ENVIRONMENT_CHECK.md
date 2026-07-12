# 算力平台环境快速检查

这组命令用于快速了解算力平台当前环境，全部为只读检查，不会安装依赖、提交作业或修改系统配置。

请在算力平台登录节点执行。输出中可能包含节点名、用户名和网络信息，分享前请确认没有密码、Token、私钥或其他敏感内容。

## 一键检查

```bash
printf '\\n== Host ==\\n'
hostname
uname -a
cat /etc/os-release 2>/dev/null | sed -n '1,8p'

printf '\\n== CPU and Memory ==\\n'
lscpu 2>/dev/null | grep -E 'Model name|CPU\\(s\\)|Thread|Core|Socket' | head -10
free -h

printf '\\n== Storage ==\\n'
df -hT "$HOME" /tmp 2>/dev/null

printf '\\n== Python ==\\n'
command -v python || true
python --version 2>/dev/null || true
command -v python3 || true
python3 --version 2>/dev/null || true
python3 -m pip --version 2>/dev/null || true

printf '\\n== Conda ==\\n'
command -v conda || true
conda --version 2>/dev/null || true
conda env list 2>/dev/null || true

printf '\\n== Common Python Packages ==\\n'
python3 - <<'PY'
from importlib.util import find_spec

packages = [
    "torch", "torchvision", "torchaudio", "transformers", "numpy",
    "pandas", "scipy", "sklearn", "fastapi", "uvicorn", "sqlalchemy",
]

for package in packages:
    print(f"{package}: {'installed' if find_spec(package) else 'missing'}")
PY

printf '\\n== GPU ==\\n'
command -v nvidia-smi && nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
command -v rocm-smi && rocm-smi --showproductname --showmeminfo vram 2>/dev/null || true

printf '\\n== Docker ==\\n'
command -v docker || true
docker --version 2>/dev/null || true
docker compose version 2>/dev/null || true
docker info --format 'server={{.ServerVersion}}; rootless={{.SecurityOptions}}' 2>/dev/null || true

printf '\\n== Slurm ==\\n'
command -v sbatch || true
command -v squeue || true
command -v sacct || true
command -v scancel || true
sinfo -o '%P %a %l %G %c %m' 2>/dev/null | head -20 || true
squeue -u "$USER" -o '%.18i %.12P %.24j %.10T %.10M %.10l %.12R' 2>/dev/null | head -20 || true

printf '\\n== Network ==\\n'
getent hosts gitee.com github.com 2>/dev/null || true
curl -I --max-time 5 https://gitee.com 2>/dev/null | head -5 || true
curl -I --max-time 5 https://github.com 2>/dev/null | head -5 || true
```

## 重点记录内容

执行后，建议把以下信息整理到项目的部署记录中：

- 操作系统和内核版本；
- Python 和 Conda 版本；
- 可用 Conda 环境；
- 是否存在 Docker，以及当前用户是否有 Docker 权限；
- Slurm 命令是否可用；
- 可用分区、最长运行时间和 GPU 类型；
- Web 服务容器是否能调用 Slurm 命令；
- 日志目录和作业工作目录的实际路径；
- Gitee、GitHub 等外网 HTTPS 是否可访问。

## 检查 Dashboard 所需的关键能力

Dashboard 正式开发前，至少需要确认：

```bash
command -v sbatch squeue sacct scancel
docker version
docker compose version
test -r /etc/slurm/slurm.conf && echo 'slurm.conf readable' || true
```

后端容器能否调用 Slurm 是部署成败的关键。不能只在宿主机上验证命令可用，还需要在最终的 `api` 容器中验证：

```bash
docker compose exec api sbatch --version
docker compose exec api squeue --version
```

如果 Slurm 客户端配置、认证文件或命令路径不能直接挂载到容器，需要由平台管理员确定受控的提交方式，例如宿主机代理服务或专用提交用户。

## 不要收集或提交的内容

以下内容不应写入项目文档、Issue 或 Git：

- 登录密码和 TOTP 密钥；
- SSH 私钥和 Gitee Token；
- 完整的用户环境变量；
- 其他用户的作业命令和日志；
- 生产数据库凭据；
- 未脱敏的内部主机地址和访问令牌。
