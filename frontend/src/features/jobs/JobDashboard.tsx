import { useEffect, useState } from "react";

import { ApiError, fetchJob, fetchJobs } from "../../api/jobs";
import type { Job, JobListResponse, JobState } from "./types";

const PAGE_SIZE = 5;

const stateLabels: Record<JobState, string> = {
  PENDING: "排队中",
  RUNNING: "运行中",
  COMPLETED: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消",
  TIMEOUT: "超时",
  UNKNOWN: "未知",
};

const stateOptions: Array<{ value: JobState | "ALL"; label: string }> = [
  { value: "ALL", label: "全部状态" },
  ...Object.entries(stateLabels).map(([value, label]) => ({ value: value as JobState, label })),
];

function valueOrDash(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function formatMemory(memoryMb: number | null): string {
  if (memoryMb === null) return "—";
  return memoryMb >= 1024 ? `${memoryMb / 1024} GiB` : `${memoryMb} MiB`;
}

function JobDetail({ job, onClose }: { job: Job; onClose: () => void }) {
  const details = [
    ["Slurm Job ID", job.slurm_job_id],
    ["状态", stateLabels[job.state]],
    ["分区", job.partition],
    ["节点", job.node],
    ["账户 / QoS", [job.account, job.qos].filter(Boolean).join(" / ")],
    ["CPU", job.resources.cpus],
    ["内存", formatMemory(job.resources.memory_mb)],
    ["GPU", job.resources.gpus],
    ["时限", job.resources.time_limit_minutes ? `${job.resources.time_limit_minutes} 分钟` : null],
    ["退出码", job.exit_code],
    ["排队或失败原因", job.reason],
  ] as const;

  return (
    <aside className="detail-panel" aria-labelledby="detail-title">
      <div className="detail-heading">
        <div>
          <p className="section-kicker">作业详情</p>
          <h2 id="detail-title">{job.name}</h2>
        </div>
        <button className="quiet-button" type="button" onClick={onClose} aria-label="关闭作业详情">
          关闭
        </button>
      </div>
      <dl className="detail-grid">
        {details.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{valueOrDash(value)}</dd>
          </div>
        ))}
      </dl>
      {job.command === null && (
        <p className="detail-note">Fixture 查询暂不提供提交命令和事件时间，真实平台接入后再补充。</p>
      )}
    </aside>
  );
}

export function JobDashboard() {
  const [stateFilter, setStateFilter] = useState<JobState | "ALL">("ALL");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<JobListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchJobs(page, PAGE_SIZE, stateFilter, controller.signal)
      .then(setData)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof ApiError ? reason.message : "无法连接作业 API");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [page, reloadKey, stateFilter]);

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  const openDetail = async (jobId: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      setSelectedJob(await fetchJob(jobId));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "无法读取作业详情");
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">107</div>
        <div>
          <p className="eyebrow">STUDENT SLURM CONSOLE</p>
          <h1>算力作业</h1>
        </div>
        <div className={`connection-pill ${error ? "is-offline" : ""}`}>
          <span className="status-dot" />
          {error ? "API 异常" : loading ? "正在同步" : "Fixture 已连接"}
        </div>
      </header>

      <section className="workspace" aria-labelledby="jobs-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">作业队列与历史</p>
            <h2 id="jobs-title">当前账户的计算任务</h2>
            <p>先确认数据和操作路径，视觉细节将在后续统一完善。</p>
          </div>
          <label className="filter-control">
            <span>状态筛选</span>
            <select
              value={stateFilter}
              onChange={(event) => {
                setStateFilter(event.target.value as JobState | "ALL");
                setPage(1);
                setSelectedJob(null);
              }}
            >
              {stateOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>

        {error && (
          <div className="notice error-notice" role="alert">
            <div><strong>暂时无法读取作业</strong><span>{error}</span></div>
            <button type="button" onClick={() => setReloadKey((value) => value + 1)}>重新加载</button>
          </div>
        )}

        <div className="list-frame" aria-busy={loading}>
          <div className="list-summary">
            <span>{loading ? "正在读取…" : `共 ${data?.total ?? 0} 个作业`}</span>
            <span>第 {page} / {totalPages} 页</span>
          </div>

          {!loading && !error && data?.items.length === 0 && (
            <div className="empty-state">
              <strong>没有符合条件的作业</strong>
              <span>切换状态筛选，或等待新的作业进入队列。</span>
            </div>
          )}

          <div className="job-list">
            {loading
              ? Array.from({ length: 3 }, (_, index) => <div className="job-card skeleton" key={index} />)
              : data?.items.map((job) => (
                  <article className={`job-card state-${job.state.toLowerCase()}`} key={job.id}>
                    <div className="state-rail" aria-hidden="true" />
                    <div className="job-main">
                      <div className="job-title-row">
                        <div>
                          <span className="job-id">#{job.slurm_job_id}</span>
                          <h3>{job.name}</h3>
                        </div>
                        <span className="state-badge">{stateLabels[job.state]}</span>
                      </div>
                      <div className="job-meta">
                        <span>分区 {valueOrDash(job.partition)}</span>
                        <span>节点 {valueOrDash(job.node)}</span>
                        <span>CPU {valueOrDash(job.resources.cpus)}</span>
                        <span>GPU {valueOrDash(job.resources.gpus)}</span>
                        <span>内存 {formatMemory(job.resources.memory_mb)}</span>
                      </div>
                    </div>
                    <button
                      className="detail-button"
                      type="button"
                      disabled={detailLoading}
                      onClick={() => void openDetail(job.id)}
                    >
                      查看详情
                    </button>
                  </article>
                ))}
          </div>

          <nav className="pagination" aria-label="作业列表分页">
            <button type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}>
              上一页
            </button>
            <button
              type="button"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((value) => value + 1)}
            >
              下一页
            </button>
          </nav>
        </div>
      </section>

      {selectedJob && <JobDetail job={selectedJob} onClose={() => setSelectedJob(null)} />}
    </main>
  );
}
