import { ThemeToggle } from "./ThemeToggle";
import { useTheme } from "./useTheme";

export type WorkspaceDestination =
  | { kind: "module"; module: "overview" | "jobs" | "reports" | "projects" | "repositories" | "ai"; item: string }
  | { kind: "utility"; page: "help" | "settings" };

type Navigate = (destination: WorkspaceDestination) => void;

const topics = [
  { id: "help-start", label: "开始使用" },
  { id: "help-jobs", label: "作业管理" },
  { id: "help-reports", label: "诊断与评价" },
  { id: "help-git", label: "Git 仓库" },
  { id: "help-ai", label: "AI 工作台" },
  { id: "help-security", label: "安全边界" },
  { id: "help-troubleshooting", label: "故障排查" },
];

export function HelpWorkspace({ onNavigate }: { onNavigate: Navigate }) {
  const focusTopic = (id: string) => {
    window.requestAnimationFrame(() => document.getElementById(id)?.focus());
  };

  return (
    <div className="prototype-help-layout">
      <aside className="prototype-panel prototype-help-nav" aria-label="帮助主题">
        <span className="prototype-kicker">CONTENTS</span>
        <h2>帮助主题</h2>
        <nav aria-label="帮助目录">
          {topics.map((topic) => <a key={topic.id} href={`#${topic.id}`} onClick={() => focusTopic(topic.id)}>{topic.label}</a>)}
        </nav>
      </aside>

      <section className="prototype-panel prototype-panel--scroll prototype-help-content">
        <article id="help-start" tabIndex={-1}>
          <span className="prototype-kicker">GETTING STARTED</span>
          <h2>开始使用</h2>
          <p>107 Dashboard 以当前 Unix 账号访问 Slurm，只展示该账号可见的作业。页面顶部的 LIVE API 表示当前工作区通过后端 API 获取数据，不代表所有写操作都已开放。</p>
          <div className="prototype-help-actions">
            <button className="prototype-primary" type="button" onClick={() => onNavigate({ kind: "module", module: "jobs", item: "作业总览" })}>查看作业总览</button>
            <button className="prototype-secondary" type="button" onClick={() => onNavigate({ kind: "utility", page: "settings" })}>打开外观设置</button>
          </div>
        </article>

        <article id="help-jobs" tabIndex={-1}>
          <span className="prototype-kicker">SLURM JOBS</span>
          <h2>作业管理</h2>
          <dl className="prototype-help-steps">
            <div><dt>1</dt><dd><strong>确认运行时门禁</strong><span>作业页会显示 Native、只读或 Fixture 状态；后端能力关闭时，提交、取消和克隆按钮不会执行操作。</span></dd></div>
            <div><dt>2</dt><dd><strong>提交作业</strong><span>选择受支持的模板或测试项目，填写资源与命令。后端会重新校验字段，并使用幂等键避免重复提交。</span></dd></div>
            <div><dt>3</dt><dd><strong>查看详情与日志</strong><span>在列表点击“查看”，可读取调度信息、资源使用和 stdout/stderr；日志分页读取，不会在浏览器直接访问服务器文件。</span></dd></div>
            <div><dt>4</dt><dd><strong>取消或克隆</strong><span>操作仅在运行时能力开放且作业状态允许时可用；取消前需要再次确认。</span></dd></div>
          </dl>
          <div className="prototype-help-actions">
            <button className="prototype-primary" type="button" onClick={() => onNavigate({ kind: "module", module: "jobs", item: "新建作业" })}>新建作业</button>
            <button className="prototype-secondary" type="button" onClick={() => onNavigate({ kind: "module", module: "jobs", item: "活动作业" })}>查看活动作业</button>
          </div>
        </article>

        <article id="help-reports" tabIndex={-1}>
          <span className="prototype-kicker">EVIDENCE</span>
          <h2>诊断与项目评价</h2>
          <p>诊断报告依据 Slurm 调度事实、资源统计和日志证据生成确定性结论。项目评价可组合多个作业，比较实验状态、健康分数和证据覆盖率。报告不是后台控制入口，也不会修改作业。</p>
          <div className="prototype-help-actions">
            <button className="prototype-secondary" type="button" onClick={() => onNavigate({ kind: "module", module: "reports", item: "报告总览" })}>浏览诊断报告</button>
            <button className="prototype-secondary" type="button" onClick={() => onNavigate({ kind: "module", module: "projects", item: "项目总览" })}>创建评价项目</button>
          </div>
        </article>

        <article id="help-ai" tabIndex={-1}>
          <span className="prototype-kicker">AI PROVIDERS</span>
          <h2>AI 工作台</h2>
          <p>先在“接入设置”集中配置兼容 OpenAI Chat Completions 的 HTTPS Provider、模型与密钥，再在 Chat 内选择本次会话使用的模型。支持工具调用的模型可按需查询运行状态、作业、资源用量、脱敏日志、诊断、评价项目、测试项目与 Git 只读数据；不支持工具调用的模型仍使用您勾选作业的结构化证据。Chat 不具备提交、取消、克隆或修改配置的权限。</p>
          <div className="prototype-help-actions">
            <button className="prototype-primary" type="button" onClick={() => onNavigate({ kind: "module", module: "ai", item: "接入设置" })}>配置 Provider</button>
            <button className="prototype-secondary" type="button" onClick={() => onNavigate({ kind: "module", module: "ai", item: "调用记录" })}>查看调用记录</button>
          </div>
        </article>

        <article id="help-git" tabIndex={-1}>
          <span className="prototype-kicker">SOURCE CONTROL</span>
          <h2>Git 仓库浏览</h2>
          <p>仓库页只读取部署配置允许范围内的 Git 元数据：当前分支、工作区状态、最近提交、提交文件列表与仓库根目录 README。页面不会显示远程仓库地址、凭据、任意文件正文或补丁，也不会执行提交、推送、拉取和分支切换。</p>
          <div className="prototype-help-actions">
            <button className="prototype-primary" type="button" onClick={() => onNavigate({ kind: "module", module: "repositories", item: "仓库浏览" })}>浏览代码仓库</button>
          </div>
        </article>

        <article id="help-security" tabIndex={-1}>
          <span className="prototype-kicker">BOUNDARIES</span>
          <h2>安全边界</h2>
          <ul className="prototype-help-list">
            <li>作业身份由后端进程的 Unix UID 决定，浏览器不能指定其他用户。</li>
            <li>Shell 命令与资源字段均由后端校验，前端不会直接执行命令。</li>
            <li>AI 密钥保存在后端受限文件中，API 和浏览器只显示末四位提示。</li>
            <li>Fixture 或能力探测失败时，危险写操作默认关闭。</li>
          </ul>
        </article>

        <article id="help-troubleshooting" tabIndex={-1}>
          <span className="prototype-kicker">TROUBLESHOOTING</span>
          <h2>故障排查</h2>
          <dl className="prototype-help-faq">
            <div><dt>列表没有更新</dt><dd>确认轮询已开启，点击刷新按钮；仍失败时查看页面内错误信息并重试。</dd></div>
            <div><dt>提交按钮不可用</dt><dd>查看作业页的运行时状态。只读、Fixture 回退或能力探测失败都会关闭提交。</dd></div>
            <div><dt>AI 连接失败</dt><dd>核对 HTTPS Base URL、模型名和密钥，然后在“接入设置”执行连接测试。</dd></div>
            <div><dt>页面颜色不合适</dt><dd>在顶栏或系统设置中选择跟随系统、浅色或深色主题。</dd></div>
          </dl>
        </article>
      </section>
    </div>
  );
}

export function SettingsWorkspace({ onNavigate }: { onNavigate: Navigate }) {
  const { preference, effective } = useTheme();

  return (
    <div className="prototype-settings-grid">
      <section className="prototype-panel prototype-panel--scroll">
        <span className="prototype-kicker">APPEARANCE</span>
        <h2>外观设置</h2>
        <p className="prototype-page-description">选择工作台主题。显式选择会保存在当前浏览器中；跟随系统会实时响应操作系统变化。</p>
        <div className="prototype-setting-row">
          <div><strong>颜色主题</strong><span>当前偏好：{preference === "system" ? "跟随系统" : preference === "light" ? "浅色" : "深色"} · 实际显示：{effective === "light" ? "浅色" : "深色"}</span></div>
          <ThemeToggle />
        </div>
      </section>
      <aside className="prototype-panel prototype-panel--scroll">
        <span className="prototype-kicker">CONFIGURATION</span>
        <h2>功能配置入口</h2>
        <div className="prototype-settings-links">
          <button type="button" onClick={() => onNavigate({ kind: "module", module: "ai", item: "接入设置" })}><strong>AI 接入设置</strong><span>集中配置端点、模型、密钥并测试连接</span></button>
          <button type="button" onClick={() => onNavigate({ kind: "utility", page: "help" })}><strong>帮助中心</strong><span>查看作业、报告和 AI 使用说明</span></button>
        </div>
      </aside>
    </div>
  );
}
