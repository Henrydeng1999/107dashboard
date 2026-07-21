import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  cancelJob,
  cloneJob,
  fetchJob,
  fetchJobs,
  fetchRuntimeInfo,
} from "../api/jobs";
import {
  formatMemory,
  JobDetail,
  JobSubmitForm,
  JobSummaryPanel,
  stateLabels,
  stateOptions,
} from "../features/jobs/JobDashboard";
import type {
  Job,
  JobListResponse,
  JobState,
  RuntimeCapabilities,
  RuntimeInfo,
} from "../features/jobs/types";

const PAGE_SIZE = 20;
const ACTIVE_REFRESH_MS = 5_000;
const IDLE_REFRESH_MS = 15_000;

const safeCapabilities: RuntimeCapabilities = {
  list_jobs: true,
  job_details: true,
  usage: true,
  submit: false,
  cancel: false,
  clone: false,
  logs: false,
};

function stateTone(state: JobState): "green" | "orange" | "blue" {
  if (state === "PENDING" || state === "TIMEOUT") return "orange";
  if (state === "RUNNING" || state === "UNKNOWN") return "blue";
  return "green";
}

function StatusDot({ tone }: { tone: "green" | "orange" | "blue" }) {
  return <span className={`prototype-status-dot prototype-status-dot--${tone}`} aria-hidden="true" />;
}

function formatDate(value: string | null): string {
  if (value === null) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function runtimeLabel(runtime: RuntimeInfo | null, runtimeError: boolean): string {
  if (runtimeError) return "能力信息不可用";
  if (runtime === null) return "正在确认数据源";
  if (runtime.degraded) return "Fixture 演示回退";
  if (runtime.serving_source === "native" && runtime.read_only) return "Native 只读";
  if (runtime.serving_source === "native") return "Native 真实交互";
  return "Fixture 开发模式";
}

function pagePredicate(subpage: string, job: Job): boolean {
  if (subpage === "活动作业") return job.state === "PENDING" || job.state === "RUNNING";
  if (subpage === "历史作业") return job.state !== "PENDING" && job.state !== "RUNNING";
  return true;
}

export function JobsWorkspace({
  subpage,
  onNavigate,
}: {
  subpage: string;
  onNavigate: (subpage: string) => void;
}) {
  const [stateFilter, setStateFilter] = useState<JobState | "ALL">("ALL");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<JobListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [runtimeError, setRuntimeError] = useState(false);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionPending, setActionPending] = useState<"cancel" | "clone" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [pageVisible, setPageVisible] = useState(() => !document.hidden);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const operationIdempotency = useRef<Record<string, string>>({});

  useEffect(() => {
    const updateVisibility = () => setPageVisible(!document.hidden);
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchRuntimeInfo(controller.signal)
      .then((payload) => {
        setRuntime(payload);
        setRuntimeError(false);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setRuntimeError(true);
      });
    return () => controller.abort();
  }, [reloadKey]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchJobs(page, PAGE_SIZE, stateFilter, controller.signal)
      .then((payload) => {
        setData(payload);
        setLastSyncedAt(new Date());
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

  useEffect(() => {
    setSelectedJob(null);
    setActionError(null);
    if (subpage === "活动作业" || subpage === "历史作业") {
      setStateFilter("ALL");
      setPage(1);
    }
  }, [subpage]);

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));
  const visibleJobs = (data?.items ?? []).filter((job) => pagePredicate(subpage, job));
  const capabilities = runtime?.capabilities ?? safeCapabilities;

  const openDetail = async (jobId: string) => {
    setDetailLoading(true);
    setActionError(null);
    try {
      setSelectedJob(await fetchJob(jobId));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "无法读取作业详情");
    } finally {
      setDetailLoading(false);
    }
  };

  const operateOnJob = async (operation: "cancel" | "clone") => {
    if (selectedJob === null) return;
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
      setNotice(operation === "cancel" ? `作业 #${job.slurm_job_id} 已取消` : `已克隆为新作业 #${job.slurm_job_id}`);
      setStateFilter("ALL");
      setPage(1);
      setReloadKey((value) => value + 1);
    } catch (reason) {
      setActionError(reason instanceof ApiError ? reason.message : "作业操作失败");
    } finally {
      setActionPending(null);
    }
  };

  if (subpage === "新建作业") {
    return (
      <div className="prototype-split prototype-jobs-live">
        <section className="prototype-panel prototype-panel--scroll prototype-live-form">
          {runtime === null && !runtimeError && <div className="prototype-live-loading">正在确认提交能力…</div>}
          {runtimeError && <div className="prototype-live-error" role="alert">无法读取运行时能力，已安全关闭提交。</div>}
          {runtime !== null && !capabilities.submit && (
            <div className="prototype-live-empty">
              <span>▣</span>
              <h2>当前部署未开放作业提交</h2>
              <p>{runtime.degraded ? "Native 查询已降级到 Fixture，所有写操作被强制关闭。" : "请检查 Native 提交能力开关和部署身份门禁。"}</p>
              <button className="prototype-secondary" type="button" onClick={() => onNavigate("作业总览")}>返回作业总览</button>
            </div>
          )}
          {runtime !== null && capabilities.submit && (
            <JobSubmitForm
              nativeMode={runtime.serving_source === "native"}
              onCancel={() => onNavigate("作业总览")}
              onSubmitted={(job) => {
                setNotice(runtime.serving_source === "native" ? `作业 #${job.slurm_job_id} 已提交到 Slurm` : `作业 #${job.slurm_job_id} 已加入 Fixture 队列`);
                setSelectedJob(job);
                setStateFilter("ALL");
                setPage(1);
                setReloadKey((value) => value + 1);
                onNavigate("作业总览");
              }}
            />
          )}
        </section>
        <aside className="prototype-panel prototype-side-stack">
          <div><span className="prototype-kicker">RUNTIME GATE</span><h2>运行时门禁</h2></div>
          <ul className="prototype-check-list">
            <li><StatusDot tone={runtime?.serving_source === "native" ? "green" : "orange"} /> 数据源：{runtimeLabel(runtime, runtimeError)}</li>
            <li><StatusDot tone={capabilities.submit ? "green" : "orange"} /> 提交：{capabilities.submit ? "已开放" : "已关闭"}</li>
            <li><StatusDot tone="green" /> 身份由后端 Unix UID 决定</li>
            <li><StatusDot tone="green" /> 幂等键由浏览器按请求生成</li>
          </ul>
          <div className="prototype-callout">资源与命令仍由后端重新校验；页面不会拼接或直接执行 Shell。</div>
        </aside>
      </div>
    );
  }

  return (
    <div className="prototype-split prototype-jobs-live">
      <section className="prototype-panel prototype-panel--flush">
        <div className="prototype-live-mode" role="status">
          <span className={runtime?.degraded || runtimeError ? "is-warning" : ""}><StatusDot tone={runtime?.degraded || runtimeError ? "orange" : "green"} />{runtimeLabel(runtime, runtimeError)}</span>
          <small>{runtime?.degraded ? "当前为脱敏 Fixture，写操作已关闭" : runtime?.serving_source === "native" ? "当前只展示本 Unix 账号的真实 Slurm 作业" : "本地开发数据，不会调用 Slurm"}</small>
        </div>
        <div className="prototype-toolbar prototype-live-toolbar">
          <label className="prototype-live-filter">
            <span>状态</span>
            <select value={stateFilter} onChange={(event) => { setStateFilter(event.target.value as JobState | "ALL"); setPage(1); setSelectedJob(null); }}>
              {stateOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <div className="prototype-live-sync">
            <span>{lastSyncedAt ? `同步于 ${lastSyncedAt.toLocaleTimeString("zh-CN", { hour12: false })}` : "等待首次同步"}</span>
            <button type="button" className="prototype-secondary" onClick={() => setAutoRefresh((value) => !value)}>{autoRefresh ? "暂停轮询" : "开启轮询"}</button>
            <button type="button" className="prototype-icon-button" aria-label="立即刷新" disabled={loading} onClick={() => setReloadKey((value) => value + 1)}>↻</button>
          </div>
        </div>
        {notice && <div className="prototype-live-notice" role="status"><span>{notice}</span><button type="button" onClick={() => setNotice(null)}>关闭</button></div>}
        {error && <div className="prototype-live-error" role="alert"><span>{error}</span><button type="button" onClick={() => setReloadKey((value) => value + 1)}>重试</button></div>}
        <div className="prototype-table-wrap">
          <table className="prototype-table prototype-live-table">
            <thead><tr><th>作业</th><th>状态</th><th>分区 / 节点</th><th>申请资源</th><th>更新时间</th><th /></tr></thead>
            <tbody>
              {loading && Array.from({ length: 4 }, (_, index) => <tr className="prototype-live-skeleton" key={index}><td colSpan={6}><span /></td></tr>)}
              {!loading && visibleJobs.map((job) => (
                <tr key={job.id} className={selectedJob?.id === job.id ? "is-selected" : ""}>
                  <td><strong>{job.name}</strong><small>Slurm #{job.slurm_job_id}</small></td>
                  <td><span className="prototype-state"><StatusDot tone={stateTone(job.state)} />{stateLabels[job.state]}</span></td>
                  <td>{job.partition ?? "—"}<small>{job.node ?? job.reason ?? "节点待分配"}</small></td>
                  <td>{job.resources.cpus ?? "—"} CPU · {job.resources.gpus ?? "—"} GPU<small>{formatMemory(job.resources.memory_mb)}</small></td>
                  <td>{formatDate(job.updated_at)}</td>
                  <td><button type="button" className="prototype-secondary prototype-view-button" disabled={detailLoading} onClick={() => void openDetail(job.id)}>查看</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && !error && visibleJobs.length === 0 && (
            <div className="prototype-live-empty prototype-live-empty--table"><span>▱</span><h2>没有符合条件的作业</h2><p>{subpage === "活动作业" ? "当前没有排队中或运行中的作业。" : subpage === "历史作业" ? "当前页没有终态历史作业。" : "切换筛选条件，或新建一个作业。"}</p></div>
          )}
        </div>
        <div className="prototype-table-footer"><span>API 共 {data?.total ?? 0} 项 · 当前显示 {visibleJobs.length} 项</span><div><button type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}>‹</button><b>{page} / {totalPages}</b><button type="button" disabled={page >= totalPages || loading} onClick={() => setPage((value) => value + 1)}>›</button></div></div>
      </section>
      <aside className="prototype-side-stack prototype-live-side">
        {selectedJob ? (
          <JobDetail
            job={selectedJob}
            capabilities={capabilities}
            actionPending={actionPending}
            actionError={actionError}
            onCancelJob={() => void operateOnJob("cancel")}
            onCloneJob={() => void operateOnJob("clone")}
            onClose={() => { setSelectedJob(null); setActionError(null); }}
          />
        ) : (
          <>
            <section className="prototype-panel prototype-live-summary"><JobSummaryPanel refreshKey={reloadKey} /></section>
            <section className="prototype-panel prototype-grow">
              <span className="prototype-kicker">CAPABILITIES</span><h2>可用操作</h2>
              <dl className="prototype-details">
                <div><dt>提交</dt><dd>{capabilities.submit ? "已开放" : "关闭"}</dd></div>
                <div><dt>日志</dt><dd>{capabilities.logs ? "已开放" : "关闭"}</dd></div>
                <div><dt>取消</dt><dd>{capabilities.cancel ? "已开放" : "关闭"}</dd></div>
                <div><dt>克隆</dt><dd>{capabilities.clone ? "已开放" : "关闭"}</dd></div>
              </dl>
              <button className="prototype-primary prototype-bottom-button" type="button" disabled={!capabilities.submit} onClick={() => onNavigate("新建作业")}>＋ 新建作业</button>
            </section>
          </>
        )}
      </aside>
    </div>
  );
}
