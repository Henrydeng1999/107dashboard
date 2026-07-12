#!/usr/bin/env bash
#SBATCH --job-name=dashboard-env-check
#SBATCH --partition=Students
#SBATCH --account=stu
#SBATCH --qos=qos_stu_default
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --gres=gpu:1
#SBATCH --time=00:05:00

set -u

section() {
    printf '\n== %s ==\n' "$1"
}

section "Job"
printf 'date=%s\n' "$(date --iso-8601=seconds)"
printf 'user=%s\n' "$USER"
printf 'job_id=%s\n' "${SLURM_JOB_ID:-}"
printf 'job_name=%s\n' "${SLURM_JOB_NAME:-}"
printf 'cluster=%s\n' "${SLURM_CLUSTER_NAME:-}"
printf 'partition=%s\n' "${SLURM_JOB_PARTITION:-}"
printf 'qos=%s\n' "${SLURM_JOB_QOS:-}"
printf 'account=%s\n' "${SLURM_JOB_ACCOUNT:-}"
printf 'node=%s\n' "${SLURMD_NODENAME:-$(hostname)}"
printf 'cpus=%s\n' "${SLURM_CPUS_PER_TASK:-}"
printf 'memory_per_node_mb=%s\n' "${SLURM_MEM_PER_NODE:-}"
printf 'job_gpus=%s\n' "${SLURM_JOB_GPUS:-}"
printf 'cuda_visible_devices=%s\n' "${CUDA_VISIBLE_DEVICES:-}"

section "Host"
hostname
uname -a
lscpu | grep -E 'Model name|CPU\(s\)|Thread|Core|Socket' | head -10
free -h

section "GPU"
command -v nvidia-smi || true
nvidia-smi || true
nvidia-smi --query-gpu=index,name,uuid,driver_version,memory.total,memory.free,compute_cap --format=csv,noheader || true

section "CUDA"
command -v nvcc || true
nvcc --version 2>/dev/null || true
ls -l /dev/nvidia* 2>/dev/null || true

section "Python"
command -v python3 || true
python3 --version 2>/dev/null || true
python3 - <<'PY'
try:
    import torch
except Exception as exc:
    print(f"torch_import=failed: {exc}")
else:
    print(f"torch_version={torch.__version__}")
    print(f"torch_cuda_available={torch.cuda.is_available()}")
    print(f"torch_cuda_version={torch.version.cuda}")
    print(f"torch_device_count={torch.cuda.device_count()}")
    if torch.cuda.is_available():
        print(f"torch_device_name={torch.cuda.get_device_name(0)}")
PY

section "Slurm Job"
scontrol show job "$SLURM_JOB_ID" -o || true

section "Environment Limits"
ulimit -a

section "Result"
printf 'environment_check=completed\n'
