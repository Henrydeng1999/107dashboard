import { type FormEvent, useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { fetchJobs } from "../api/jobs";
import { fetchRepositories } from "../api/repositories";
import {
  addAiProviderModel,
  createEvaluationProject,
  createPromptTemplate,
  deletePromptTemplate,
  deleteAiProviderModel,
  fetchAiCalls,
  fetchAiProviderModels,
  fetchAiProviders,
  fetchAiSession,
  fetchAiSessions,
  fetchEvaluationProjects,
  fetchPromptTemplates,
  fetchReports,
  saveAiProvider,
  sendAiChat,
  setDefaultAiProviderModel,
  testAiProvider,
  testAiProviderModel,
  updatePromptTemplate,
  resetPromptTemplate,
} from "../api/product";
import type { Job } from "../features/jobs/types";
import type { GitRepositorySummary } from "../features/repositories/types";
import type {
  AiCallRecord,
  AiChatMessage,
  AiChatSession,
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
          <label className="prototype-project-field"><span>项目名称</span><input
            required
            maxLength={64}
            placeholder="例如：H200 参数对比"
            value={name}
            onChange={(event) => setName(event.target.value)}
          /></label>
          <label className="prototype-project-field"><span>项目说明（可选）</span><textarea
            maxLength={500}
            placeholder="记录实验目标和比较口径"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          /></label>
          <p className="prototype-field-hint">至少选择一个作业，评价将依据现有诊断事实生成。</p>
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
  const schoolPreset = {
    id: "school",
    name: "学校 AI 服务",
    base_url: "https://api.llm.ustc.edu.cn",
    model: "deepseek-v4-pro",
    api_key: "",
  };
  const [providers, setProviders] = useState<AiProvider[]>([]);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [calls, setCalls] = useState<AiCallRecord[]>([]);
  const [sessions, setSessions] = useState<AiChatSession[]>([]);
  const [messages, setMessages] = useState<AiChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [repositories, setRepositories] = useState<GitRepositorySummary[]>([]);
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
  const [selectedRepositoryIds, setSelectedRepositoryIds] = useState<string[]>([]);
  const [templateDrafts, setTemplateDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [chatStartedAt, setChatStartedAt] = useState<number | null>(null);
  const [chatWaitSeconds, setChatWaitSeconds] = useState(0);
  const [providerTest, setProviderTest] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [providerForm, setProviderForm] = useState(schoolPreset);
  const [chat, setChat] = useState({ provider_id: "school", model: "deepseek-v4-pro", message: "", template_id: "job-diagnosis" as string | null });
  const [newTemplate, setNewTemplate] = useState({ id: "", name: "", description: "", system_prompt: "" });
  const suggestions = [
    "总结这个作业的异常发现",
    "对比这两个作业的资源效率",
    "分析作业失败的可能原因",
    "提取作业中的关键指标",
  ];

  const reload = async () => {
    const [providerItems, templateItems, callItems, sessionItems] = await Promise.all([
      fetchAiProviders(),
      fetchPromptTemplates(),
      fetchAiCalls(),
      fetchAiSessions(),
    ]);
    setProviders(providerItems);
    setTemplates(templateItems);
    setTemplateDrafts(Object.fromEntries(templateItems.map((item) => [item.id, item.system_prompt])));
    setCalls(callItems);
    setSessions(sessionItems);
    const selected = providerItems.find((item) => item.id === chat.provider_id);
    if (providerItems[0] && (!selected || !selected.models.includes(chat.model))) {
      setChat((current) => ({
        ...current,
        provider_id: providerItems[0].id,
        model: providerItems[0].model,
      }));
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchAiProviders(controller.signal),
      fetchPromptTemplates(controller.signal),
      fetchAiCalls(controller.signal),
      fetchJobs(1, 20, "ALL", controller.signal),
      fetchRepositories(controller.signal),
      fetchAiSessions(controller.signal),
    ])
      .then(([providerItems, templateItems, callItems, jobPage, repositoryPage, sessionItems]) => {
        setProviders(providerItems);
        setTemplates(templateItems);
        setCalls(callItems);
        setJobs(jobPage.items);
        setRepositories(repositoryPage.items);
        setSessions(sessionItems);
        setTemplateDrafts(Object.fromEntries(templateItems.map((item) => [item.id, item.system_prompt])));
        if (providerItems[0]) {
          setChat((current) => ({
            ...current,
            provider_id: providerItems[0].id,
            model: providerItems[0].model,
          }));
          setProviderForm((current) => ({
            ...current,
            id: providerItems[0].id,
            name: providerItems[0].name,
            base_url: providerItems[0].base_url,
            model: providerItems[0].model,
            api_key: "",
          }));
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(message(reason));
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (chatStartedAt === null) {
      setChatWaitSeconds(0);
      return;
    }
    const update = () => setChatWaitSeconds(Math.floor((Date.now() - chatStartedAt) / 1000));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [chatStartedAt]);

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
    const question = chat.message.trim();
    if (!question) return;
    setError(null);
    const optimisticUser: AiChatMessage = { id: `pending-${Date.now()}`, role: "USER", content: question, evidence_job_ids: selectedJobIds, evidence_repository_ids: selectedRepositoryIds, template_id: chat.template_id, created_at: new Date().toISOString() };
    setMessages((current) => [...current, optimisticUser]);
    setChat((current) => ({ ...current, message: "" }));
    setBusy(true);
    setChatStartedAt(Date.now());
    try {
      const response = await sendAiChat({ ...chat, message: question, job_ids: selectedJobIds, repository_ids: selectedRepositoryIds, session_id: sessionId });
      setSessionId(response.session_id);
      const stored = await fetchAiSession(response.session_id);
      setMessages(stored.messages);
      await reload();
    } catch (reason) {
      setMessages((current) => current.filter((item) => item.id !== optimisticUser.id));
      setError(message(reason));
    } finally {
      setChatStartedAt(null);
      setBusy(false);
    }
  };

  const openSession = async (id: string) => {
    setError(null);
    try {
      const selected = await fetchAiSession(id);
      setSessionId(id);
      setMessages(selected.messages);
      setChat((current) => ({ ...current, provider_id: selected.provider_id, model: selected.model }));
    } catch (reason) { setError(message(reason)); }
  };

  const startSession = () => { setSessionId(null); setMessages([]); setError(null); };

  const testProvider = async () => {
    setError(null);
    setProviderTest(null);
    setBusy(true);
    try {
      const result = await testAiProvider(providerForm.id);
      if (result.reachable && result.authenticated && !result.error) {
        setProviderTest(`连接成功 · ${result.model ?? providerForm.model} · ${result.latency_ms ?? 0} ms`);
      } else {
        setProviderTest(result.error ?? "连接测试未通过");
      }
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const discoverModels = async () => {
    setError(null);
    setProviderTest(null);
    setBusy(true);
    try {
      const result = await fetchAiProviderModels(providerForm.id);
      setAvailableModels(result.models);
      setProviderTest(`已获取 ${result.count} 个模型 · 接口与密钥正常 · ${result.latency_ms} ms`);
      if (!result.models.includes(providerForm.model) && result.models[0]) {
        setProviderForm((current) => ({ ...current, model: result.models[0] }));
      }
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const testSelectedModel = async () => {
    setError(null);
    setProviderTest(null);
    setBusy(true);
    try {
      const result = await testAiProviderModel(providerForm.id, providerForm.model);
      if (result.reachable && result.authenticated && !result.error) {
        setProviderTest(`模型可用 · ${result.model ?? providerForm.model} · ${result.latency_ms ?? 0} ms`);
      } else {
        setProviderTest(result.error ?? "模型测试未通过");
      }
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const addModel = async (model: string) => {
    setError(null);
    setBusy(true);
    try {
      await addAiProviderModel(providerForm.id, model);
      setProviderTest(`已添加模型 · ${model}`);
      await reload();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const setDefaultModel = async (providerId: string, model: string) => {
    setError(null);
    setBusy(true);
    try {
      await setDefaultAiProviderModel(providerId, model);
      setProviderTest(`已设为默认模型 · ${model}`);
      setProviderForm((current) => current.id === providerId ? { ...current, model } : current);
      await reload();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const removeModel = async (provider: AiProvider, model: string) => {
    if (!window.confirm(`从 ${provider.name} 中删除模型 ${model}？`)) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await deleteAiProviderModel(provider.id, model);
      setProviderTest(`已删除模型 · ${model}`);
      if (providerForm.id === provider.id) {
        setProviderForm((current) => ({ ...current, model: updated.model }));
      }
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

  if (subpage === "内置提示词") {
    const saveTemplate = async (template: PromptTemplate) => {
      setBusy(true); setError(null);
      try { await updatePromptTemplate(template.id, templateDrafts[template.id] ?? template.system_prompt); await reload(); }
      catch (reason) { setError(message(reason)); } finally { setBusy(false); }
    };
    const restoreTemplate = async (template: PromptTemplate) => {
      setBusy(true); setError(null);
      try { const restored = await resetPromptTemplate(template.id); setTemplateDrafts((current) => ({ ...current, [template.id]: restored.system_prompt })); await reload(); }
      catch (reason) { setError(message(reason)); } finally { setBusy(false); }
    };
    const addTemplate = async (event: FormEvent) => {
      event.preventDefault(); setBusy(true); setError(null);
      try { await createPromptTemplate(newTemplate); setNewTemplate({ id: "", name: "", description: "", system_prompt: "" }); await reload(); }
      catch (reason) { setError(message(reason)); } finally { setBusy(false); }
    };
    const removeTemplate = async (template: PromptTemplate) => {
      if (!window.confirm(`删除自定义提示词“${template.name}”？`)) return;
      setBusy(true); setError(null);
      try { await deletePromptTemplate(template.id); await reload(); }
      catch (reason) { setError(message(reason)); } finally { setBusy(false); }
    };
    return (
      <section className="prototype-panel prototype-panel--scroll">
        {heading}
        {error && <div className="prototype-live-error">{error}</div>}
        <details className="prototype-collapsible" open>
          <summary><span>新增自定义提示词</span><small>只调整分析侧重点</small></summary>
          <form className="prototype-custom-template-form" onSubmit={(event) => void addTemplate(event)}>
            <label><span>ID</span><input required pattern="[A-Za-z0-9_-]+" maxLength={64} value={newTemplate.id} onChange={(event) => setNewTemplate({ ...newTemplate, id: event.target.value })} /></label>
            <label><span>名称</span><input required maxLength={64} value={newTemplate.name} onChange={(event) => setNewTemplate({ ...newTemplate, name: event.target.value })} /></label>
            <label className="prototype-form-wide"><span>说明</span><input maxLength={240} value={newTemplate.description} onChange={(event) => setNewTemplate({ ...newTemplate, description: event.target.value })} /></label>
            <label className="prototype-form-wide"><span>提示词</span><textarea required maxLength={4000} value={newTemplate.system_prompt} onChange={(event) => setNewTemplate({ ...newTemplate, system_prompt: event.target.value })} /></label>
            <button className="prototype-primary" type="submit" disabled={busy}>新增提示词</button>
          </form>
        </details>
        <div className="prototype-template-grid">{templates.map((item) => (
          <article key={item.id}>
            <span>{item.builtin ? (item.customized ? "OVERRIDE" : "SYSTEM") : "CUSTOM"}</span><h3>{item.name}</h3><p>{item.description}</p>
            <textarea value={templateDrafts[item.id] ?? item.system_prompt} maxLength={4000} onChange={(event) => setTemplateDrafts((current) => ({ ...current, [item.id]: event.target.value }))} />
            <div><button type="button" disabled={busy || !(templateDrafts[item.id] ?? "").trim()} onClick={() => void saveTemplate(item)}>保存</button>{item.builtin ? <button type="button" disabled={busy || !item.customized} onClick={() => void restoreTemplate(item)}>恢复默认</button> : <button type="button" disabled={busy} onClick={() => void removeTemplate(item)}>删除</button>}</div>
          </article>
        ))}</div>
      </section>
    );
  }

  const loadProvider = (provider: AiProvider) => {
    setAvailableModels([]);
    setProviderTest(null);
    setProviderForm({
      id: provider.id,
      name: provider.name,
      base_url: provider.base_url,
      model: provider.model,
      api_key: "",
    });
  };

  if (subpage === "接入设置") {
    return (
      <div className="prototype-split">
        <section className="prototype-panel prototype-panel--scroll">
          {heading}
          <p className="prototype-page-description">学校服务已设为默认预设。API Key 仅保存在后端；获取模型会同时验证接口与密钥。</p>
          {error && <div className="prototype-live-error">{error}</div>}
          {providerTest && <div className="prototype-live-notice">{providerTest}</div>}
          <form className="prototype-form" onSubmit={(event) => void save(event)}>
            <label><span>Provider ID</span><input required readOnly={providers.some((provider) => provider.id === providerForm.id)} pattern="[A-Za-z0-9_-]+" maxLength={64} value={providerForm.id} onChange={(event) => setProviderForm({ ...providerForm, id: event.target.value })} /></label>
            <label><span>名称</span><input required maxLength={64} value={providerForm.name} onChange={(event) => setProviderForm({ ...providerForm, name: event.target.value })} /></label>
            <label className="prototype-form-wide"><span>Base URL（HTTPS）</span><input required type="url" value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} /></label>
            <label><span>默认模型</span>
              {availableModels.length > 0 ? (
                <select required value={providerForm.model} onChange={(event) => setProviderForm({ ...providerForm, model: event.target.value })}>
                  {availableModels.map((model) => <option key={model} value={model}>{model}</option>)}
                </select>
              ) : (
                <input required value={providerForm.model} onChange={(event) => setProviderForm({ ...providerForm, model: event.target.value })} />
              )}
            </label>
            <label><span>API Key</span><input type="password" minLength={8} autoComplete="new-password" placeholder="保存后不可回读" value={providerForm.api_key} onChange={(event) => setProviderForm({ ...providerForm, api_key: event.target.value })} /></label>
            <div className="prototype-form-actions">
              <button className="prototype-primary" type="submit" disabled={busy}>{busy ? "处理中…" : "保存 Provider"}</button>
              <button className="prototype-secondary" type="button" disabled={busy || !providers.some((provider) => provider.id === providerForm.id && provider.configured)} onClick={() => void discoverModels()}>获取模型</button>
              <button className="prototype-secondary" type="button" disabled={busy || !providers.some((provider) => provider.id === providerForm.id && provider.configured)} onClick={() => void testSelectedModel()}>测试选中模型</button>
              <button className="prototype-secondary" type="button" disabled={busy || !providers.some((provider) => provider.id === providerForm.id && provider.configured)} onClick={() => void testProvider()}>测试默认模型</button>
            </div>
            {!providers.some((provider) => provider.id === providerForm.id && provider.configured) && <p className="prototype-field-hint prototype-form-wide">先保存至少 8 位 API Key，随后即可测试连接。</p>}
          </form>
          {availableModels.length > 0 && (
            <div className="prototype-model-candidates">
              <div className="prototype-section-title"><h3>接口可用模型</h3><span>{availableModels.length} 个</span></div>
              {availableModels.map((model) => {
                const added = providers.find((provider) => provider.id === providerForm.id)?.models.includes(model) ?? false;
                return (
                  <div className="prototype-model-row" key={model}>
                    <code>{model}</code>
                    <button className="prototype-secondary" type="button" disabled={busy || added} onClick={() => void addModel(model)}>{added ? "已添加" : "添加"}</button>
                  </div>
                );
              })}
            </div>
          )}
        </section>
        <aside className="prototype-panel prototype-panel--scroll">
          <span className="prototype-kicker">CONFIGURED</span><h2>已配置 Provider</h2>
          <p className="prototype-panel-hint">管理已添加模型，设置 Chat 默认项或删除不用的模型</p>
          {providers.map((provider) => (
            <article className="prototype-provider-models" key={provider.id}>
              <button className="prototype-provider-heading" type="button" onClick={() => loadProvider(provider)}>
                <div className="prototype-provider-logo">AI</div>
                <div><strong>{provider.name}</strong><span>{provider.models.length} 个模型</span></div>
                <code>{provider.key_hint ?? "未配置密钥"}</code>
                <span className={provider.configured ? "prototype-status-ok" : "prototype-status-missing"}>{provider.configured ? "可用" : "缺少密钥"}</span>
              </button>
              <div className="prototype-provider-model-list">
                {provider.models.map((model) => (
                  <div className="prototype-model-row" key={model}>
                    <code>{model}</code>
                    {model === provider.model ? <span className="prototype-default-model">默认</span> : <button type="button" disabled={busy} onClick={() => void setDefaultModel(provider.id, model)}>设为默认</button>}
                    <button className="prototype-model-delete" type="button" aria-label={`删除模型 ${model}`} title="删除模型" disabled={busy || provider.models.length === 1} onClick={() => void removeModel(provider, model)}>×</button>
                  </div>
                ))}
              </div>
            </article>
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
          {messages.length > 0 ? (
            <div className="prototype-chat-thread">
              {messages.map((item) => item.role === "USER" ? <div className="prototype-user-message" key={item.id}>{item.content}</div> : (
                <div className="prototype-ai-answer" key={item.id}>
                  <Markdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      a: ({ children, ...props }) => (
                        <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>
                      ),
                    }}
                  >
                    {item.content}
                  </Markdown>
                </div>
              ))}
            </div>
          ) : (
            <div className="prototype-chat-empty">
              <span>✦</span><h3>只读作业分析助手</h3>
              <p>回答来自配置的 OpenAI 兼容 Provider；AI 不具备作业控制权限。</p>
              <div className="prototype-suggestion-list">
                {suggestions.map((text) => (
                  <button key={text} type="button" onClick={() => setChat({ ...chat, message: text })}>
                    {text}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        {chatStartedAt !== null && (
          <div className="prototype-chat-waiting" role="status" aria-live="polite">
            <span className="prototype-chat-spinner" aria-hidden="true" />
            <strong>正在等待 {chat.model}</strong>
            <small>{chatWaitSeconds} 秒</small>
          </div>
        )}
        {error && <div className="prototype-live-error">{error}</div>}
        <form className="prototype-composer" onSubmit={(event) => void send(event)}>
          <select aria-label="选择分析提示词" value={chat.template_id ?? ""} onChange={(event) => setChat({ ...chat, template_id: event.target.value || null })}><option value="">通用分析</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select>
          <select aria-label="选择 AI 模型" value={JSON.stringify([chat.provider_id, chat.model])} onChange={(event) => {
            const [provider_id, model] = JSON.parse(event.target.value) as [string, string];
            setChat({ ...chat, provider_id, model });
          }}>
            {!providers.some((provider) => provider.configured) && <option value="school">请先配置可用 Provider</option>}
            {providers.filter((provider) => provider.configured).flatMap((provider) => provider.models.map((model) => <option key={`${provider.id}:${model}`} value={JSON.stringify([provider.id, model])}>{model}</option>))}
          </select>
          <input required aria-label="分析问题" placeholder="输入问题…" value={chat.message} onChange={(event) => setChat({ ...chat, message: event.target.value })} />
          <button className="prototype-send-button" type="submit" title="发送" aria-label="发送分析请求" disabled={busy || !chat.message.trim() || !providers.some((provider) => provider.configured)}>
            <span aria-hidden="true">{busy ? "···" : "➤"}</span>
          </button>
        </form>
      </section>
      <aside className="prototype-panel prototype-panel--scroll">
        <div className="prototype-aside-heading"><div><span className="prototype-kicker">EVIDENCE CONTEXT</span><h2>分析上下文</h2></div><button type="button" className="prototype-secondary" onClick={startSession}>新对话</button></div>
        <details className="prototype-collapsible" open><summary><span>对话历史</span><small>{sessions.length} 个会话</small></summary><div className="prototype-session-list">{sessions.map((session) => <button type="button" className={session.id === sessionId ? "is-active" : ""} key={session.id} onClick={() => void openSession(session.id)}><span>{session.title}</span><small>{session.message_count} 条 · {new Date(session.updated_at).toLocaleString()}</small></button>)}{sessions.length === 0 && <p>还没有历史对话。</p>}</div></details>
        <details className="prototype-collapsible" open><summary><span>历史作业证据</span><small>{selectedJobIds.length} 个已选</small></summary><div className="prototype-ai-job-list">
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
        </div></details>
        <details className="prototype-collapsible" open><summary><span>引用 Git 项目</span><small>{selectedRepositoryIds.length} 个已选</small></summary><div className="prototype-ai-repository-list">
          {repositories.map((repository) => <label key={repository.id}><input type="checkbox" checked={selectedRepositoryIds.includes(repository.id)} onChange={() => setSelectedRepositoryIds((current) => current.includes(repository.id) ? current.filter((id) => id !== repository.id) : [...current, repository.id])} /><span>{repository.name}</span><small>{repository.branch} · {repository.dirty ? `${repository.changed_files} 个未提交文件` : "工作区干净"}</small></label>)}
          {repositories.length === 0 && <p>当前没有可引用的 Git 项目。</p>}
        </div></details>
        <details className="prototype-collapsible"><summary><span>只读边界</span><small>固定安全约束</small></summary><ul className="prototype-check-list">
          <li>AI 仅接收勾选作业与 Git 项目的结构化证据</li>
          <li>无法提交、取消或克隆作业</li>
          <li>密钥原文不会返回浏览器</li>
          <li>调用成功或失败均进入审计记录</li>
        </ul></details>
      </aside>
    </div>
  );
}
