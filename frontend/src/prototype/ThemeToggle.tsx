import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";

import { useTheme } from "./useTheme";

type ThemePreference = "system" | "light" | "dark";

const options: {
  value: ThemePreference;
  label: string;
  icon: LucideIcon;
  title: string;
}[] = [
  { value: "system", label: "系统", icon: Monitor, title: "跟随系统主题" },
  { value: "light", label: "浅色", icon: Sun, title: "切换至浅色主题" },
  { value: "dark", label: "深色", icon: Moon, title: "切换至深色主题" },
];

export function ThemeToggle() {
  const { preference, setPreference } = useTheme();

  return (
    <div className="prototype-theme-toggle" role="group" aria-label="主题切换">
      {options.map((opt) => {
        const Icon = opt.icon;
        return <button
          key={opt.value}
          type="button"
          className={preference === opt.value ? "is-active" : ""}
          onClick={() => setPreference(opt.value)}
          aria-pressed={preference === opt.value}
          aria-label={opt.label}
          title={opt.title}
        >
          <Icon aria-hidden="true" />
        </button>;
      })}
    </div>
  );
}
