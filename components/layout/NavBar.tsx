"use client";

import { useEffect, useState } from "react";
import { UserButton } from "@clerk/nextjs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Moon, Sun, Zap } from "lucide-react";

interface StatusData {
  session: string;
  label: string;
  paperMode: boolean;
}

export function NavBar() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const fetchStatus = () =>
      fetch("/api/status").then((r) => r.json()).then(setStatus).catch(() => {});
    fetchStatus();
    const statusInterval = setInterval(fetchStatus, 10_000);
    const clockInterval = setInterval(() => setTime(new Date()), 1000);
    return () => { clearInterval(statusInterval); clearInterval(clockInterval); };
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const sessionColor = {
    RTH: "bg-buy/20 text-buy border-buy/30",
    "Pre-market": "bg-accent/20 text-accent border-accent/30",
    AH: "bg-close/20 text-close border-close/30",
    Globex: "bg-purple-500/20 text-purple-400 border-purple-500/30",
    Closed: "bg-muted text-muted-foreground border-border",
  }[status?.session ?? "Closed"] ?? "bg-muted text-muted-foreground";

  return (
    <header className="flex items-center justify-between px-5 py-3 border-b border-border bg-card/50 backdrop-blur-xl flex-none">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
            <Zap className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-sm">Lucid AI</span>
        </div>
        {status && (
          <Badge variant="outline" className={`text-xs font-medium border ${sessionColor}`}>
            {status.session}
          </Badge>
        )}
        {status?.paperMode && (
          <Badge variant="outline" className="text-xs border-close/30 text-close bg-close/10">
            PAPER
          </Badge>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-xs text-muted-foreground font-mono tabular-nums">
          {time.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="w-8 h-8"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </Button>
        <UserButton afterSignOutUrl="/login" />
      </div>
    </header>
  );
}
