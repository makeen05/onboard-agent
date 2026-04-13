"use client";

import { useState } from "react";

interface IndexFormProps {
  onSubmit: (repoUrl: string) => void;
  loading: boolean;
  status: string | null;
}

export default function IndexForm({ onSubmit, loading, status }: IndexFormProps) {
  const [url, setUrl] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="max-w-md w-full px-6 text-center">
        <h1 className="text-2xl font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
          Onboard Agent
        </h1>
        <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }}>
          Enter a GitHub repo URL to get started. We&apos;ll index the codebase so you can ask
          questions about it.
        </p>

        <form onSubmit={handleSubmit} className="relative">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            disabled={loading}
            className="w-full px-5 py-4 pr-24 rounded-2xl text-sm outline-none placeholder:opacity-40"
            style={{
              background: "var(--bg-secondary)",
              color: "var(--text-primary)",
            }}
          />
          <button
            type="submit"
            disabled={loading || !url.trim()}
            className="absolute right-3 top-1/2 -translate-y-1/2 px-4 py-2 rounded-xl text-sm font-medium cursor-pointer transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: "var(--accent)", color: "var(--bg-primary)" }}
            onMouseOver={(e) => {
              if (!e.currentTarget.disabled) e.currentTarget.style.background = "var(--accent-hover)";
            }}
            onMouseOut={(e) => (e.currentTarget.style.background = "var(--accent)")}
          >
            {loading ? "Indexing..." : "Index"}
          </button>
        </form>

        {status && (
          <p className="mt-4 text-sm" style={{ color: "var(--text-secondary)" }}>
            {status}
          </p>
        )}
      </div>
    </div>
  );
}
