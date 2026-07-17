import { type FormEvent, useEffect, useState } from "react";

import { ApiError, cancelJob, cloneJob, fetchJob, fetchJobLog, fetchJobSummary, fetchJobUsage, fetchJobs, submitJob } from "../../api/jobs";
import type { Job, JobListResponse, JobLogStream, JobState, JobSubmitRequest, JobUsageResponse, UserJobSummary } from "./types";

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

const defaultSubmission: JobSubmitRequest = {
  name: "course-training",
  command: "python train.py",
  partition: "Students",
  account: "stu",
  qos: "qos_stu_default",
  resources: { cpus: 2, memory_mb: 4096, gpus: 1, time_limit_minutes: 60 },
};

function valueOrDash(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function formatMemory(memoryMb: number | null): string {
  if (memoryMb === null) return "—";
  return memoryMb >= 1024 ? `${memoryMb / 1024} GiB` : `${memoryMb} MiB`;
}

function formatMemoryKb(memoryKb: number | null): string {
  if (memoryKb === null) return "平台未提供";
  if (memoryKb < 1024) return `${memoryKb} KiB`;
  return formatMemory(memoryKb / 1024);
}

function JobSummaryPanel({ refreshKey }: { refreshKey: number }) {
  const [summary, setSummary] = useState<UserJobSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    fetchJobSummary(controller.signal)
      .then(setSummary)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof ApiError ? reason.message : "无法读取账户摘要");
      });
    return () => controller.abort();
  }, [refreshKey]);

  if (error) return <div className="summary-error" role="alert">账户摘要暂时不可用：{error}</div>;
  if (!summary) return <div className="summary-loading">正在汇总当前账户作业…</div>;

  const headline = [
    ["作业总数", summary.total_jobs],
    ["活跃作业", summary.active_jobs],
    ["成功完成", summary.successful_jobs],
    ["失败/取消/超时", summary.unsuccessful_jobs],
  ] as const;
  const resources = [
    ["CPU 字段合计", `${summary.resources.cpus} 核`, summary.resources.cpus_jobs],
    ["GPU 字段合计", `${summary.resources.gpus} 张`, summary.resources.gpus_jobs],
    ["内存字段合计", formatMemory(summary.resources.memory_mb), summary.resources.memory_jobs],
    ["时限字段合计", `${summary.resources.time_limit_minutes} 分钟`, summary.resources.time_limit_jobs],
  ] as const;

  return (
    <section className="account-summary" aria-labelledby="account-summary-title">
      <div className="summary-heading">
        <div>
          <p className="section-kicker">当前用户摘要</p>
          <h3 id="account-summary-title">作业状态与资源快照</h3>
        </div>
        <span>资源为当前记录中的申请或分配值，并非实际利用率</span>
      </div>
      <div className="summary-headline">
        {headline.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </div>
      <div className="state-distribution">
        {stateOptions.slice(1).map(({ value, label }) => (
          <span key={value}>{label} <strong>{summary.state_counts[value as JobState]}</strong></span>
        ))}
      </div>
      <div className="summary-resources">
        {resources.map(([label, value, coverage]) => (
          <div key={label}><span>{label}</span><strong>{value}</strong><small>覆盖 {coverage}/{summary.total_jobs} 个作业</small></div>
        ))}
      </div>
    </section>
  );
}

function formatSeconds(seconds: number | null): string {
  if (seconds === null) return "平台未提供";
  if (seconds === 0) return "少于 1 秒";
  if (seconds < 60) return `${seconds.toFixed(seconds % 1 === 0 ? 0 : 3)} 秒`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = Math.floor(seconds % 60);
  return [hours ? `${hours} 小时` : "", minutes ? `${minutes} 分钟` : "", remainder ? `${remainder} 秒` : ""]
    .filter(Boolean)
    .join(" ");
}

function JobUsagePanel({ jobId }: { jobId: string }) {
  const [usage, setUsage] = useState<JobUsageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setUsage(null);
    setError(null);
    fetchJobUsage(jobId, controller.signal)
      .then(setUsage)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof ApiError ? reason.message : "无法读取资源统计");
      });
    return () => controller.abort();
  }, [jobId]);

  const metrics = usage
    ? [
        ["申请 CPU", valueOrDash(usage.requested.cpus), "核"],
        ["分配 CPU", valueOrDash(usage.allocated.cpus), "核"],
        ["申请内存", formatMemory(usage.requested.memory_mb), ""],
        ["峰值内存", formatMemoryKb(usage.max_rss_kb), ""],
        ["分配 GPU", valueOrDash(usage.allocated.gpus), "张"],
        ["GPU 实际使用", "平台未提供", ""],
        ["运行时长", formatSeconds(usage.elapsed_seconds), ""],
        ["累计 CPU 时间", formatSeconds(usage.total_cpu_seconds), ""],
      ]
    : [];

  return (
    <section className="usage-panel" aria-labelledby="usage-title">
      <div className="usage-heading">
        <div>
          <p className="section-kicker">资源统计</p>
          <h3 id="usage-title">申请、分配与实际使用</h3>
        </div>
        <span>GPU利用率未由平台提供</span>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {!error && !usage && <div className="usage-loading">正在读取资源统计…</div>}
      {usage && (
        <div className="usage-grid">
          {metrics.map(([label, value, unit]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}{value !== "平台未提供" && value !== "—" ? unit : ""}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function JobLogPanel({ jobId }: { jobId: string }) {
  const [stream, setStream] = useState<JobLogStream>("stdout");
  const [content, setContent] = useState("");
  const [nextOffset, setNextOffset] = useState(0);
  const [available, setAvailable] = useState(true);
  const [eof, setEof] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setContent("");
    setNextOffset(0);
    fetchJobLog(jobId, stream, 0, controller.signal)
      .then((log) => {
        setContent(log.content);
        setNextOffset(log.next_offset);
        setAvailable(log.available);
        setEof(log.eof);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof ApiError ? reason.message : "无法读取作业日志");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [jobId, refreshKey, stream]);

  const loadMore = async () => {
    setLoading(true);
    setError(null);
    try {
      const log = await fetchJobLog(jobId, stream, nextOffset);
      setContent((current) => current + log.content);
      setNextOffset(log.next_offset);
      setAvailable(log.available);
      setEof(log.eof);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "无法继续读取作业日志");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="log-panel" aria-labelledby="job-log-title">
      <div className="log-heading">
        <div>
          <p className="section-kicker">增量日志</p>
          <h3 id="job-log-title">标准输出与错误</h3>
        </div>
        <div className="log-toolbar">
          <div className="stream-tabs" role="tablist" aria-label="日志流">
            {(["stdout", "stderr"] as const).map((value) => (
              <button
                type="button"
                role="tab"
                aria-selected={stream === value}
                className={stream === value ? "is-active" : ""}
                key={value}
                onClick={() => setStream(value)}
              >
                {value}
              </button>
            ))}
          </div>
          <button className="quiet-button" type="button" disabled={loading} onClick={() => setRefreshKey((value) => value + 1)}>
            刷新
          </button>
        </div>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {!error && !available && <div className="log-empty">该日志尚未产生。</div>}
      {!error && available && (
        <pre className="log-output" aria-live="polite">{content || (loading ? "正在读取…" : "日志为空")}</pre>
      )}
      <div className="log-footer">
        <span>{available ? `已读取 ${nextOffset} 字节` : "等待日志文件"}</span>
        <button className="quiet-button" type="button" disabled={loading || !available || eof} onClick={() => void loadMore()}>
          {loading ? "读取中…" : eof ? "已到末尾" : "继续加载"}
        </button>
      </div>
    </section>
  );
}

function JobDetail({
  job,
  actionPending,
  actionError,
  onCancelJob,
  onCloneJob,
  onClose,
}: {
  job: Job;
  actionPending: "cancel" | "clone" | null;
  actionError: string | null;
  onCancelJob: () => void;
  onCloneJob: () => void;
  onClose: () => void;
}) {
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
      <JobUsagePanel jobId={job.id} />
      <JobLogPanel jobId={job.id} />
      {job.command === null && (
        <p className="detail-note">Fixture 查询暂不提供提交命令和事件时间，真实平台接入后再补充。</p>
      )}
      {actionError && <p className="form-error" role="alert">{actionError}</p>}
      <div className="detail-actions">
        <button
          className="danger-button"
          type="button"
          disabled={actionPending !== null || !["PENDING", "RUNNING"].includes(job.state)}
          onClick={onCancelJob}
        >
          {actionPending === "cancel" ? "正在取消…" : "取消作业"}
        </button>
        <button
          className="primary-button"
          type="button"
          disabled={actionPending !== null || job.command === null}
          onClick={onCloneJob}
        >
          {actionPending === "clone" ? "正在克隆…" : "克隆为新作业"}
        </button>
      </div>
    </aside>
  );
}

function JobSubmitForm({
  onCancel,
  onSubmitted,
}: {
  onCancel: () => void;
  onSubmitted: (job: Job) => void;
}) {
  const [submission, setSubmission] = useState<JobSubmitRequest>(defaultSubmission);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const updateResource = (field: keyof JobSubmitRequest["resources"], value: number) => {
    setSubmission((current) => ({
      ...current,
      resources: { ...current.resources, [field]: value },
    }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      onSubmitted(await submitJob(submission));
    } catch (reason) {
      setSubmitError(reason instanceof ApiError ? reason.message : "无法提交作业");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="submit-panel" onSubmit={(event) => void handleSubmit(event)}>
      <div className="submit-heading">
        <div>
          <p className="section-kicker">Fixture 提交</p>
          <h2>配置一个排队作业</h2>
          <p>当前只模拟提交，不会执行命令或占用服务器资源。</p>
        </div>
        <button className="quiet-button" type="button" onClick={onCancel}>关闭</button>
      </div>

      <div className="form-grid">
        <label className="field field-wide">
          <span>作业名称</span>
          <input
            required
            maxLength={64}
            pattern="[A-Za-z0-9][A-Za-z0-9._-]*"
            value={submission.name}
            onChange={(event) => setSubmission({ ...submission, name: event.target.value })}
          />
        </label>
        <label className="field field-wide">
          <span>运行命令</span>
          <input
            required
            maxLength={500}
            value={submission.command}
            onChange={(event) => setSubmission({ ...submission, command: event.target.value })}
          />
        </label>
        <label className="field">
          <span>CPU（1–4）</span>
          <input type="number" min={1} max={4} value={submission.resources.cpus} onChange={(event) => updateResource("cpus", Number(event.target.value))} />
        </label>
        <label className="field">
          <span>GPU（0–1）</span>
          <input type="number" min={0} max={1} value={submission.resources.gpus} onChange={(event) => updateResource("gpus", Number(event.target.value))} />
        </label>
        <label className="field">
          <span>内存 MiB</span>
          <input type="number" min={512} max={16384} step={512} value={submission.resources.memory_mb} onChange={(event) => updateResource("memory_mb", Number(event.target.value))} />
        </label>
        <label className="field">
          <span>时长（分钟）</span>
          <input type="number" min={1} max={240} value={submission.resources.time_limit_minutes} onChange={(event) => updateResource("time_limit_minutes", Number(event.target.value))} />
        </label>
      </div>

      <div className="fixed-config">
        <span>分区 <strong>Students</strong></span>
        <span>账户 <strong>stu</strong></span>
        <span>QoS <strong>qos_stu_default</strong></span>
      </div>
      {submitError && <p className="form-error" role="alert">{submitError}</p>}
      <div className="form-actions">
        <button className="quiet-button" type="button" onClick={onCancel}>取消</button>
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? "正在提交…" : "提交到 Fixture 队列"}
        </button>
      </div>
    </form>
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
  const [showSubmitForm, setShowSubmitForm] = useState(false);
  const [submissionNotice, setSubmissionNotice] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState<"cancel" | "clone" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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

  const operateOnJob = async (operation: "cancel" | "clone") => {
    if (!selectedJob) return;
    if (operation === "cancel" && !window.confirm(`确定取消作业 #${selectedJob.slurm_job_id} 吗？`)) return;
    setActionPending(operation);
    setActionError(null);
    try {
      const job = operation === "cancel"
        ? await cancelJob(selectedJob.id)
        : await cloneJob(selectedJob.id);
      setSelectedJob(job);
      setSubmissionNotice(
        operation === "cancel"
          ? `作业 #${job.slurm_job_id} 已取消`
          : `已克隆为新作业 #${job.slurm_job_id}`,
      );
      setStateFilter("ALL");
      setPage(1);
      setReloadKey((value) => value + 1);
    } catch (reason) {
      setActionError(reason instanceof ApiError ? reason.message : "作业操作失败");
    } finally {
      setActionPending(null);
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
          <div className="section-actions">
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
            <button className="primary-button new-job-button" type="button" onClick={() => setShowSubmitForm(true)}>
              新建作业
            </button>
          </div>
        </div>

        <JobSummaryPanel refreshKey={reloadKey} />

        {showSubmitForm && (
          <JobSubmitForm
            onCancel={() => setShowSubmitForm(false)}
            onSubmitted={(job) => {
              setShowSubmitForm(false);
              setSubmissionNotice(`作业 #${job.slurm_job_id} 已加入 Fixture 队列`);
              setStateFilter("ALL");
              setPage(1);
              setSelectedJob(job);
              setReloadKey((value) => value + 1);
            }}
          />
        )}

        {submissionNotice && (
          <div className="notice success-notice" role="status">
            <div><strong>提交成功</strong><span>{submissionNotice}</span></div>
            <button type="button" onClick={() => setSubmissionNotice(null)}>知道了</button>
          </div>
        )}

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

      {selectedJob && (
        <JobDetail
          job={selectedJob}
          actionPending={actionPending}
          actionError={actionError}
          onCancelJob={() => void operateOnJob("cancel")}
          onCloneJob={() => void operateOnJob("clone")}
          onClose={() => {
            setSelectedJob(null);
            setActionError(null);
          }}
        />
      )}
    </main>
  );
}
