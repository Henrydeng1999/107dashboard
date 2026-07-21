import { useEffect, useMemo, useRef, useState } from "react";

import { JobsWorkspace } from "./JobsWorkspace";
import { AiWorkspace, ProjectsWorkspace, ReportsWorkspace } from "./ProductWorkspaces";
import { ThemeProvider } from "./useTheme";
import { ThemeToggle } from "./ThemeToggle";
import { HelpWorkspace, SettingsWorkspace, type WorkspaceDestination } from "./HelpWorkspace";

type ModuleId = "jobs" | "reports" | "projects" | "ai";

type NavModule = {
  id: ModuleId;
  label: string;
  icon: string;
  items: string[];
};

const modules: NavModule[] = [
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
    items: ["Chat", "模型接入", "API Keys", "内置提示词", "调用记录"],
  },
];

const pageMeta: Record<ModuleId, { eyebrow: string; title: string; description: string }> = {
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
  ai: {
    eyebrow: "AI WORKSPACE",
    title: "AI 工作台",
    description: "管理模型接入、提示词与辅助分析会话。",
  },
};

function StatusDot({ tone = "green" }: { tone?: "green" | "orange" | "blue" }) {
  return <span className={`prototype-status-dot prototype-status-dot--${tone}`} aria-hidden="true" />;
}

export function WorkspacePrototype() {
  const [activeModule, setActiveModule] = useState<ModuleId>("jobs");
  const [utilityPage, setUtilityPage] = useState<"help" | "settings" | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);
  const [activeItems, setActiveItems] = useState<Record<ModuleId, string>>({ jobs: "作业总览", reports: "报告总览", projects: "项目总览", ai: "Chat" });
  const active = useMemo(() => modules.find((item) => item.id === activeModule)!, [activeModule]);
  const meta = pageMeta[activeModule];

  function selectModule(module: NavModule) {
    setUtilityPage(null);
    setAccountOpen(false);
    setActiveModule(module.id);
  }

  function selectItem(module: NavModule, item: string) {
    setUtilityPage(null);
    setAccountOpen(false);
    setActiveModule(module.id);
    setActiveItems((current) => ({ ...current, [module.id]: item }));
  }

  function navigate(destination: WorkspaceDestination) {
    setAccountOpen(false);
    if (destination.kind === "utility") {
      setUtilityPage(destination.page);
      return;
    }
    setUtilityPage(null);
    setActiveModule(destination.module);
    setActiveItems((current) => ({ ...current, [destination.module]: destination.item }));
  }

  useEffect(() => {
    if (!accountOpen) return;
    const close = (event: MouseEvent) => {
      if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [accountOpen]);

  const utilityMeta = utilityPage === "help"
    ? { eyebrow: "DOCUMENTATION", title: "帮助与文档", description: "了解真实能力、操作流程和安全边界。" }
    : { eyebrow: "PREFERENCES", title: "系统设置", description: "管理当前浏览器的外观与功能入口。" };

  return (
    <ThemeProvider>
    <div className="prototype-shell">
      <aside className="prototype-sidebar">
        <div className="prototype-brand"><span>107</span><div><strong>Dashboard</strong><small>Student Workspace</small></div></div>
        <div className="prototype-account" ref={accountRef}><span>PB</span><div><strong>当前 Unix 账号</strong><small>Students · stu</small></div><button type="button" aria-label="打开账号菜单" aria-expanded={accountOpen} onClick={() => setAccountOpen((value) => !value)}>⌄</button>{accountOpen && <div className="prototype-account-menu"><strong>当前会话</strong><span>身份由后端 Unix UID 确认</span><button type="button" onClick={() => navigate({ kind: "utility", page: "settings" })}>系统设置</button><button type="button" onClick={() => navigate({ kind: "utility", page: "help" })}>帮助与文档</button></div>}</div>
        <nav className="prototype-nav" aria-label="产品主导航">
          <span className="prototype-nav-label">工作空间</span>
          {modules.map((module) => (
            <div className="prototype-nav-group" key={module.id}>
              <button type="button" className={activeModule === module.id ? "is-active" : ""} onClick={() => selectModule(module)} aria-expanded={activeModule === module.id}><span>{module.icon}</span>{module.label}<span aria-hidden="true">⌄</span></button>
              {activeModule === module.id && <div className="prototype-subnav">{module.items.map((item) => <button type="button" key={item} aria-current={!utilityPage && activeItems[module.id] === item ? "page" : undefined} className={activeItems[module.id] === item ? "is-current" : ""} onClick={() => selectItem(module, item)}>{item}</button>)}</div>}
            </div>
          ))}
        </nav>
        <div className="prototype-sidebar-bottom"><button type="button" className={utilityPage === "help" ? "is-active" : ""} onClick={() => navigate({ kind: "utility", page: "help" })}><span>?</span>帮助与文档</button><button type="button" className={utilityPage === "settings" ? "is-active" : ""} onClick={() => navigate({ kind: "utility", page: "settings" })}><span>⚙</span>系统设置</button><div className="prototype-platform"><StatusDot /><div><strong>单账号工作台</strong><small>数据源状态见作业页</small></div></div></div>
      </aside>
      <main className="prototype-main">
        <header className="prototype-topbar"><div className="prototype-breadcrumb"><span>{utilityPage ? "工作台" : active.label}</span><b>/</b><strong>{utilityPage === "help" ? "帮助与文档" : utilityPage === "settings" ? "系统设置" : activeItems[activeModule]}</strong></div><div className="prototype-top-actions"><ThemeToggle /><span className="prototype-design-pill is-live">API 数据</span><button className="prototype-avatar" type="button" aria-label="打开系统设置" onClick={() => navigate({ kind: "utility", page: "settings" })}>PB</button></div></header>
        <div className="prototype-content">
          <nav className="prototype-mobile-navigation" aria-label="当前模块导航">
            {!utilityPage && active.items.map((item) => <button type="button" key={item} aria-current={activeItems[activeModule] === item ? "page" : undefined} className={activeItems[activeModule] === item ? "is-current" : ""} onClick={() => selectItem(active, item)}>{item}</button>)}
            <button type="button" aria-current={utilityPage === "help" ? "page" : undefined} className={utilityPage === "help" ? "is-current" : ""} onClick={() => navigate({ kind: "utility", page: "help" })}>帮助</button>
            <button type="button" aria-current={utilityPage === "settings" ? "page" : undefined} className={utilityPage === "settings" ? "is-current" : ""} onClick={() => navigate({ kind: "utility", page: "settings" })}>设置</button>
          </nav>
          <div className="prototype-page-header"><div><span>{utilityPage ? utilityMeta.eyebrow : meta.eyebrow}</span><h1>{utilityPage ? utilityMeta.title : meta.title}</h1><p>{utilityPage ? utilityMeta.description : meta.description}</p></div><div className="prototype-page-actions">{!utilityPage && activeModule === "jobs" && <button className="prototype-primary" type="button" onClick={() => setActiveItems((current) => ({ ...current, jobs: "新建作业" }))}>＋ 新建作业</button>}</div></div>
          <div className="prototype-workspace">
            {utilityPage === "help" && <HelpWorkspace onNavigate={navigate} />}
            {utilityPage === "settings" && <SettingsWorkspace onNavigate={navigate} />}
            {!utilityPage && activeModule === "jobs" && <JobsWorkspace subpage={activeItems.jobs} onNavigate={(subpage) => setActiveItems((current) => ({ ...current, jobs: subpage }))} />}
            {!utilityPage && activeModule === "reports" && <ReportsWorkspace />}
            {!utilityPage && activeModule === "projects" && <ProjectsWorkspace />}
            {!utilityPage && activeModule === "ai" && <AiWorkspace subpage={activeItems.ai} />}
          </div>
        </div>
      </main>
    </div>
    </ThemeProvider>
  );
}
