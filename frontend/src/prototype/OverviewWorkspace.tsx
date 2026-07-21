import { type CSSProperties, useEffect, useMemo, useState } from "react";

import { fetchClusterResourceOverview, fetchJobs, fetchJobSummary, fetchRuntimeInfo } from "../api/jobs";
import { fetchAiCalls, fetchAiProviders, fetchReports } from "../api/product";
import { fetchRepositories } from "../api/repositories";
import type { ClusterResourceOverview, Job, RuntimeInfo, UserJobSummary } from "../features/jobs/types";
import type { AiCallRecord, AiProvider, DiagnosticReport } from "../features/product/types";
import type { GitRepositorySummary } from "../features/repositories/types";

type OverviewDestination =
  | { module: "jobs"; item: string }
  | { module: "reports"; item: string }
  | { module: "repositories"; item: string }
  | { module: "ai"; item: string };

type OverviewData = {
  runtime: RuntimeInfo | null;
  summary: UserJobSummary | null;
  jobs: Job[];
  reports: DiagnosticReport[];
  repositories: GitRepositorySummary[];
  providers: AiProvider[];
  calls: AiCallRecord[];
  resources: ClusterResourceOverview | null;
};

const emptyData: OverviewData = {
  runtime: null,
  summary: null,
  jobs: [],
  reports: [],
  repositories: [],
  providers: [],
  calls: [],
  resources: null,
};

function formatTime(value: string | null | undefined): string {
  if (!value) return "暂无记录";
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function OverviewWorkspace({ onNavigate }: { onNavigate: (destination: OverviewDestination) => void }) {
  const [data, setData] = useState<OverviewData>(emptyData);
  const [loading, setLoading] = useState(true);
  const [failedSources, setFailedSources] = useState<string[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    const requests = [
      fetchRuntimeInfo(controller.signal),
      fetchJobSummary(controller.signal),
      Promise.all([
        fetchJobs(1, 3, "RUNNING", controller.signal),
        fetchJobs(1, 3, "PENDING", controller.signal),
      ]),
      fetchReports(controller.signal),
      fetchRepositories(controller.signal),
      fetchAiProviders(controller.signal),
      fetchAiCalls(controller.signal),
      fetchClusterResourceOverview(controller.signal),
    ] as const;

    Promise.allSettled(requests).then((results) => {
      if (controller.signal.aborted) return;
      const failed: string[] = [];
      const value = <T,>(index: number, label: string): T | null => {
        const result = results[index];
        if (result.status === "fulfilled") return result.value as T;
        failed.push(label);
        return null;
      };
      const runtime = value<RuntimeInfo>(0, "运行时");
      const summary = value<UserJobSummary>(1, "作业摘要");
      const jobs = value<[Awaited<ReturnType<typeof fetchJobs>>, Awaited<ReturnType<typeof fetchJobs>>]>(2, "活动作业");
      const reports = value<DiagnosticReport[]>(3, "诊断报告");
      const repositories = value<Awaited<ReturnType<typeof fetchRepositories>>>(4, "Git 仓库");
      const providers = value<AiProvider[]>(5, "AI Provider");
      const calls = value<AiCallRecord[]>(6, "AI 调用记录");
      const resources = value<ClusterResourceOverview>(7, "集群资源");
      setData({
        runtime,
        summary,
        jobs: jobs ? [...jobs[0].items, ...jobs[1].items] : [],
        reports: reports ?? [],
        repositories: repositories?.items ?? [],
        providers: providers ?? [],
        calls: calls ?? [],
        resources,
      });
      setFailedSources(failed);
      setLoading(false);
    });
    return () => controller.abort();
  }, []);

  const activeJobs = useMemo(
    () => data.jobs.filter((job) => job.state === "PENDING" || job.state === "RUNNING").slice(0, 3),
    [data.jobs],
  );
  const urgentReports = useMemo(
    () => data.reports.filter((report) => report.findings.some((finding) => finding.severity !== "info")).sort((a, b) => a.health_score - b.health_score).slice(0, 3),
    [data.reports],
  );
  const dirtyRepositories = data.repositories.filter((repository) => repository.dirty);
  const configuredProviders = data.providers.filter((provider) => provider.configured);
  const degraded = data.runtime?.degraded || failedSources.length > 0;
  const sourceFailed = (label: string) => failedSources.includes(label);
  const primaryPartition = data.resources?.partitions.find(
    (partition) => partition.name === data.resources?.primary_partition,
  ) ?? null;

  return (
    <div className={`prototype-overview${failedSources.length > 0 ? " has-warning" : ""}`}>
      {failedSources.length > 0 && (
        <div className="prototype-live-error" role="alert">部分数据暂不可用：{failedSources.join("、")}</div>
      )}

      <section className="prototype-overview-status" aria-label="核心状态">
        <button type="button" onClick={() => onNavigate({ module: "jobs", item: "活动作业" })}>
          <span>活动作业</span><strong>{loading ? "…" : data.summary?.active_jobs ?? "—"}</strong><small>运行中与排队中</small>
        </button>
        <button type="button" onClick={() => onNavigate({ module: "reports", item: "报告总览" })}>
          <span>异常作业</span><strong>{loading ? "…" : data.summary?.unsuccessful_jobs ?? "—"}</strong><small>失败、超时或取消</small>
        </button>
        <button type="button" onClick={() => onNavigate({ module: "repositories", item: "仓库浏览" })}>
          <span>脏工作区</span><strong>{loading ? "…" : sourceFailed("Git 仓库") ? "—" : dirtyRepositories.length}</strong><small>{sourceFailed("Git 仓库") ? "仓库状态不可用" : data.repositories.length > 0 ? `共 ${data.repositories.length} 个可见仓库` : "当前没有可见仓库"}</small>
        </button>
        <button type="button" onClick={() => onNavigate({ module: "ai", item: "接入设置" })}>
          <span>AI Provider</span><strong>{loading ? "…" : sourceFailed("AI Provider") ? "—" : configuredProviders.length}</strong><small>{sourceFailed("AI Provider") ? "连接状态不可用" : configuredProviders.length > 0 ? "已配置可用连接" : "尚无可用连接"}</small>
        </button>
      </section>

      <div className="prototype-overview-grid">
        <section className="prototype-panel prototype-resource-overview">
          <div className="prototype-panel-heading">
            <div><span className="prototype-kicker">SLURM CAPACITY</span><h2>CPU 与分区占用</h2></div>
            <span className="prototype-resource-time">{formatTime(data.resources?.updated_at)}</span>
          </div>
          {loading ? (
            <div className="prototype-overview-placeholder">正在读取 Slurm 分区资源…</div>
          ) : sourceFailed("集群资源") ? (
            <p className="prototype-repository-empty">集群资源暂时不可用。</p>
          ) : primaryPartition ? (
            <div className="prototype-resource-layout">
              <div className="prototype-cpu-donut-wrap">
                <div
                  className="prototype-cpu-donut"
                  style={{ "--cpu-usage": `${primaryPartition.utilization_percent * 3.6}deg` } as CSSProperties}
                  aria-label={`${primaryPartition.name} CPU 占用 ${primaryPartition.utilization_percent}%`}
                >
                  <span><strong>{primaryPartition.utilization_percent}%</strong><small>已分配</small></span>
                </div>
                <div><strong>{primaryPartition.name}</strong><small>{primaryPartition.allocated_cpus} / {primaryPartition.total_cpus} 核</small></div>
              </div>
              <div className="prototype-partition-list">
                {data.resources?.partitions.map((partition) => (
                  <div className="prototype-partition-row" key={partition.name}>
                    <span><strong>{partition.name}</strong><small>{partition.allocated_cpus} 已分配 · {partition.idle_cpus} 空闲</small></span>
                    <div><i style={{ width: `${partition.utilization_percent}%` }} /></div>
                    <b>{partition.utilization_percent}%</b>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="prototype-repository-empty">当前没有可展示的 Slurm 分区。</p>
          )}
        </section>

        <section className="prototype-panel prototype-panel--scroll prototype-overview-primary">
          <div className="prototype-panel-heading"><div><span className="prototype-kicker">LIVE JOBS</span><h2>当前活动</h2></div><button className="prototype-overview-link" type="button" onClick={() => onNavigate({ module: "jobs", item: "活动作业" })}>查看全部</button></div>
          {activeJobs.map((job) => (
            <button className="prototype-overview-row" type="button" key={job.id} onClick={() => onNavigate({ module: "jobs", item: "活动作业" })}>
              <span className={`prototype-overview-state is-${job.state.toLowerCase()}`}>{job.state === "RUNNING" ? "运行中" : "排队中"}</span>
              <span><strong>{job.name}</strong><small>Slurm #{job.slurm_job_id} · {job.partition ?? "分区待定"}</small></span>
              <time dateTime={job.updated_at}>{formatTime(job.updated_at)}</time>
            </button>
          ))}
          {loading && <div className="prototype-overview-placeholder">正在读取活动作业…</div>}
          {!loading && sourceFailed("活动作业") && <p className="prototype-repository-empty">活动作业暂时不可用。</p>}
          {!loading && !sourceFailed("活动作业") && activeJobs.length === 0 && <p className="prototype-repository-empty">当前没有运行中或排队中的作业。</p>}
        </section>

        <section className="prototype-panel prototype-panel--scroll">
          <div className="prototype-panel-heading"><div><span className="prototype-kicker">ATTENTION</span><h2>需要关注</h2></div><button className="prototype-overview-link" type="button" onClick={() => onNavigate({ module: "reports", item: "报告总览" })}>查看报告</button></div>
          {urgentReports.map((report) => (
            <button className="prototype-overview-row" type="button" key={report.job_id} onClick={() => onNavigate({ module: "reports", item: "报告总览" })}>
              <span className="prototype-overview-score">{report.health_score}</span>
              <span><strong>{report.job_name}</strong><small>{report.summary}</small></span>
            </button>
          ))}
          {loading && <div className="prototype-overview-placeholder">正在检查诊断报告…</div>}
          {!loading && sourceFailed("诊断报告") && <p className="prototype-repository-empty">诊断报告暂时不可用。</p>}
          {!loading && !sourceFailed("诊断报告") && urgentReports.length === 0 && <p className="prototype-repository-empty">当前没有需要关注的诊断异常。</p>}
        </section>

        <section className="prototype-panel prototype-panel--scroll">
          <div className="prototype-panel-heading"><div><span className="prototype-kicker">SOURCE CONTROL</span><h2>仓库动态</h2></div><button className="prototype-overview-link" type="button" onClick={() => onNavigate({ module: "repositories", item: "仓库浏览" })}>打开仓库</button></div>
          {data.repositories.slice(0, 4).map((repository) => (
            <button className="prototype-overview-row" type="button" key={repository.id} onClick={() => onNavigate({ module: "repositories", item: "仓库浏览" })}>
              <span className={repository.dirty ? "prototype-overview-state is-warning" : "prototype-overview-state is-clean"}>{repository.dirty ? `${repository.changed_files} 变更` : "干净"}</span>
              <span><strong>{repository.name}</strong><small>{repository.branch} · {formatTime(repository.last_commit_at)}</small></span>
            </button>
          ))}
          {loading && <div className="prototype-overview-placeholder">正在读取仓库状态…</div>}
          {!loading && sourceFailed("Git 仓库") && <p className="prototype-repository-empty">仓库状态暂时不可用。</p>}
          {!loading && !sourceFailed("Git 仓库") && data.repositories.length === 0 && <p className="prototype-repository-empty">当前没有可见 Git 仓库。</p>}
        </section>

        <section className="prototype-panel prototype-panel--scroll">
          <div className="prototype-panel-heading"><div><span className="prototype-kicker">SYSTEM</span><h2>服务状态</h2></div><span className={degraded ? "prototype-badge prototype-badge--orange" : "prototype-badge"}>{degraded ? "部分降级" : "正常"}</span></div>
          <dl className="prototype-overview-services">
            <div><dt>107 / Slurm</dt><dd>{data.runtime ? (data.runtime.degraded ? "Fixture 回退" : data.runtime.serving_source === "native" ? "Native 已连接" : "开发数据") : "状态未知"}</dd></div>
            <div><dt>Git</dt><dd>{sourceFailed("Git 仓库") ? "状态不可用" : data.repositories.length > 0 ? `${data.repositories.length} 个仓库可读` : "无可见仓库"}</dd></div>
            <div><dt>AI</dt><dd>{sourceFailed("AI Provider") ? "状态不可用" : configuredProviders.length > 0 ? `${configuredProviders.length} 个 Provider 可用` : "尚未配置"}</dd></div>
            <div><dt>最近 AI 调用</dt><dd>{sourceFailed("AI 调用记录") ? "状态不可用" : formatTime(data.calls[0]?.created_at)}</dd></div>
            <div><dt>数据同步</dt><dd>{formatTime(data.summary?.updated_at)}</dd></div>
          </dl>
        </section>
      </div>
    </div>
  );
}
