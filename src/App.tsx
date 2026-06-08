import { useEffect, useState } from "react";

import { Sidebar, type PageKey } from "./components/sidebar";
import { ComparePage } from "./pages/compare";
import { DashboardPage } from "./pages/dashboard";
import { MnenoSuitePage } from "./pages/mneno-suite";
import { RunsPage } from "./pages/runs";

const validPages: PageKey[] = ["dashboard", "runs", "compare", "mneno-suite"];

function pageFromHash(): PageKey {
  const candidate = window.location.hash.replace("#/", "") as PageKey;
  return validPages.includes(candidate) ? candidate : "dashboard";
}

export default function App() {
  const [page, setPage] = useState<PageKey>(pageFromHash);

  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = (nextPage: PageKey) => {
    window.location.hash = `/${nextPage}`;
    setPage(nextPage);
  };

  return (
    <div className="min-h-dvh bg-canvas text-ink-950">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Sidebar activePage={page} onNavigate={navigate} />
      <main
        id="main-content"
        className="min-w-0 px-4 pb-12 pt-24 sm:px-6 lg:ml-64 lg:px-10 lg:pt-10"
      >
        <div className="mx-auto max-w-7xl">
          {page === "dashboard" && <DashboardPage onNavigate={navigate} />}
          {page === "runs" && <RunsPage />}
          {page === "compare" && <ComparePage />}
          {page === "mneno-suite" && <MnenoSuitePage />}
        </div>
      </main>
    </div>
  );
}
