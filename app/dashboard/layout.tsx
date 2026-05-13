"use client";

import { useState } from "react";
import { NavBar } from "@/components/layout/NavBar";
import { Sidebar } from "@/components/layout/Sidebar";
import { DashboardView } from "@/components/views/DashboardView";
import { StrategiesView } from "@/components/views/StrategiesView";
import { BrokersView } from "@/components/views/BrokersView";
import { TradingViewPanel } from "@/components/views/TradingViewPanel";
import { PerformanceView } from "@/components/views/PerformanceView";
import { BacktestView } from "@/components/views/BacktestView";
import { AiChatView } from "@/components/views/AiChatView";
import { MarketsView } from "@/components/views/MarketsView";

type View = "dashboard" | "strategies" | "brokers" | "tradingview" | "performance" | "backtest" | "chat" | "markets";

export default function DashboardLayout({ children: _ }: { children: React.ReactNode }) {
  const [activeView, setActiveView] = useState<View>("dashboard");

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar activeView={activeView} onViewChange={setActiveView} />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <NavBar />
        <main className="flex-1 overflow-auto p-4">
          {activeView === "dashboard" && <DashboardView />}
          {activeView === "strategies" && <StrategiesView />}
          {activeView === "brokers" && <BrokersView />}
          {activeView === "tradingview" && <TradingViewPanel />}
          {activeView === "performance" && <PerformanceView />}
          {activeView === "backtest" && <BacktestView />}
          {activeView === "chat" && <AiChatView />}
          {activeView === "markets" && <MarketsView />}
        </main>
      </div>
    </div>
  );
}
