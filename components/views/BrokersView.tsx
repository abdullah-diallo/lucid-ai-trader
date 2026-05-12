"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CheckCircle2, XCircle, Plug, PlugZap } from "lucide-react";
import type { BrokerStatus } from "@/lib/types";

export function BrokersView() {
  const [brokers, setBrokers] = useState<BrokerStatus[]>([]);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [creds, setCreds] = useState<Record<string, Record<string, string>>>({});

  useEffect(() => {
    fetch("/api/brokers/all?action=list")
      .then((r) => r.json())
      .then(setBrokers)
      .catch(() => {});
  }, []);

  async function connect(name: string) {
    setConnecting(name);
    const result = await fetch(`/api/brokers/${name}?action=connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(creds[name] ?? {}),
    }).then((r) => r.json());
    setConnecting(null);
    if (result.ok) {
      const updated = await fetch("/api/brokers/all?action=list").then((r) => r.json());
      setBrokers(updated);
    }
  }

  async function activate(name: string) {
    await fetch(`/api/brokers/${name}?action=activate`, { method: "POST" });
    const updated = await fetch("/api/brokers/all?action=list").then((r) => r.json());
    setBrokers(updated);
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Broker Connections</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {brokers.map((b) => (
          <div key={b.name} className="glass rounded-2xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {b.connected ? (
                  <CheckCircle2 className="w-4 h-4 text-buy" />
                ) : (
                  <XCircle className="w-4 h-4 text-muted-foreground" />
                )}
                <span className="font-medium capitalize">{b.name}</span>
              </div>
              <Badge variant="outline" className={cn("text-xs", b.connected ? "text-buy border-buy/30 bg-buy/10" : "text-muted-foreground")}>
                {b.connected ? "Connected" : "Disconnected"}
              </Badge>
            </div>

            {b.connected && b.balance !== undefined && (
              <div className="text-sm">
                <span className="text-muted-foreground">Balance: </span>
                <span className="font-semibold">${b.balance?.toLocaleString()}</span>
              </div>
            )}

            {!b.connected && b.connectionFields.length > 0 && (
              <div className="space-y-2">
                {b.connectionFields.map((f) => (
                  <input
                    key={f.key}
                    type={f.type}
                    placeholder={f.label}
                    value={creds[b.name]?.[f.key] ?? ""}
                    onChange={(e) =>
                      setCreds((prev) => ({ ...prev, [b.name]: { ...prev[b.name], [f.key]: e.target.value } }))
                    }
                    className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                ))}
              </div>
            )}

            <div className="flex gap-2">
              {!b.connected ? (
                <Button size="sm" className="flex-1 gap-1.5" onClick={() => connect(b.name)} disabled={connecting === b.name}>
                  <Plug className="w-3.5 h-3.5" />
                  {connecting === b.name ? "Connecting…" : "Connect"}
                </Button>
              ) : (
                <Button size="sm" variant="secondary" className="flex-1 gap-1.5" onClick={() => activate(b.name)}>
                  <PlugZap className="w-3.5 h-3.5" />
                  Set Active
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
