import { type FormEvent, useEffect, useRef, useState } from "react";

import { ApiError, cancelJob, cloneJob, fetchJob, fetchJobLog, fetchJobSummary, fetchJobUsage, fetchJobs, fetchRuntimeInfo, submitJob } from "../../api/jobs";
import type { Job, JobListResponse, JobLogStream, JobState, JobSubmitRequest, JobUsageResponse, RuntimeCapabilities, RuntimeInfo, UserJobSummary } from "./types";

const PAGE_SIZE = 5;
const ACTIVE_REFRESH_MS = 5_000;
const IDLE_REFRESH_MS = 15_000;

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
  name: "python-env-check",
  command: "python3 --version",
  partition: "Students",
  account: "stu",
  qos: "qos_stu_default",
  resources: { cpus: 1, memory_mb: 512, gpus: 0, time_limit_minutes: 5 },
};

const jobTemplates: Array<{
  id: string;
  label: string;
  description: string;
  submission: JobSubmitRequest;
}> = [
  {
    id: "cpu-check",
    label: "CPU 快速检查",
    description: "单核、无 GPU、5 分钟，适合环境与依赖确认。",
    submission: {
      ...defaultSubmission,
      name: "cpu-env-check",
      command: "python3 --version",
      resources: { cpus: 1, memory_mb: 1024, gpus: 0, time_limit_minutes: 5 },
    },
  },
  {
    id: "cancelable-cpu",
    label: "可取消 CPU 任务",
    description: "持续运行的受控 Python 任务，适合验证观察、取消和克隆。",
    submission: {
      ...defaultSubmission,
      name: "cancelable-cpu-task",
      command: "python3 -m timeit -n 1000000000 pass",
      resources: { cpus: 1, memory_mb: 512, gpus: 0, time_limit_minutes: 2 },
    },
  },
  {
    id: "gpu-allocation",
    label: "GPU 分配检查",
    description: "申请 1 张 GPU 并运行 Python 环境检查；只验证分配，不宣称实际利用率。",
    submission: {
      ...defaultSubmission,
      name: "gpu-allocation-check",
      command: "python3 --version",
      resources: { cpus: 1, memory_mb: 1024, gpus: 1, time_limit_minutes: 5 },
    },
  },
];

function copySubmission(submission: JobSubmitRequest): JobSubmitRequest {
  return { ...submission, resources: { ...submission.resources } };
}

function valueOrDash(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function nativeCapabilitySummary(runtime: RuntimeInfo): string {
  const labels: Array<[keyof RuntimeCapabilities, string]> = [
    ["submit", "提交"],
    ["logs", "日志"],
    ["cancel", "取消"],
    ["clone", "克隆"],
  ];
  const enabled = labels.filter(([key]) => runtime.capabilities[key]).map(([, label]) => label);
  const disabled = labels.filter(([key]) => !runtime.capabilities[key]).map(([, label]) => label);
  return [
    enabled.length > 0 ? `已开放：${enabled.join("、")}` : "当前只开放查询与资源统计",
    disabled.length > 0 ? `未开放：${disabled.join("、")}` : "全部 MVP 能力已开放",
    "所有操作均绑定当前 Unix 账号",
  ].join("；");
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

function ratioPercent(value: number | null, maximum: number | null): number | null {
  if (value === null || maximum === null || maximum <= 0) return null;
  return Math.min(100, Math.max(0, (value / maximum) * 100));
}

function UsageComparison({
  label,
  value,
  maximum,
  detail,
}: {
  label: string;
  value: number | null;
  maximum: number | null;
  detail: string;
}) {
  const percent = ratioPercent(value, maximum);
  return (
    <div className="usage-comparison">
      <div><span>{label}</span><strong>{detail}</strong></div>
      <div
        className={`usage-track ${percent === null ? "is-unknown" : ""}`}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent === null ? undefined : Math.round(percent)}
        aria-valuetext={percent === null ? "平台未提供完整数据" : detail}
      >
        <span style={{ width: percent === null ? "0%" : `${percent}%` }} />
      </div>
    </div>
  );
}

function JobUsagePanel({ jobId, refreshToken }: { jobId: string; refreshToken: string }) {
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
  }, [jobId, refreshToken]);

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
        <>
          <div className="usage-grid">
            {metrics.map(([label, value, unit]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{value}{value !== "平台未提供" && value !== "—" ? unit : ""}</strong>
              </div>
            ))}
          </div>
          <div className="usage-comparisons" aria-label="资源使用对比">
            <UsageComparison
              label="CPU 分配 / 申请"
              value={usage.allocated.cpus}
              maximum={usage.requested.cpus}
              detail={`${valueOrDash(usage.allocated.cpus)} / ${valueOrDash(usage.requested.cpus)} 核`}
            />
            <UsageComparison
              label="峰值内存 / 申请"
              value={usage.max_rss_kb === null ? null : usage.max_rss_kb / 1024}
              maximum={usage.requested.memory_mb}
              detail={`${formatMemoryKb(usage.max_rss_kb)} / ${formatMemory(usage.requested.memory_mb)}`}
            />
            <UsageComparison
              label="运行时长 / 时限"
              value={usage.elapsed_seconds}
              maximum={usage.time_limit_seconds}
              detail={`${formatSeconds(usage.elapsed_seconds)} / ${formatSeconds(usage.time_limit_seconds)}`}
            />
          </div>
        </>
      )}
    </section>
  );
}

function jobDiagnosticHints(job: Job): string[] {
  const hints: string[] = [];
  const reason = job.reason?.toLowerCase() ?? "";
  if (job.state === "TIMEOUT") {
    hints.push("作业达到时限；先检查是否存在重复计算，再按实际需要提高时间上限。 ");
  }
  if (job.state === "FAILED") {
    hints.push("优先查看 stderr 和退出码；不要只根据 FAILED 状态猜测根因。 ");
  }
  if (reason.includes("memory") || reason.includes("oom")) {
    hints.push("调度原因包含内存线索；对比峰值内存与申请内存后再调整资源。 ");
  }
  if (job.exit_code?.startsWith("137:") || job.exit_code === "137") {
    hints.push("退出码 137 常与进程被终止或内存压力有关，需要结合 stderr 与 MaxRSS 确认。 ");
  }
  if (job.state === "PENDING") {
    hints.push(`当前仍在排队${job.reason ? `（${job.reason}）` : ""}；这不代表程序执行失败。`);
  }
  if (job.state === "UNKNOWN") {
    hints.push("Slurm 状态暂时未知，可能处于记账同步窗口；稍后刷新再判断。 ");
  }
  if (job.state === "COMPLETED" && job.exit_code === "0:0") {
    hints.push("Slurm 报告正常完成且退出码为 0:0；资源效率仍需结合统计面板判断。 ");
  }
  return hints.map((hint) => hint.trim());
}

function JobDiagnosticPanel({ job }: { job: Job }) {
  const hints = jobDiagnosticHints(job);
  if (hints.length === 0) return null;
  return (
    <section className="diagnostic-panel" aria-labelledby="diagnostic-title">
      <div>
        <p className="section-kicker">排查提示</p>
        <h3 id="diagnostic-title">基于当前证据的下一步</h3>
      </div>
      <ul>{hints.map((hint) => <li key={hint}>{hint}</li>)}</ul>
      <small>提示用于缩小排查范围，不替代 Slurm 状态、退出码和日志原文。</small>
    </section>
  );
}

function JobLogPanel({ jobId, active }: { jobId: string; active: boolean }) {
  const [stream, setStream] = useState<JobLogStream>("stdout");
  const [content, setContent] = useState("");
  const [nextOffset, setNextOffset] = useState(0);
  const [available, setAvailable] = useState(true);
  const [eof, setEof] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [followKey, setFollowKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setContent("");
    setNextOffset(0);
    setFollowKey(0);
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

  useEffect(() => {
    if (!active || loading) return;
    const timer = window.setTimeout(() => setFollowKey((value) => value + 1), 3_000);
    return () => window.clearTimeout(timer);
  }, [active, followKey, jobId, loading, stream]);

  useEffect(() => {
    if (followKey === 0 || !active) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchJobLog(jobId, stream, nextOffset, controller.signal)
      .then((log) => {
        setContent((current) => current + log.content);
        setNextOffset(log.next_offset);
        setAvailable(log.available);
        setEof(log.eof);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof ApiError ? reason.message : "无法自动跟踪作业日志");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [active, followKey, jobId, stream]);

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
        <span>
          {available ? `已读取 ${nextOffset} 字节` : "等待日志文件"}
          {active ? " · 每 3 秒自动跟踪" : ""}
        </span>
        <button className="quiet-button" type="button" disabled={loading || !available || eof} onClick={() => void loadMore()}>
          {loading ? "读取中…" : eof ? "已到末尾" : "继续加载"}
        </button>
      </div>
    </section>
  );
}

function JobDetail({
  job,
  capabilities,
  actionPending,
  actionError,
  onCancelJob,
  onCloneJob,
  onClose,
}: {
  job: Job;
  capabilities: RuntimeCapabilities;
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
      <JobDiagnosticPanel job={job} />
      {capabilities.usage && <JobUsagePanel jobId={job.id} refreshToken={job.updated_at} />}
      {capabilities.logs
        ? <JobLogPanel jobId={job.id} active={["PENDING", "RUNNING"].includes(job.state)} />
        : <div className="mode-notice compact">Native 只读阶段暂不开放日志路径读取。</div>}
      {job.command === null && (
        <p className="detail-note">当前 Slurm 查询未提供提交命令和完整事件时间；仅由可信元数据补充这些字段。</p>
      )}
      {actionError && <p className="form-error" role="alert">{actionError}</p>}
      {(capabilities.cancel || capabilities.clone) && (
        <div className="detail-actions">
          {capabilities.cancel && (
            <button
              className="danger-button"
              type="button"
              disabled={actionPending !== null || !["PENDING", "RUNNING"].includes(job.state)}
              onClick={onCancelJob}
            >
              {actionPending === "cancel" ? "正在取消…" : "取消作业"}
            </button>
          )}
          {capabilities.clone && (
            <button
              className="primary-button"
              type="button"
              disabled={actionPending !== null || job.command === null}
              onClick={onCloneJob}
            >
              {actionPending === "clone" ? "正在克隆…" : "克隆为新作业"}
            </button>
          )}
        </div>
      )}
    </aside>
  );
}

function JobSubmitForm({
  onCancel,
  onSubmitted,
  nativeMode,
}: {
  onCancel: () => void;
  onSubmitted: (job: Job) => void;
  nativeMode: boolean;
}) {
  const [submission, setSubmission] = useState<JobSubmitRequest>(defaultSubmission);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const idempotency = useRef<{ fingerprint: string; key: string } | null>(null);

  const updateResource = (field: keyof JobSubmitRequest["resources"], value: number) => {
    setSubmission((current) => ({
      ...current,
      resources: { ...current.resources, [field]: value },
    }));
  };

  const applyTemplate = (template: (typeof jobTemplates)[number]) => {
    setSubmission(copySubmission(template.submission));
    setSubmitError(null);
    idempotency.current = null;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      const fingerprint = JSON.stringify(submission);
      if (idempotency.current?.fingerprint !== fingerprint) {
        idempotency.current = { fingerprint, key: crypto.randomUUID() };
      }
      onSubmitted(await submitJob(submission, idempotency.current.key));
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
          <p className="section-kicker">{nativeMode ? "真实 Slurm 提交" : "Fixture 提交"}</p>
          <h2>配置一个排队作业</h2>
          <p>
            {nativeMode
              ? "提交将进入 Slurm；重复点击会复用同一请求键，活跃作业达到上限时会被拒绝。"
              : "当前只模拟提交，不会执行命令或占用服务器资源。"}
          </p>
        </div>
        <button className="quiet-button" type="button" onClick={onCancel}>关闭</button>
      </div>

      <div className="template-picker" aria-label="常用作业模板">
        {jobTemplates.map((template) => (
          <button key={template.id} type="button" onClick={() => applyTemplate(template)}>
            <strong>{template.label}</strong>
            <span>{template.description}</span>
          </button>
        ))}
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
            aria-describedby="native-command-policy"
            value={submission.command}
            onChange={(event) => setSubmission({ ...submission, command: event.target.value })}
          />
          {nativeMode && (
            <small className="field-hint" id="native-command-policy">
              当前仅允许 python/python3 及安全参数；不支持管道、重定向、命令替换或绝对路径。
            </small>
          )}
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
          {submitting ? "正在提交…" : nativeMode ? "提交到 Slurm" : "提交到 Fixture 队列"}
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
  const operationIdempotency = useRef<Record<string, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [runtimeError, setRuntimeError] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [pageVisible, setPageVisible] = useState(() => !document.hidden);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [stateEvents, setStateEvents] = useState<string[]>([]);
  const previousStates = useRef<Map<string, JobState>>(new Map());

  useEffect(() => {
    const updateVisibility = () => setPageVisible(!document.hidden);
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchJobs(page, PAGE_SIZE, stateFilter, controller.signal)
      .then((payload) => {
        const nextStates = new Map(previousStates.current);
        const changes: string[] = [];
        for (const job of payload.items) {
          const previous = previousStates.current.get(job.id);
          if (previous !== undefined && previous !== job.state) {
            changes.push(`#${job.slurm_job_id}：${stateLabels[previous]} → ${stateLabels[job.state]}`);
          }
          nextStates.set(job.id, job.state);
        }
        previousStates.current = nextStates;
        if (changes.length > 0) {
          setStateEvents((current) => [...changes, ...current].slice(0, 4));
        }
        setData(payload);
        setLastSyncedAt(new Date());
        void fetchRuntimeInfo(controller.signal)
          .then((runtimeInfo) => {
            setRuntime(runtimeInfo);
            setRuntimeError(false);
          })
          .catch((reason: unknown) => {
            if (reason instanceof DOMException && reason.name === "AbortError") return;
            setRuntimeError(true);
          });
        setSelectedJob((current) => {
          if (current === null) return null;
          return payload.items.find((job) => job.id === current.id) ?? current;
        });
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof ApiError ? reason.message : "无法连接作业 API");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [page, reloadKey, stateFilter]);

  const hasActiveJobs = data?.items.some((job) => ["PENDING", "RUNNING"].includes(job.state)) ?? false;
  const refreshDelay = hasActiveJobs ? ACTIVE_REFRESH_MS : IDLE_REFRESH_MS;

  useEffect(() => {
    if (!autoRefresh || !pageVisible) return;
    const timer = window.setTimeout(() => setReloadKey((value) => value + 1), refreshDelay);
    return () => window.clearTimeout(timer);
  }, [autoRefresh, pageVisible, refreshDelay, reloadKey]);

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
    const operationKey = `${operation}:${selectedJob.id}`;
    const idempotencyKey = operationIdempotency.current[operationKey] ?? crypto.randomUUID();
    operationIdempotency.current[operationKey] = idempotencyKey;
    try {
      const job = operation === "cancel"
        ? await cancelJob(selectedJob.id, idempotencyKey)
        : await cloneJob(selectedJob.id, idempotencyKey);
      delete operationIdempotency.current[operationKey];
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
        <div className={`connection-pill ${error ? "is-offline" : runtime?.degraded ? "is-degraded" : ""}`}>
          <span className="status-dot" />
          {error || runtimeError
            ? "API 异常"
            : loading || runtime === null
              ? "正在同步"
              : runtime.degraded
                ? "Fixture 演示回退"
                : runtime.read_only
                ? "Native 只读"
                : runtime.data_source === "native"
                  ? "Native 真实交互"
                  : "Fixture 已连接"}
        </div>
      </header>

      <section className="workspace" aria-labelledby="jobs-title">
        {runtime?.data_source === "native" && (
          <div className={`mode-notice ${runtime.degraded ? "fallback-notice" : ""}`} role="status">
            <strong>
              {runtime.degraded
                ? "Slurm 暂不可用 · 已进入只读演示回退"
                : runtime.read_only
                  ? "Native 只读模式"
                  : "真实 Slurm 操作模式"}
            </strong>
            <span>
              {runtime.degraded
                ? "当前展示脱敏 Fixture；提交、取消和克隆已强制关闭，系统将在冷却后自动探测 Native 恢复。"
                : `当前只展示真实 Slurm 作业；${nativeCapabilitySummary(runtime)}`}
            </span>
          </div>
        )}
        <div className="section-heading">
          <div>
            <p className="section-kicker">作业队列与历史</p>
            <h2 id="jobs-title">当前账户的计算任务</h2>
            <p>自动跟踪状态变化，并对比申请资源、分配资源与实际指标。</p>
          </div>
          <div className="section-actions">
            <div className="refresh-control" role="group" aria-label="自动刷新控制">
              <button type="button" onClick={() => setAutoRefresh((value) => !value)}>
                {autoRefresh ? "暂停自动刷新" : "开启自动刷新"}
              </button>
              <button type="button" onClick={() => setReloadKey((value) => value + 1)}>立即刷新</button>
              <span>
                {!pageVisible
                  ? "页面隐藏，已暂停"
                  : autoRefresh
                    ? `${hasActiveJobs ? "活跃" : "空闲"} · ${refreshDelay / 1000} 秒`
                    : "自动刷新已暂停"}
              </span>
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
            {runtime?.capabilities.submit && (
              <button className="primary-button new-job-button" type="button" onClick={() => setShowSubmitForm(true)}>
                新建作业
              </button>
            )}
          </div>
        </div>

        <JobSummaryPanel refreshKey={reloadKey} />

        <div className="sync-status" aria-live="polite">
          <span>{lastSyncedAt ? `上次同步 ${lastSyncedAt.toLocaleTimeString("zh-CN", { hour12: false })}` : "等待首次同步"}</span>
          <span>页面失焦时自动暂停网络请求</span>
        </div>

        {stateEvents.length > 0 && (
          <div className="notice state-change-notice" role="status">
            <div><strong>作业状态发生变化</strong><span>{stateEvents.join("；")}</span></div>
            <button type="button" onClick={() => setStateEvents([])}>清除</button>
          </div>
        )}

        {showSubmitForm && (
          <JobSubmitForm
            nativeMode={runtime?.serving_source === "native"}
            onCancel={() => setShowSubmitForm(false)}
            onSubmitted={(job) => {
              setShowSubmitForm(false);
              setSubmissionNotice(
                runtime?.serving_source === "native"
                  ? `作业 #${job.slurm_job_id} 已提交到 Slurm`
                  : `作业 #${job.slurm_job_id} 已加入 Fixture 队列`,
              );
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
          capabilities={runtime?.capabilities ?? {
            list_jobs: true,
            job_details: true,
            usage: true,
            submit: false,
            cancel: false,
            clone: false,
            logs: false,
          }}
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
