// Runs before first paint so there's no light-then-dark flash. Mirrors
// src/theme.ts's storage key/logic exactly — keep the two in sync. A file
// (not an inline <script>) so the Content-Security-Policy can forbid inline
// scripts (vercel.json).
(function () {
  try {
    var stored = localStorage.getItem("rupha.theme");
    var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
    // Keep native controls (select popups, scrollbars) in sync with the
    // manually-chosen theme, not the OS's — see theme.ts::applyTheme.
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  } catch (e) {}
})();
