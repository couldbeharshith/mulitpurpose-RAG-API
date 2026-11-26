"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

export function ThemeControl() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const system = matchMedia("(prefers-color-scheme: dark)");
    function sync() {
      const theme = document.documentElement.dataset.theme;
      setDark(theme === "dark" || (theme !== "light" && system.matches));
    }
    sync();
    system.addEventListener("change", sync);
    return () => system.removeEventListener("change", sync);
  }, []);

  function toggle() {
    const theme = dark ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    setDark(!dark);
    try { localStorage.setItem("plexrag-theme", theme); } catch { /* The tab still reflects the choice. */ }
  }

  const label = dark ? "Switch to light theme" : "Switch to dark theme";
  return <button className="theme-control icon-btn" aria-label={label} title={label} onClick={toggle}>
    {dark ? <Sun /> : <Moon />}
  </button>;
}
