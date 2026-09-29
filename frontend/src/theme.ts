import { useCallback, useEffect, useState } from "react";

// Keep in sync with the anti-flash inline script in index.html.
const STORAGE_KEY = "rupha.theme";

export type Theme = "light" | "dark";

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function getStoredTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return systemPrefersDark() ? "dark" : "light";
}

function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  // index.html sets `color-scheme: light dark` on <html>, which lets the
  // browser pick native-control theming (a <select>'s option popup,
  // scrollbars) from the OS preference — independent of this app's manual
  // .dark class. When the two disagree (dark mode forced on while the OS is
  // still light, or vice versa), a <select>'s popup renders with the OS's
  // colors while this app's own dark: text classes still apply, producing
  // light-text-on-light-popup (or the reverse) — effectively invisible
  // options. Setting color-scheme explicitly here pins native controls to
  // the SAME theme this app is actually showing.
  document.documentElement.style.colorScheme = theme;
}

/** Reads/writes the manual light/dark override (CLAUDE.md §20: dark mode is
 * first-class, and a person should be able to pick it explicitly rather than
 * only following the OS). Only one theme-owning component is ever mounted at
 * a time (the TopBar inside AppShell, or a bare auth page) — no cross-tab or
 * cross-component sync is needed beyond localStorage + the DOM class both
 * being the single source of truth on next mount. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return { theme, toggleTheme };
}
