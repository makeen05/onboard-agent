"use client";

import { useState, useRef, useEffect } from "react";
import Markdown from "react-markdown";

export interface Message {
  role: "user" | "assistant";
  content: string;
  agent?: string;
}

interface ChatProps {
  messages: Message[];
  loading: boolean;
  onSend: (question: string) => void;
  repoLabel: string;
}

export default function Chat({ messages, loading, onSend, repoLabel }: ChatProps) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    setInput("");
    onSend(trimmed);
  }

  return (
    <div className="flex-1 flex flex-col h-screen" style={{ background: "var(--bg-primary)" }}>
      {/* Header */}
      <div
        className="px-6 py-4 text-sm font-medium shrink-0"
        style={{ color: "var(--text-secondary)" }}
      >
        {repoLabel}
      </div>

      {/* Messages — centered column */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-4">
          {messages.length === 0 && (
            <div className="flex items-center justify-center" style={{ minHeight: "50vh" }}>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Ask anything about this codebase
              </p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className="mb-6">
              {msg.role === "user" ? (
                <div className="flex justify-end">
                  <div
                    className="max-w-lg px-4 py-3 rounded-2xl text-sm"
                    style={{ background: "var(--user-bubble)", color: "var(--text-primary)" }}
                  >
                    {msg.content}
                  </div>
                </div>
              ) : (
                <div className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                  <div className="markdown-content">
                    <Markdown>{msg.content}</Markdown>
                  </div>
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="mb-6">
              <span className="inline-flex gap-1 text-sm" style={{ color: "var(--text-muted)" }}>
                <span className="animate-pulse">Thinking</span>
                <span className="animate-bounce" style={{ animationDelay: "0.1s" }}>.</span>
                <span className="animate-bounce" style={{ animationDelay: "0.2s" }}>.</span>
                <span className="animate-bounce" style={{ animationDelay: "0.3s" }}>.</span>
              </span>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Floating input bar */}
      <div className="shrink-0 pb-6 px-6">
        <form
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto relative"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about the codebase..."
            disabled={loading}
            className="w-full px-5 py-4 pr-14 rounded-2xl text-sm outline-none placeholder:opacity-40"
            style={{
              background: "var(--bg-secondary)",
              color: "var(--text-primary)",
            }}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="absolute right-3 top-1/2 -translate-y-1/2 w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: "var(--accent)" }}
            onMouseOver={(e) => {
              if (!e.currentTarget.disabled) e.currentTarget.style.background = "var(--accent-hover)";
            }}
            onMouseOut={(e) => (e.currentTarget.style.background = "var(--accent)")}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 8H13M13 8L8.5 3.5M13 8L8.5 12.5" stroke="#0d0d0d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
