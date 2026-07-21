import { useEffect, useMemo, useState } from "react";

import { fetchRepositories, fetchRepository, fetchRepositoryCommit } from "../api/repositories";
import type {
  GitCommitDetail,
  GitRepositoryDetail,
  GitRepositorySummary,
} from "../features/repositories/types";

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "暂无提交";
}

function statusLabel(status: string): string {
  const code = status.trim();
  if (code === "M") return "修改";
  if (code === "A") return "新增";
  if (code === "D") return "删除";
  if (code === "R") return "重命名";
  if (code === "??" || code === "?") return "未跟踪";
  return code || "变更";
}

export function RepositoriesWorkspace() {
  const [repositories, setRepositories] = useState<GitRepositorySummary[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GitRepositoryDetail | null>(null);
  const [commit, setCommit] = useState<GitCommitDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchRepositories(controller.signal)
      .then((payload) => {
        setEnabled(payload.enabled);
        setRepositories(payload.items);
        setSelectedId((current) => current ?? payload.items[0]?.id ?? null);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "无法读取 Git 仓库");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setCommit(null);
    fetchRepository(selectedId, controller.signal)
      .then(setDetail)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "无法读取仓库详情");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [selectedId]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return repositories;
    return repositories.filter((item) =>
      item.name.toLowerCase().includes(normalized)
      || item.relative_path.toLowerCase().includes(normalized)
      || item.branch.toLowerCase().includes(normalized)
    );
  }, [query, repositories]);

  const openCommit = async (revision: string) => {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    try {
      setCommit(await fetchRepositoryCommit(selectedId, revision));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取提交详情");
    } finally {
      setLoading(false);
    }
  };

  if (!enabled) {
    return <section className="prototype-panel prototype-live-empty"><span>⌘</span><h2>Git 浏览尚未配置</h2><p>部署管理员需要显式设置允许扫描的仓库根目录。</p></section>;
  }

  return (
    <div className="prototype-repository-layout">
      <section className="prototype-panel prototype-panel--flush prototype-repository-sidebar">
        <div className="prototype-toolbar">
          <label className="prototype-search"><span aria-hidden="true">⌕</span><input aria-label="搜索仓库" placeholder="搜索仓库、路径或分支" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <span className="prototype-repository-count">{filtered.length}</span>
        </div>
        {error && <div className="prototype-live-error" role="alert">{error}</div>}
        <div className="prototype-repository-list" aria-label="Git 仓库">
          {filtered.map((repository) => (
            <button type="button" key={repository.id} className={selectedId === repository.id ? "is-selected" : ""} aria-current={selectedId === repository.id ? "true" : undefined} onClick={() => setSelectedId(repository.id)}>
              <span className="prototype-repository-icon" aria-hidden="true">◇</span>
              <span><strong>{repository.name}</strong><small>{repository.relative_path}</small></span>
              <span className={repository.dirty ? "is-dirty" : "is-clean"}>{repository.dirty ? `${repository.changed_files} 变更` : "干净"}</span>
            </button>
          ))}
          {!loading && filtered.length === 0 && <div className="prototype-live-empty"><span>⌕</span><h2>没有匹配仓库</h2></div>}
        </div>
      </section>

      <section className="prototype-panel prototype-panel--scroll prototype-repository-main">
        {loading && !detail && <div className="prototype-live-loading">正在读取 Git 元数据…</div>}
        {detail && <>
          <div className="prototype-repository-heading">
            <div><span className="prototype-kicker">READ-ONLY REPOSITORY</span><h2>{detail.repository.name}</h2><p>{detail.repository.relative_path}</p></div>
            <div><span className="prototype-git-branch">⑂ {detail.repository.branch}</span><span className={detail.repository.dirty ? "prototype-git-state is-dirty" : "prototype-git-state is-clean"}>{detail.repository.dirty ? "工作区有变更" : "工作区干净"}</span></div>
          </div>
          <div className="prototype-repository-facts">
            <div><span>HEAD</span><code>{detail.repository.head?.slice(0, 12) ?? "无提交"}</code></div>
            <div><span>最近提交</span><strong>{formatDate(detail.repository.last_commit_at)}</strong></div>
            <div><span>工作区</span><strong>{detail.repository.changed_files} 个变更文件</strong></div>
          </div>

          <section className="prototype-repository-section">
            <div className="prototype-panel-heading"><div><span className="prototype-kicker">WORKTREE</span><h2>工作区状态</h2></div><span className="prototype-badge">只读</span></div>
            {detail.changes.length > 0 ? <div className="prototype-change-list">{detail.changes.map((item, index) => <div key={`${item.path}-${index}`}><span>{statusLabel(item.status)}</span><code>{item.path}</code></div>)}</div> : <p className="prototype-repository-empty">没有未提交变更。</p>}
          </section>

          <section className="prototype-repository-section">
            <div className="prototype-panel-heading"><div><span className="prototype-kicker">README</span><h2>{detail.readme_name ?? "仓库说明"}</h2></div>{detail.readme_truncated && <span className="prototype-badge prototype-badge--orange">已截断</span>}</div>
            {detail.readme_content ? <pre className="prototype-readme">{detail.readme_content}</pre> : <p className="prototype-repository-empty">仓库根目录没有 README。</p>}
          </section>
        </>}
      </section>

      <aside className="prototype-panel prototype-panel--scroll prototype-commit-panel">
        <span className="prototype-kicker">COMMIT HISTORY</span><h2>{commit ? "提交详情" : "最近提交"}</h2>
        {commit ? <div className="prototype-commit-detail">
          <button className="prototype-secondary" type="button" onClick={() => setCommit(null)}>← 返回历史</button>
          <code>{commit.hash}</code><h3>{commit.subject}</h3>
          <p>{commit.author_name} · {formatDate(commit.authored_at)}</p>
          {commit.body && <pre>{commit.body}</pre>}
          <div className="prototype-change-list">{commit.files.map((item, index) => <div key={`${item.path}-${index}`}><span>{statusLabel(item.status)}</span><code>{item.path}</code></div>)}</div>
        </div> : <div className="prototype-commit-list">{detail?.commits.map((item) => (
          <button type="button" key={item.hash} onClick={() => void openCommit(item.hash)}>
            <span><strong>{item.subject}</strong><small>{item.author_name} · {formatDate(item.authored_at)}</small></span><code>{item.short_hash}</code>
          </button>
        ))}</div>}
        {!loading && detail?.commits.length === 0 && <p className="prototype-repository-empty">仓库尚无提交。</p>}
      </aside>
    </div>
  );
}
