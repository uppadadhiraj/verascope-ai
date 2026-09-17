import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Send, FileCode, Network } from "lucide-react";
import { Layout } from "@/components/Layout";
import { chatApi } from "@/api/endpoints";
import { apiErrorMessage } from "@/api/client";
import type { ChatMessage } from "@/api/types";

export function ChatPage() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!repositoryId || !input.trim() || busy) return;
    const question = input.trim();
    setInput("");
    setError(null);

    const userMsg: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: question,
      citations: null,
      token_usage: null,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);
    setBusy(true);
    try {
      const reply = await chatApi.send(repositoryId, question, conversationId);
      setMessages((m) => [...m, reply]);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Layout>
      <div className="mx-auto flex h-full max-w-3xl flex-col px-6 py-6">
        <h1 className="mb-2 text-lg font-semibold text-slate-100">Repository Chat</h1>
        <Link
          to={`/repositories/${repositoryId}/graph`}
          className="mb-4 flex items-center gap-1.5 self-start text-xs text-indigo-400 hover:underline"
        >
          <Network size={13} />
          Want a visual instead? See the Dependency Graph page for an actual rendered diagram --
          chat only ever answers in text.
        </Link>

        <div className="flex-1 space-y-4 overflow-y-auto">
          {messages.length === 0 && (
            <div className="mt-10 text-center text-sm text-slate-600">
              Ask about this repository's architecture, authentication, data flow, or any file --
              answers are text with file/line citations, not diagrams.
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2.5 text-sm ${
                  m.role === "user" ? "bg-indigo-600 text-white" : "card text-slate-200"
                }`}
              >
                <p className="whitespace-pre-wrap">{m.content}</p>
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5 border-t border-white/10 pt-2">
                    {m.citations.map((c, i) => (
                      <span
                        key={i}
                        className="badge bg-black/20 font-mono text-[11px] text-slate-300"
                        title={c.symbol || undefined}
                      >
                        <FileCode size={11} />
                        {c.file_path}
                        {c.start_line ? `:${c.start_line}` : ""}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="text-xs text-slate-500">Investigating repository...</div>}
          <div ref={bottomRef} />
        </div>

        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}

        <form onSubmit={send} className="mt-4 flex gap-2">
          <input
            className="input"
            placeholder="Where is authentication implemented?"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
          />
          <button type="submit" className="btn-primary" disabled={busy || !input.trim()}>
            <Send size={16} />
          </button>
        </form>
      </div>
    </Layout>
  );
}
