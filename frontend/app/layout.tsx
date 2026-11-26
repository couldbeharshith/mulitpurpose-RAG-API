import type { Metadata } from "next";
import "@fontsource-variable/bricolage-grotesque/wght.css";
import "@fontsource-variable/source-sans-3/wght.css";
import "./workspace.css";

export const metadata: Metadata = {
  title: "PlexRAG · Source workspace",
  description: "Open a source and explore it in conversation.",
};

const initializeTheme = `try {
  const theme = localStorage.getItem("plexrag-theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch {}`;

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning>
    <head><script dangerouslySetInnerHTML={{ __html: initializeTheme }} /></head>
    <body>{children}</body>
  </html>;
}
