"use client";

import type { Repo } from "@/lib/api";

interface SidebarProps {
  repos: Repo[];
  activeRepo: string | null;
  onSelect: (repoUrl: string) => void;
  onNewChat: () => void;
}

function repoLabel(url: string): string {
  const match = url.match(/github\.com\/(.+?)(?:\.git)?$/);
  return match ? match[1] : url;
}

export default function Sidebar({ repos, activeRepo, onSelect, onNewChat }: SidebarProps) {
  return (
    <aside
      className="flex flex-col h-screen w-64 shrink-0"
      style={{ background: "var(--bg-sidebar)" }}
    >
      <div className="p-4 flex items-center justify-between">
        <span className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
          Onboard Agent
        </span>
        <button
          onClick={onNewChat}
          className="text-xs px-3 py-1.5 rounded-md cursor-pointer transition-colors"
          style={{ background: "var(--accent)", color: "var(--bg-primary)" }}
          onMouseOver={(e) => (e.currentTarget.style.background = "var(--accent-hover)")}
          onMouseOut={(e) => (e.currentTarget.style.background = "var(--accent)")}
        >
          + New
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        {repos.length === 0 && (
          <p className="text-xs px-2 py-4 text-center" style={{ color: "var(--text-muted)" }}>
            No repos indexed yet
          </p>
        )}
        {repos.map((repo) => (
          <button
            key={repo.repo_url}
            onClick={() => onSelect(repo.repo_url)}
            className="w-full text-left px-3 py-2.5 rounded-lg mb-1 text-sm truncate block cursor-pointer transition-colors"
            style={{
              background: activeRepo === repo.repo_url ? "var(--bg-hover)" : "transparent",
              color: activeRepo === repo.repo_url ? "var(--text-primary)" : "var(--text-secondary)",
            }}
            onMouseOver={(e) => {
              if (activeRepo !== repo.repo_url) e.currentTarget.style.background = "var(--bg-input)";
            }}
            onMouseOut={(e) => {
              if (activeRepo !== repo.repo_url) e.currentTarget.style.background =
                activeRepo === repo.repo_url ? "var(--bg-hover)" : "transparent";
            }}
          >
            {repoLabel(repo.repo_url)}
          </button>
        ))}
      </nav>
    </aside>
  );
}
