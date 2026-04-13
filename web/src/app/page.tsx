"use client";

import { useState, useEffect, useCallback } from "react";
import Sidebar from "@/components/sidebar";
import Chat, { type Message } from "@/components/chat";
import IndexForm from "@/components/index-form";
import { fetchRepos, startIndex, pollIndexStatus, queryRepo, type Repo } from "@/lib/api";

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [activeRepo, setActiveRepo] = useState<string | null>(null);
  // Each repo gets its own message history
  const [chatHistory, setChatHistory] = useState<Record<string, Message[]>>({});
  const [loading, setLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [indexStatus, setIndexStatus] = useState<string | null>(null);

  const messages = activeRepo ? chatHistory[activeRepo] ?? [] : [];

  // Load repos on mount
  const loadRepos = useCallback(async () => {
    try {
      const data = await fetchRepos();
      setRepos(data);
    } catch {
      // API might not be ready yet — that's fine
    }
  }, []);

  useEffect(() => {
    loadRepos();
  }, [loadRepos]);

  // ── Index a new repo ─────────────────────────────────────────────────────

  async function handleIndex(repoUrl: string) {
    setIndexing(true);
    setIndexStatus("Starting indexing...");

    try {
      const workflowId = await startIndex(repoUrl);
      setIndexStatus("Indexing in progress — cloning and processing files...");

      // Poll until done
      let done = false;
      while (!done) {
        await new Promise((r) => setTimeout(r, 3000));
        const status = await pollIndexStatus(workflowId);

        if (status.status === "completed") {
          done = true;
          const r = status.result;
          setIndexStatus(
            r
              ? `Done! ${r.files_processed} files, ${r.chunks_stored} chunks, ${r.summaries_generated} summaries`
              : "Indexing complete!"
          );
          // Refresh repo list and switch to the new repo
          await loadRepos();
          setActiveRepo(repoUrl);
        } else if (status.status === "failed") {
          done = true;
          setIndexStatus("Indexing failed. Check the Temporal UI for details.");
        } else {
          setIndexStatus(`Indexing in progress (${status.status})...`);
        }
      }
    } catch (err) {
      setIndexStatus(`Error: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setIndexing(false);
    }
  }

  // ── Send a question ──────────────────────────────────────────────────────

  async function handleSend(question: string) {
    if (!activeRepo) return;

    const userMsg: Message = { role: "user", content: question };
    setChatHistory((prev) => ({
      ...prev,
      [activeRepo]: [...(prev[activeRepo] ?? []), userMsg],
    }));
    setLoading(true);

    try {
      const res = await queryRepo(question, activeRepo);
      const assistantMsg: Message = {
        role: "assistant",
        content: res.answer,
        agent: res.agent,
      };
      setChatHistory((prev) => ({
        ...prev,
        [activeRepo]: [...(prev[activeRepo] ?? []), assistantMsg],
      }));
    } catch {
      const errorMsg: Message = {
        role: "assistant",
        content: "Something went wrong. Make sure the API is running and try again.",
      };
      setChatHistory((prev) => ({
        ...prev,
        [activeRepo]: [...(prev[activeRepo] ?? []), errorMsg],
      }));
    } finally {
      setLoading(false);
    }
  }

  // ── Sidebar handlers ─────────────────────────────────────────────────────

  function handleNewChat() {
    setActiveRepo(null);
    setIndexStatus(null);
  }

  function handleSelectRepo(repoUrl: string) {
    setActiveRepo(repoUrl);
    setIndexStatus(null);
  }

  // ── Derive a display label from the active repo URL ──────────────────────

  function repoLabel(url: string): string {
    const match = url.match(/github\.com\/(.+?)(?:\.git)?$/);
    return match ? match[1] : url;
  }

  return (
    <div className="flex h-screen" style={{ background: "var(--bg-primary)" }}>
      <Sidebar
        repos={repos}
        activeRepo={activeRepo}
        onSelect={handleSelectRepo}
        onNewChat={handleNewChat}
      />

      {activeRepo ? (
        <Chat
          messages={messages}
          loading={loading}
          onSend={handleSend}
          repoLabel={repoLabel(activeRepo)}
        />
      ) : (
        <IndexForm onSubmit={handleIndex} loading={indexing} status={indexStatus} />
      )}
    </div>
  );
}
