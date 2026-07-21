import { type FormEvent, useEffect, useState } from "react";

import { fetchJobs } from "../api/jobs";
import {
  createEvaluationProject,
  fetchAiCalls,
  fetchAiProviders,
  fetchEvaluationProjects,
  fetchPromptTemplates,
  fetchReports,
  saveAiProvider,
  sendAiChat,
} from "../api/product";
import type { Job } from "../features/jobs/types";
import type {
  AiCallRecord,
  AiProvider,
  DiagnosticReport,
  EvaluationProject,
  PromptTemplate,
} from "../features/product/types";

function message(reason: unknown): string {
  return reason instanceof Error ? reason.message : "请求失败";
}

export function ReportsWorkspace() {
  const [items, setItems] = useState<DiagnosticReport[]>([]);
  const [selected, setSelected] = useState<DiagnosticReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchReports(controller.signal)
      .then((reports) => {
        setItems(reports);
        setSelected(reports[0] ?? null);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(message(reason));
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="prototype-split">
      <section className="prototype-panel prototype-panel--scroll">
        <div className="prototype-panel-heading">
          <div>
            <span className="prototype-kicker">RULES V1</span>
            <h2>确定性诊断报告</h2>
          </div>
          <span className="prototype-badge">LIVE API</span>
        </div>
        {error && <div className="prototype-live-error">{error}</div>}
        <div className="prototype-report-list">
          {items.map((report) => (
            <button
              type="button"
              key={report.job_id}
              className={selected?.job_id === report.job_id ? "is-selected" : ""}
              onClick={() => setSelected(report)}
            >
              <div>
                <strong>{report.job_name}</strong>
                <small>
                  Slurm #{report.slurm_job_id} · {report.state}
                </small>
              </div>
              <b>{report.health_score}</b>
            </button>
          ))}
        </div>
        {!error && items.length === 0 && (
          <div className="prototype-live-empty"><h2>暂无可诊断作业</h2></div>
        )}
      </section>

      <aside className="prototype-panel prototype-panel--scroll">
        {selected ? (
          <>
            <span className="prototype-kicker">EVIDENCE REPORT</span>
            <h2>{selected.summary}</h2>
            <div className="prototype-score-line">
              <strong>{selected.health_score}</strong><span>/100</span>
            </div>
            <h3>事实证据</h3>
            <dl className="prototype-details">
              {selected.evidence.map((entry) => (
                <div key={entry.key}>
                  <dt>{entry.label}<small>{entry.source}</small></dt>
                  <dd>{entry.value}</dd>
                </div>
              ))}
            </dl>
            <h3>诊断发现</h3>
            {selected.findings.map((finding) => (
              <div
                className={`prototype-real-finding is-${finding.severity}`}
                key={`${finding.title}-${finding.explanation}`}
              >
                <strong>{finding.title}</strong>
                <p>{finding.explanation}</p>
                <small>{finding.recommendation}</small>
              </div>
            ))}
          </>
        ) : (
          <div className="prototype-live-empty"><h2>选择一份报告</h2></div>
        )}
      </aside>
    </div>
  );
}

export function ProjectsWorkspace() {
  const [projects, setProjects] = useState<EvaluationProject[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const reloadProjects = async () => setProjects(await fetchEvaluationProjects());

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchEvaluationProjects(controller.signal),
      fetchJobs(1, 100, "ALL", controller.signal),
    ])
      .then(([projectItems, jobPage]) => {
        setProjects(projectItems);
        setJobs(jobPage.items);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(message(reason));
      });
    return () => controller.abort();
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await createEvaluationProject({ name, description, job_ids: selectedIds });
      setName("");
      setDescription("");
      setSelectedIds([]);
      await reloadProjects();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="prototype-split">
      <section className="prototype-panel prototype-panel--scroll">
        <div className="prototype-panel-heading">
          <div>
            <span className="prototype-kicker">PROJECT EVALUATION</span>
            <h2>项目与实验作业</h2>
          </div>
          <span className="prototype-badge">LIVE API</span>
        </div>
        {error && <div className="prototype-live-error">{error}</div>}
        <form className="prototype-project-form" onSubmit={(event) => void submit(event)}>
          <input
            required
            maxLength={64}
            placeholder="项目名称"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <textarea
            maxLength={500}
            placeholder="项目说明（可选）"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <div>
            {jobs.map((job) => (
              <label key={job.id}>
                <input
                  type="checkbox"
                  checked={selectedIds.includes(job.id)}
                  onChange={() => setSelectedIds((current) =>
                    current.includes(job.id)
                      ? current.filter((id) => id !== job.id)
                      : [...current, job.id]
                  )}
                />
                <span>{job.name}</span>
                <small>#{job.slurm_job_id} · {job.state}</small>
              </label>
            ))}
          </div>
          <button
            className="prototype-primary"
            type="submit"
            disabled={saving || !name || selectedIds.length === 0}
          >
            {saving ? "评价中…" : "创建并评价"}
          </button>
        </form>
      </section>

      <aside className="prototype-panel prototype-panel--scroll">
        <span className="prototype-kicker">EVALUATION RESULTS</span>
        <h2>评价结果</h2>
        {projects.map((project) => (
          <article className="prototype-evaluation-card" key={project.id}>
            <div><strong>{project.name}</strong><b>{project.grade}</b></div>
            <p>{project.summary}</p>
            <span>综合 {project.score}/100 · 证据覆盖 {project.evidence_coverage_percent}%</span>
            <ul>{project.recommendations.map((item) => <li key={item}>{item}</li>)}</ul>
          </article>
        ))}
        {projects.length === 0 && (
          <div className="prototype-live-empty"><h2>尚未创建评价项目</h2></div>
        )}
      </aside>
    </div>
  );
}

export function AiWorkspace({ subpage }: { subpage: string }) {
  const [providers, setProviders] = useState<AiProvider[]>([]);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [calls, setCalls] = useState<AiCallRecord[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [providerForm, setProviderForm] = useState({
    id: "school",
    name: "学校 AI 服务",
    base_url: "https://ai.example.edu/v1",
    model: "school-chat-pro",
    api_key: "",
  });
  const [chat, setChat] = useState({ provider_id: "school", message: "" });

  const reload = async () => {
    const [providerItems, templateItems, callItems] = await Promise.all([
      fetchAiProviders(),
      fetchPromptTemplates(),
      fetchAiCalls(),
    ]);
    setProviders(providerItems);
    setTemplates(templateItems);
    setCalls(callItems);
    if (providerItems.length > 0 && !providerItems.some((item) => item.id === chat.provider_id)) {
      setChat((current) => ({ ...current, provider_id: providerItems[0].id }));
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchAiProviders(controller.signal),
      fetchPromptTemplates(controller.signal),
      fetchAiCalls(controller.signal),
      fetchJobs(1, 20, "ALL", controller.signal),
    ])
      .then(([providerItems, templateItems, callItems, jobPage]) => {
        setProviders(providerItems);
        setTemplates(templateItems);
        setCalls(callItems);
        setJobs(jobPage.items);
        if (providerItems[0]) {
          setChat((current) => ({ ...current, provider_id: providerItems[0].id }));
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(message(reason));
      });
    return () => controller.abort();
  }, []);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await saveAiProvider(providerForm.id, {
        name: providerForm.name,
        base_url: providerForm.base_url,
        model: providerForm.model,
        ...(providerForm.api_key ? { api_key: providerForm.api_key } : {}),
      });
      setProviderForm((current) => ({ ...current, api_key: "" }));
      await reload();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setAnswer("");
    setBusy(true);
    try {
      const response = await sendAiChat({ ...chat, job_ids: selectedJobIds });
      setAnswer(response.answer);
      setChat((current) => ({ ...current, message: "" }));
      await reload();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const heading = (
    <div className="prototype-panel-heading">
      <div><span className="prototype-kicker">AI WORKSPACE</span><h2>{subpage}</h2></div>
      <span className="prototype-badge">LIVE API</span>
    </div>
  );

  if (subpage === "调用记录") {
    return (
      <section className="prototype-panel prototype-panel--scroll">
        {heading}
        <table className="prototype-table">
          <thead><tr><th>时间</th><th>Provider</th><th>模型</th><th>状态</th><th>请求</th></tr></thead>
          <tbody>{calls.map((call) => (
            <tr key={call.id}>
              <td>{new Date(call.created_at).toLocaleString()}</td>
              <td>{call.provider_id}</td><td>{call.model}</td><td>{call.status}</td>
              <td>{call.prompt_preview}</td>
            </tr>
          ))}</tbody>
        </table>
      </section>
    );
  }

  if (subpage === "提示词模板") {
    return (
      <section className="prototype-panel prototype-panel--scroll">
        {heading}
        <div className="prototype-template-grid">{templates.map((item) => (
          <article key={item.id}>
            <span>SYSTEM</span><h3>{item.name}</h3><p>{item.description}</p>
            <small>{item.system_prompt}</small>
          </article>
        ))}</div>
      </section>
    );
  }

  if (subpage === "模型接入" || subpage === "API Keys") {
    return (
      <div className="prototype-split">
        <section className="prototype-panel prototype-panel--scroll">
          {heading}
          {error && <div className="prototype-live-error">{error}</div>}
          <form className="prototype-form" onSubmit={(event) => void save(event)}>
            <label><span>Provider ID</span><input required pattern="[A-Za-z0-9_-]+" maxLength={64} value={providerForm.id} onChange={(event) => setProviderForm({ ...providerForm, id: event.target.value })} /></label>
            <label><span>名称</span><input required maxLength={64} value={providerForm.name} onChange={(event) => setProviderForm({ ...providerForm, name: event.target.value })} /></label>
            <label className="prototype-form-wide"><span>Base URL（HTTPS）</span><input required type="url" value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} /></label>
            <label><span>模型</span><input required value={providerForm.model} onChange={(event) => setProviderForm({ ...providerForm, model: event.target.value })} /></label>
            <label><span>API Key</span><input type="password" minLength={8} autoComplete="new-password" placeholder="保存后不可回读" value={providerForm.api_key} onChange={(event) => setProviderForm({ ...providerForm, api_key: event.target.value })} /></label>
            <button className="prototype-primary" type="submit" disabled={busy}>{busy ? "保存中…" : "安全保存"}</button>
          </form>
        </section>
        <aside className="prototype-panel prototype-panel--scroll">
          <span className="prototype-kicker">CONFIGURED</span><h2>已配置 Provider</h2>
          {providers.map((provider) => (
            <div className="prototype-key-card" key={provider.id}>
              <div className="prototype-provider-logo">AI</div>
              <div><strong>{provider.name}</strong><span>{provider.model}</span></div>
              <code>{provider.key_hint ?? "未配置密钥"}</code>
              <span>{provider.configured ? "可用" : "缺少密钥"}</span>
            </div>
          ))}
        </aside>
      </div>
    );
  }

  return (
    <div className="prototype-split">
      <section className="prototype-panel prototype-chat">
        {heading}
        <div className="prototype-chat-body">
          {answer ? <div className="prototype-ai-answer">{answer}</div> : (
            <div className="prototype-chat-empty">
              <span>✦</span><h3>只读作业分析助手</h3>
              <p>回答来自配置的 OpenAI 兼容 Provider；AI 不具备作业控制权限。</p>
            </div>
          )}
        </div>
        {error && <div className="prototype-live-error">{error}</div>}
        <form className="prototype-composer" onSubmit={(event) => void send(event)}>
          <select value={chat.provider_id} onChange={(event) => setChat({ ...chat, provider_id: event.target.value })}>
            {providers.length === 0 && <option value="school">请先配置 Provider</option>}
            {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
          </select>
          <input required placeholder="输入问题…" value={chat.message} onChange={(event) => setChat({ ...chat, message: event.target.value })} />
          <button type="submit" disabled={busy || providers.length === 0}>{busy ? "…" : "↑"}</button>
        </form>
      </section>
      <aside className="prototype-panel prototype-panel--scroll">
        <span className="prototype-kicker">EVIDENCE CONTEXT</span><h2>选择作业证据</h2>
        <div className="prototype-ai-job-list">
          {jobs.map((job) => (
            <label key={job.id}>
              <input
                type="checkbox"
                checked={selectedJobIds.includes(job.id)}
                onChange={() => setSelectedJobIds((current) =>
                  current.includes(job.id)
                    ? current.filter((id) => id !== job.id)
                    : [...current, job.id]
                )}
              />
              <span>{job.name}</span><small>#{job.slurm_job_id} · {job.state}</small>
            </label>
          ))}
        </div>
        <h3>只读边界</h3>
        <ul className="prototype-check-list">
          <li>AI 仅接收勾选作业的结构化报告</li>
          <li>无法提交、取消或克隆作业</li>
          <li>密钥原文不会返回浏览器</li>
          <li>调用成功或失败均进入审计记录</li>
        </ul>
      </aside>
    </div>
  );
}
