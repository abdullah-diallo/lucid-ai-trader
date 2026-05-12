"use client";

import { useQuery, useMutation } from "convex/react";
import { useUser } from "@clerk/nextjs";
import { api } from "@/convex/_generated/api";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Zap } from "lucide-react";

export function StrategiesView() {
  const { user } = useUser();
  const userId = user?.id ?? "";

  const strategies = useQuery(api.strategies.listConfigs, userId ? { userId } : "skip");
  const toggle = useMutation(api.strategies.toggle);

  const enabled = (strategies ?? []).filter((s) => s.enabled).length;
  const total = (strategies ?? []).length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Strategies</h2>
          <p className="text-sm text-muted-foreground">{enabled}/{total} active</p>
        </div>
        <Badge variant="outline" className="text-xs">{total} total</Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {(strategies ?? []).map((s) => (
          <div
            key={s.id}
            className={cn(
              "glass rounded-2xl p-4 flex gap-3 transition-all",
              s.enabled ? "border-white/10" : "opacity-60"
            )}
          >
            <div className={cn(
              "w-8 h-8 rounded-lg flex items-center justify-center flex-none mt-0.5",
              s.enabled ? "bg-primary/20" : "bg-muted"
            )}>
              <Zap className={cn("w-4 h-4", s.enabled ? "text-primary" : "text-muted-foreground")} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium truncate">{s.name}</span>
                <Switch
                  checked={s.enabled}
                  onCheckedChange={(enabled) =>
                    userId && toggle({ userId, strategyId: s.id, enabled })
                  }
                />
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{s.description}</p>
              <Badge variant="outline" className="mt-2 text-[10px] font-mono border-border text-muted-foreground">
                {s.id}
              </Badge>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
