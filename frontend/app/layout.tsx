import type { Metadata } from "next";
import "@fontsource-variable/bricolage-grotesque/wght.css";
import "@fontsource-variable/source-sans-3/wght.css";
import "./workspace.css";

export const metadata: Metadata = {
  title: "Folio · Source workspace",
  description: "Open a source and explore it in conversation.",
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
