"use client";

import { useQuery, useMutation } from "convex/react";
import { useCurrentUserId } from "@/hooks/useCurrentUserId";
import { api } from "@/convex/_generated/api";
import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MessageSquare, Plus, Send, Bot, User } from "lucide-react";
import type { Id } from "@/convex/_generated/dataModel";

export function AiChatView() {
  const userId = useCurrentUserId();

  const sessions = useQuery(api.chat.listSessions, userId ? { userId } : "skip");
  const [activeSessionId, setActiveSessionId] = useState<Id<"chatSessions"> | null>(null);
  const session = useQuery(api.chat.getSession, activeSessionId ? { sessionId: activeSessionId } : "skip");

  const createSession = useMutation(api.chat.createSession);
  const addMessage = useMutation(api.chat.addMessage);

  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages, streamingText]);

  async function handleSend() {
    if (!input.trim() || !activeSessionId || !userId) return;
    const userMsg = input.trim();
    setInput("");

    await addMessage({ sessionId: activeSessionId, userId, role: "user", content: userMsg });

    const messages = [
      ...(session?.messages ?? []).map((m) => ({ role: m.role, content: m.content })),
      { role: "user" as const, content: userMsg },
    ];

    setStreaming(true);
    setStreamingText("");

    try {
      const res = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages }),
      });

      const reader = res.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let full = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ") && !line.includes("[DONE]")) {
            const data = JSON.parse(line.slice(6)) as { text: string };
            full += data.text;
            setStreamingText(full);
          }
        }
      }

      await addMessage({ sessionId: activeSessionId, userId, role: "assistant", content: full });
    } finally {
      setStreaming(false);
      setStreamingText("");
    }
  }

  return (
    <div className="flex h-full gap-4">
      {/* Session List */}
      <div className="w-56 flex-none flex flex-col gap-2">
        <Button
          variant="secondary"
          size="sm"
          className="gap-2"
          onClick={async () => {
            if (!userId) return;
            const id = await createSession({ userId });
            setActiveSessionId(id);
          }}
        >
          <Plus className="w-3.5 h-3.5" />
          New Chat
        </Button>

        <div className="flex-1 overflow-y-auto space-y-1">
          {(sessions ?? []).map((s) => (
            <button
              key={s._id}
              onClick={() => setActiveSessionId(s._id)}
              className={cn("w-full text-left px-3 py-2 rounded-xl text-sm transition-colors truncate",
                activeSessionId === s._id ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground hover:text-foreground hover:bg-white/5"
              )}
            >
              <MessageSquare className="w-3 h-3 inline mr-1.5 flex-none" />
              {s.title}
            </button>
          ))}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col glass rounded-2xl overflow-hidden min-h-0">
        {!activeSessionId ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Bot className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">Select a chat or start a new one</p>
            </div>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {(session?.messages ?? []).map((m) => (
                <div key={m._id} className={cn("flex gap-2.5", m.role === "user" ? "justify-end" : "justify-start")}>
                  {m.role === "assistant" && (
                    <div className="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center flex-none mt-1">
                      <Bot className="w-3.5 h-3.5 text-primary" />
                    </div>
                  )}
                  <div className={cn("max-w-[80%] rounded-2xl px-4 py-2.5 text-sm",
                    m.role === "user" ? "bg-primary text-white rounded-tr-sm" : "bg-white/8 rounded-tl-sm"
                  )}>
                    {m.content}
                  </div>
                  {m.role === "user" && (
                    <div className="w-7 h-7 rounded-full bg-muted flex items-center justify-center flex-none mt-1">
                      <User className="w-3.5 h-3.5 text-muted-foreground" />
                    </div>
                  )}
                </div>
              ))}

              {streaming && streamingText && (
                <div className="flex gap-2.5 justify-start">
                  <div className="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center flex-none mt-1">
                    <Bot className="w-3.5 h-3.5 text-primary" />
                  </div>
                  <div className="max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm bg-white/8">
                    {streamingText}
                    <span className="inline-block w-1.5 h-4 bg-primary ml-0.5 animate-pulse" />
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            <div className="flex gap-2 p-3 border-t border-border">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                placeholder="Ask Lucid AI anything about trading…"
                disabled={streaming}
                className="flex-1 bg-input border border-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <Button size="icon" onClick={handleSend} disabled={streaming || !input.trim()} className="rounded-xl w-10 h-10">
                <Send className="w-4 h-4" />
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
