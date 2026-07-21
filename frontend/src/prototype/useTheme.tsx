import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";

type ThemePreference = "system" | "light" | "dark";

interface ThemeContextValue {
  preference: ThemePreference;
  effective: "light" | "dark";
  setPreference: (p: ThemePreference) => void;
}

const STORAGE_KEY = "107dashboard-theme";

function getStoredPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    /* localStorage unavailable */
  }
  return "system";
}

function getSystemPreference(): "light" | "dark" {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function resolveEffective(pref: ThemePreference): "light" | "dark" {
  if (pref === "system") return getSystemPreference();
  return pref;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(getStoredPreference);
  const [effective, setEffective] = useState<"light" | "dark">(() =>
    resolveEffective(getStoredPreference()),
  );

  const setPreference = useCallback((pref: ThemePreference) => {
    setPreferenceState(pref);
    try {
      localStorage.setItem(STORAGE_KEY, pref);
    } catch {
      /* localStorage unavailable */
    }
  }, []);

  // Sync effective theme whenever preference or system preference changes
  useEffect(() => {
    setEffective(resolveEffective(preference));

    if (preference !== "system") return;

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => setEffective(resolveEffective("system"));
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [preference]);

  // Apply data attributes to <html>
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", effective);
    root.setAttribute("data-theme-preference", preference);
    root.style.setProperty("color-scheme", effective);
  }, [effective, preference]);

  return (
    <ThemeContext.Provider value={{ preference, effective, setPreference }}>
      {children}
    </ThemeContext.Provider>
  );
}
