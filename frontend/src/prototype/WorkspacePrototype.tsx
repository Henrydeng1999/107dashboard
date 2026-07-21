import { useEffect, useMemo, useState } from "react";

import { fetchRuntimeInfo } from "../api/jobs";
import { JobsWorkspace } from "./JobsWorkspace";
import { AiWorkspace, ProjectsWorkspace, ReportsWorkspace } from "./ProductWorkspaces";
import { ThemeProvider } from "./useTheme";
import { ThemeToggle } from "./ThemeToggle";
import { HelpWorkspace, SettingsWorkspace, type WorkspaceDestination } from "./HelpWorkspace";
import { RepositoriesWorkspace } from "./RepositoriesWorkspace";
import { OverviewWorkspace } from "./OverviewWorkspace";

type ModuleId = "overview" | "jobs" | "reports" | "projects" | "repositories" | "ai";

type NavModule = {
  id: ModuleId;
  label: string;
  icon: string;
  items: string[];
};

const modules: NavModule[] = [
  {
    id: "overview",
    label: "总览",
    icon: "⌂",
    items: [],
  },
  {
    id: "repositories",
    label: "Git 仓库",
    icon: "⑂",
    items: ["仓库浏览"],
  },
  {
    id: "jobs",
    label: "作业提交管理",
    icon: "▱",
    items: ["作业总览", "新建作业", "活动作业", "历史作业"],
  },
  {
    id: "reports",
    label: "作业诊断报告",
    icon: "⌁",
    items: ["报告总览"],
  },
  {
    id: "projects",
    label: "项目结果评价",
    icon: "◇",
    items: ["项目总览"],
  },
  {
    id: "ai",
    label: "AI 工作台",
    icon: "✦",
    items: ["Chat", "接入设置", "内置提示词", "调用记录"],
  },
];

const pageMeta: Record<ModuleId, { eyebrow: string; title: string; description: string }> = {
  overview: {
    eyebrow: "WORKSPACE OVERVIEW",
    title: "总览",
    description: "一眼查看当前账户最重要的运行状态、异常与近期活动。",
  },
  jobs: {
    eyebrow: "SLURM WORKSPACE",
    title: "作业提交管理",
    description: "配置、提交并跟踪当前账号下的 CPU 与 GPU 作业。",
  },
  reports: {
    eyebrow: "DIAGNOSTICS",
    title: "作业诊断自动报告",
    description: "基于调度事实、资源统计和日志证据生成可复核报告。",
  },
  projects: {
    eyebrow: "PROJECT REVIEW",
    title: "项目结果评价",
    description: "基于确定性诊断结果聚合作业，形成可复核的项目级结论。",
  },
  repositories: {
    eyebrow: "SOURCE CONTROL",
    title: "Git 仓库浏览",
    description: "只读查看当前账户的仓库状态、README 与提交历史。",
  },
  ai: {
    eyebrow: "AI WORKSPACE",
    title: "AI 工作台",
    description: "在会话中选择模型，并管理接入配置、提示词与调用记录。",
  },
};

function StatusDot({ tone = "green" }: { tone?: "green" | "orange" | "blue" }) {
  return <span className={`prototype-status-dot prototype-status-dot--${tone}`} aria-hidden="true" />;
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return <svg className={expanded ? "is-expanded" : ""} viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>;
}

export function WorkspacePrototype() {
  const [activeModule, setActiveModule] = useState<ModuleId>("overview");
  const [utilityPage, setUtilityPage] = useState<"help" | "settings" | null>(null);
  const [activeItems, setActiveItems] = useState<Record<ModuleId, string>>({ overview: "总览", jobs: "作业总览", reports: "报告总览", projects: "项目总览", repositories: "仓库浏览", ai: "Chat" });
  const [expandedModules, setExpandedModules] = useState<Set<ModuleId>>(() => new Set(modules.filter((module) => module.items.length > 0).map((module) => module.id)));
  const [runtimeState, setRuntimeState] = useState<"loading" | "connected" | "degraded" | "unavailable">("loading");
  const [refreshKey, setRefreshKey] = useState(0);
  const active = useMemo(() => modules.find((item) => item.id === activeModule)!, [activeModule]);
  const meta = pageMeta[activeModule];

  function selectModule(module: NavModule) {
    setUtilityPage(null);
    setActiveModule(module.id);
  }

  function toggleModule(module: NavModule) {
    setExpandedModules((current) => {
      const next = new Set(current);
      if (next.has(module.id)) next.delete(module.id);
      else next.add(module.id);
      return next;
    });
  }

  function selectItem(module: NavModule, item: string) {
    setUtilityPage(null);
    setActiveModule(module.id);
    setActiveItems((current) => ({ ...current, [module.id]: item }));
  }

  function navigate(destination: WorkspaceDestination) {
    if (destination.kind === "utility") {
      setUtilityPage(destination.page);
      return;
    }
    setUtilityPage(null);
    setActiveModule(destination.module);
    setActiveItems((current) => ({ ...current, [destination.module]: destination.item }));
  }

  useEffect(() => {
    const controller = new AbortController();
    setRuntimeState("loading");
    fetchRuntimeInfo(controller.signal)
      .then((runtime) => setRuntimeState(runtime.degraded ? "degraded" : "connected"))
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) setRuntimeState("unavailable");
      });
    return () => controller.abort();
  }, [refreshKey]);

  const utilityMeta = utilityPage === "help"
    ? { eyebrow: "DOCUMENTATION", title: "帮助与文档", description: "了解真实能力、操作流程和安全边界。" }
    : { eyebrow: "PREFERENCES", title: "系统设置", description: "管理当前浏览器的外观与功能入口。" };

  return (
    <ThemeProvider>
    <div className="prototype-shell">
      <aside className="prototype-sidebar">
        <button className="prototype-brand" type="button" onClick={() => { setUtilityPage(null); setActiveModule("overview"); }} aria-label="返回总览"><span>107</span><div><strong>Dashboard</strong><small>Student Workspace</small></div></button>
        <div className="prototype-account"><span>PB</span><div><strong>当前 Unix 账号</strong><small>Students · stu</small></div></div>
        <nav className="prototype-nav" aria-label="产品主导航">
          <span className="prototype-nav-label">工作空间</span>
          {modules.map((module) => (
            <div className="prototype-nav-group" key={module.id}>
              <div className="prototype-nav-row"><button type="button" className={activeModule === module.id ? "is-active" : ""} onClick={() => selectModule(module)}><span>{module.icon}</span>{module.label}</button>{module.items.length > 0 && <button type="button" className="prototype-nav-toggle" aria-label={`${expandedModules.has(module.id) ? "折叠" : "展开"}${module.label}`} aria-expanded={expandedModules.has(module.id)} onClick={() => toggleModule(module)}><ChevronIcon expanded={expandedModules.has(module.id)} /></button>}</div>
              {module.items.length > 0 && expandedModules.has(module.id) && <div className="prototype-subnav">{module.items.map((item) => <button type="button" key={item} aria-current={!utilityPage && activeModule === module.id && activeItems[module.id] === item ? "page" : undefined} className={!utilityPage && activeModule === module.id && activeItems[module.id] === item ? "is-current" : ""} onClick={() => selectItem(module, item)}>{item}</button>)}</div>}
            </div>
          ))}
        </nav>
        <div className="prototype-sidebar-bottom"><button type="button" className={utilityPage === "help" ? "is-active" : ""} onClick={() => navigate({ kind: "utility", page: "help" })}><span>?</span>帮助与文档</button><button type="button" className={utilityPage === "settings" ? "is-active" : ""} onClick={() => navigate({ kind: "utility", page: "settings" })}><span>⚙</span>系统设置</button><div className="prototype-platform"><StatusDot /><div><strong>单账号工作台</strong><small>数据源状态见作业页</small></div></div></div>
      </aside>
      <main className="prototype-main">
        <header className="prototype-topbar"><div className="prototype-breadcrumb"><span>{utilityPage ? "工作台" : activeModule === "overview" ? "工作空间" : active.label}</span>{(utilityPage || activeModule !== "overview") && <><b>/</b><strong>{utilityPage === "help" ? "帮助与文档" : utilityPage === "settings" ? "系统设置" : activeItems[activeModule]}</strong></>}</div><div className="prototype-top-actions"><ThemeToggle /><button className="prototype-global-refresh" type="button" disabled={runtimeState === "loading"} onClick={() => setRefreshKey((value) => value + 1)}><span aria-hidden="true">↻</span> 刷新数据</button><span className={`prototype-runtime-state is-${runtimeState}`} role="status" aria-live="polite" aria-busy={runtimeState === "loading"}><StatusDot tone={runtimeState === "connected" ? "green" : runtimeState === "loading" ? "blue" : "orange"} />{runtimeState === "connected" ? "107 已连接" : runtimeState === "degraded" ? "数据已降级" : runtimeState === "unavailable" ? "状态不可用" : "正在连接"}</span></div></header>
        <div className="prototype-content">
          <nav className={`prototype-mobile-navigation${activeModule === "overview" && !utilityPage ? " is-overview" : ""}`} aria-label="当前模块导航">
            {!utilityPage && active.items.map((item) => <button type="button" key={item} aria-current={activeItems[activeModule] === item ? "page" : undefined} className={activeItems[activeModule] === item ? "is-current" : ""} onClick={() => selectItem(active, item)}>{item}</button>)}
            <button type="button" aria-current={utilityPage === "help" ? "page" : undefined} className={utilityPage === "help" ? "is-current" : ""} onClick={() => navigate({ kind: "utility", page: "help" })}>帮助</button>
            <button type="button" aria-current={utilityPage === "settings" ? "page" : undefined} className={utilityPage === "settings" ? "is-current" : ""} onClick={() => navigate({ kind: "utility", page: "settings" })}>设置</button>
          </nav>
          <div className="prototype-page-header"><div><span>{utilityPage ? utilityMeta.eyebrow : meta.eyebrow}</span><h1>{utilityPage ? utilityMeta.title : meta.title}</h1><p>{utilityPage ? utilityMeta.description : meta.description}</p></div><div className="prototype-page-actions">{!utilityPage && activeModule === "jobs" && <button className="prototype-primary" type="button" onClick={() => setActiveItems((current) => ({ ...current, jobs: "新建作业" }))}>＋ 新建作业</button>}</div></div>
          <div className="prototype-workspace">
            {utilityPage === "help" && <HelpWorkspace onNavigate={navigate} />}
            {utilityPage === "settings" && <SettingsWorkspace onNavigate={navigate} />}
            {!utilityPage && activeModule === "overview" && <OverviewWorkspace key={`overview-${refreshKey}`} onNavigate={(destination) => navigate({ kind: "module", ...destination })} />}
            {!utilityPage && activeModule === "jobs" && <JobsWorkspace key={`jobs-${refreshKey}`} subpage={activeItems.jobs} onNavigate={(subpage) => setActiveItems((current) => ({ ...current, jobs: subpage }))} />}
            {!utilityPage && activeModule === "reports" && <ReportsWorkspace key={`reports-${refreshKey}`} />}
            {!utilityPage && activeModule === "projects" && <ProjectsWorkspace key={`projects-${refreshKey}`} />}
            {!utilityPage && activeModule === "repositories" && <RepositoriesWorkspace key={`repositories-${refreshKey}`} />}
            {!utilityPage && activeModule === "ai" && <AiWorkspace key={`ai-${refreshKey}`} subpage={activeItems.ai} />}
          </div>
        </div>
      </main>
    </div>
    </ThemeProvider>
  );
}
