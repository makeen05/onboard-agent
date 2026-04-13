// lib/api.ts
//
// API client for the FastAPI backend. All fetch calls go through here
// so the base URL is configured in one place.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Repo {
  id: number;
  repo_url: string;
  indexed_at: string;
}

export interface IndexStatus {
  workflow_id: string;
  status: string;
  result: { chunks_stored: number; files_processed: number; summaries_generated: number } | null;
}

export interface QueryResponse {
  workflow_id: string;
  answer: string;
  agent: string;
}

// ── Repos ───────────────────────────────────────────────────────────────────

export async function fetchRepos(): Promise<Repo[]> {
  const res = await fetch(`${API_BASE}/repos`);
  if (!res.ok) throw new Error("Failed to fetch repos");
  return res.json();
}

// ── Indexing ────────────────────────────────────────────────────────────────

export async function startIndex(repoUrl: string): Promise<string> {
  const res = await fetch(`${API_BASE}/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl }),
  });
  if (!res.ok) throw new Error("Failed to start indexing");
  const data = await res.json();
  return data.workflow_id as string;
}

export async function pollIndexStatus(workflowId: string): Promise<IndexStatus> {
  const res = await fetch(`${API_BASE}/index/${workflowId}`);
  if (!res.ok) throw new Error("Failed to poll index status");
  return res.json();
}

// ── Query ───────────────────────────────────────────────────────────────────

export async function queryRepo(question: string, repoUrl: string): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, repo_url: repoUrl }),
  });
  if (!res.ok) throw new Error("Failed to query repo");
  return res.json();
}
