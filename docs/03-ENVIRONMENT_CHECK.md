# 03 算力平台环境快速检查

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

## 当前容器部署结论

本次在 `tradmin-02` 登录节点检查到：

- Docker CLI、Buildx 和 Compose 已安装；
- 当前用户不能访问系统 Docker socket；
- `rootlesskit`、`slirp4netns` 已安装；
- 当前用户没有 `/etc/subuid` 和 `/etc/subgid` 映射；
- user namespace 当前不可用；
- 没有发现可用的 Podman 或 Buildah。

因此，当前环境还不能直接运行用户级 Docker daemon。Dashboard 仍然可以采用用户级容器部署，但需要平台管理员完成 Rootless Docker 的最小准备：

1. 为部署账号配置 subordinate UID/GID 映射；
2. 允许该账号使用 user namespace；
3. 配置 Rootless Docker daemon 和用户级 systemd 服务；
4. 确定 Dashboard 的监听端口、日志目录和重启策略。

不建议为了 Dashboard 把普通学生账号加入系统 `docker` 组，因为 Docker socket 权限通常等同于主机 root 权限。若平台不允许 Rootless Docker，可以考虑以下替代方案：

- 由管理员在专用服务节点运行 Dashboard 容器；
- 使用管理员提供的受控部署服务；
- 直接以用户级 Python/Node 服务运行 Dashboard，并由反向代理转发；
- 在其他机器构建镜像，再由管理员负责运行生产容器。

Dashboard 只需要运行自身的 API、前端和数据库服务，不需要管理平台上其他用户的容器；但“只运行自己的服务”并不能绕过 Docker daemon、user namespace 和端口监听权限要求。

## 不要收集或提交的内容

以下内容不应写入项目文档、Issue 或 Git：

- 登录密码和 TOTP 密钥；
- SSH 私钥和 Gitee Token；
- 完整的用户环境变量；
- 其他用户的作业命令和日志；
- 生产数据库凭据；
- 未脱敏的内部主机地址和访问令牌。
