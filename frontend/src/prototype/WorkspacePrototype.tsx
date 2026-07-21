import { useMemo, useState } from "react";

import { JobsWorkspace } from "./JobsWorkspace";
import { AiWorkspace, ProjectsWorkspace, ReportsWorkspace } from "./ProductWorkspaces";
import { ThemeProvider } from "./useTheme";
import { ThemeToggle } from "./ThemeToggle";

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
    items: ["报告总览", "诊断详情", "报告预览"],
  },
  {
    id: "projects",
    label: "项目 AI 评价",
    icon: "◇",
    items: ["项目总览", "实验对比", "结果评价"],
  },
  {
    id: "ai",
    label: "AI 工作台",
    icon: "✦",
    items: ["Chat", "模型接入", "API Keys", "提示词模板", "调用记录"],
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
    title: "项目 AI 结果评价",
    description: "聚合实验结果，比较方案并形成项目级结论。",
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
  const [activeItems, setActiveItems] = useState<Record<ModuleId, string>>({ jobs: "作业总览", reports: "报告总览", projects: "项目总览", ai: "Chat" });
  const active = useMemo(() => modules.find((item) => item.id === activeModule)!, [activeModule]);
  const meta = pageMeta[activeModule];

  function selectModule(module: NavModule) {
    setActiveModule(module.id);
  }

  function selectItem(module: NavModule, item: string) {
    setActiveModule(module.id);
    setActiveItems((current) => ({ ...current, [module.id]: item }));
  }

  return (
    <ThemeProvider>
    <div className="prototype-shell">
      <aside className="prototype-sidebar">
        <div className="prototype-brand"><span>107</span><div><strong>Dashboard</strong><small>Student Workspace</small></div></div>
        <div className="prototype-account"><span>PB</span><div><strong>当前 Unix 账号</strong><small>Students · stu</small></div><button type="button">⌄</button></div>
        <nav className="prototype-nav" aria-label="产品主导航">
          <span className="prototype-nav-label">工作空间</span>
          {modules.map((module) => (
            <div className="prototype-nav-group" key={module.id}>
              <button type="button" className={activeModule === module.id ? "is-active" : ""} onClick={() => selectModule(module)} aria-expanded={activeModule === module.id}><span>{module.icon}</span>{module.label}<b>⌄</b></button>
              {activeModule === module.id && <div className="prototype-subnav">{module.items.map((item) => <button type="button" key={item} className={activeItems[module.id] === item ? "is-current" : ""} onClick={() => selectItem(module, item)}>{item}</button>)}</div>}
            </div>
          ))}
        </nav>
        <div className="prototype-sidebar-bottom"><div className="prototype-sidebar-static-item"><span>?</span><span>帮助与文档</span></div><div className="prototype-sidebar-static-item"><span>⚙</span><span>系统设置</span></div><div className="prototype-platform"><StatusDot /><div><strong>单账号工作台</strong><small>数据源状态见作业页</small></div></div></div>
      </aside>
      <main className="prototype-main">
        <header className="prototype-topbar"><div className="prototype-breadcrumb"><span>{active.label}</span><b>/</b><strong>{activeItems[activeModule]}</strong></div><div className="prototype-top-actions"><ThemeToggle /><span className="prototype-design-pill is-live">LIVE API</span><span className="prototype-avatar">PB</span></div></header>
        <div className="prototype-content">
          <div className="prototype-page-header"><div><span>{meta.eyebrow}</span><h1>{meta.title}</h1><p>{meta.description}</p></div><div className="prototype-page-actions">{activeModule === "jobs" && <button className="prototype-primary" type="button" onClick={() => setActiveItems((current) => ({ ...current, jobs: "新建作业" }))}>＋ 新建作业</button>}</div></div>
          <div className="prototype-workspace">
            {activeModule === "jobs" && <JobsWorkspace subpage={activeItems.jobs} onNavigate={(subpage) => setActiveItems((current) => ({ ...current, jobs: subpage }))} />}
            {activeModule === "reports" && <ReportsWorkspace />}
            {activeModule === "projects" && <ProjectsWorkspace />}
            {activeModule === "ai" && <AiWorkspace subpage={activeItems.ai} />}
          </div>
        </div>
      </main>
    </div>
    </ThemeProvider>
  );
}
