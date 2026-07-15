import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

function App() {
  const [apiStatus, setApiStatus] = useState("检查中...");
  const [jobCount, setJobCount] = useState<number | null>(null);

  useEffect(() => {
    fetch(`${apiBaseUrl}/health`)
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then(() => setApiStatus("API 已连接"))
      .catch(() => setApiStatus("API 未连接"));
    fetch(`${apiBaseUrl}/jobs`)
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then((data: { total: number }) => setJobCount(data.total))
      .catch(() => setJobCount(null));
  }, []);

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">107 DASHBOARD</p>
        <h1>学生算力作业管理平台</h1>
        <p className="summary">从配置作业到查看 Slurm 状态，统一管理你的计算任务。</p>
        <div className="status-card">
          <span className="status-dot" />
          <span>{apiStatus}</span>
        </div>
        {jobCount !== null && <p className="job-count">当前演示账户共有 {jobCount} 个作业</p>}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
