"use client";

import { useQuery, useMutation } from "convex/react";
import { useCurrentUserId } from "@/hooks/useCurrentUserId";
import { api } from "@/convex/_generated/api";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Zap, Tv, Clock } from "lucide-react";
import { STRATEGY_REGISTRY } from "@/convex/strategies";

// Look up timeframe locally — don't rely on Convex returning it
const TF_MAP = new Map(STRATEGY_REGISTRY.map(s => [s.id, s.timeframe]));

const TIMEFRAME_ORDER = ["5m", "15m", "1h", "1d"] as const;

const TIMEFRAME_META: Record<string, { label: string; sublabel: string; badgeClass: string }> = {
  "5m":  { label: "5-Minute",  sublabel: "Runs every 5 min — market hours only",      badgeClass: "text-red-400    border-red-400/30    bg-red-400/10"    },
  "15m": { label: "15-Minute", sublabel: "Runs every 15 minutes",                     badgeClass: "text-yellow-400 border-yellow-400/30 bg-yellow-400/10" },
  "1h":  { label: "1-Hour",    sublabel: "Runs every hour",                           badgeClass: "text-blue-400   border-blue-400/30   bg-blue-400/10"   },
  "1d":  { label: "Daily",     sublabel: "Runs once per day at market open (9:30 AM)", badgeClass: "text-purple-400 border-purple-400/30 bg-purple-400/10" },
};

function StrategyCard({
  s,
  userId,
  toggle,
  timeframeBadgeClass,
  timeframeLabel,
}: {
  s: { id: string; name: string; description: string; timeframe: string; enabled: boolean };
  userId: string;
  toggle: (args: { userId: string; strategyId: string; enabled: boolean }) => void;
  timeframeBadgeClass: string;
  timeframeLabel: string;
}) {
  return (
    <div className={cn(
      "glass rounded-2xl p-4 flex gap-3 transition-all",
      !s.enabled && "opacity-50"
    )}>
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
            onCheckedChange={(enabled) => userId && toggle({ userId, strategyId: s.id, enabled })}
          />
        </div>
        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{s.description}</p>
        <div className="flex gap-1.5 mt-2 flex-wrap">
          <Badge variant="outline" className={cn("text-[10px] font-semibold border", timeframeBadgeClass)}>
            {timeframeLabel}
          </Badge>
          <Badge variant="outline" className="text-[10px] font-mono border-border text-muted-foreground">
            {s.id}
          </Badge>
        </div>
      </div>
    </div>
  );
}

export function StrategiesView() {
  const userId = useCurrentUserId();

  const strategies = useQuery(api.strategies.listConfigs, userId ? { userId } : "skip");
  const toggle = useMutation(api.strategies.toggle);

  const all = strategies ?? [];
  const enabled = all.filter(s => s.enabled).length;

  const scalpers   = all.filter(s => TF_MAP.get(s.id) === "tv");
  const autonomous = all.filter(s => TF_MAP.get(s.id) !== "tv");

  const byTimeframe = TIMEFRAME_ORDER.reduce<Record<string, typeof all>>((acc, tf) => {
    acc[tf] = autonomous.filter(s => TF_MAP.get(s.id) === tf);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Strategies</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{enabled} / {all.length} active</p>
        </div>
        <Badge variant="outline" className="text-xs">{all.length} total</Badge>
      </div>

      {/* ── Scalper Strategies ────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Tv className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-amber-400">Scalper Strategies</h3>
          </div>
          <div className="flex-1 h-px bg-amber-400/20" />
        </div>
        <p className="text-xs text-muted-foreground -mt-1">
          These run via <span className="font-medium text-amber-400">TradingView alerts only</span> — keep your chart on the 5-minute timeframe.
          The bot does not auto-trade these; it waits for your TradingView alert to fire.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {scalpers.map(s => (
          <StrategyCard
            key={s.id}
            s={s}
            userId={userId}
            toggle={toggle}
            timeframeBadgeClass="text-amber-400 border-amber-400/30 bg-amber-400/10"
            timeframeLabel="TradingView Only"
          />
        ))}
        </div>
      </div>

      {/* ── Autonomous Strategies ─────────────────────────────── */}
      <div className="space-y-5">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-primary">Autonomous Strategies</h3>
          </div>
          <div className="flex-1 h-px bg-primary/20" />
        </div>
        <p className="text-xs text-muted-foreground -mt-3">
          The bot trades these on its own schedule — <span className="font-medium text-foreground">no TradingView needed</span>.
          Each group shows how often the bot checks for signals.
        </p>

        {TIMEFRAME_ORDER.map(tf => {
          const group = byTimeframe[tf];
          if (!group?.length) return null;
          const meta = TIMEFRAME_META[tf];
          return (
            <div key={tf} className="space-y-2">
              {/* Timeframe sub-header */}
              <div className="flex items-center gap-2">
                <Badge variant="outline" className={cn("text-xs font-semibold border", meta.badgeClass)}>
                  {meta.label}
                </Badge>
                <span className="text-xs text-muted-foreground">{meta.sublabel}</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {group.map(s => (
                  <StrategyCard
                    key={s.id}
                    s={s}
                    userId={userId}
                    toggle={toggle}
                    timeframeBadgeClass={meta.badgeClass}
                    timeframeLabel={meta.label}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
