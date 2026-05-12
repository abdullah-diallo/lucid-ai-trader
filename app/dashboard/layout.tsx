"use client";

import { useState } from "react";
import { NavBar } from "@/components/layout/NavBar";
import { Sidebar } from "@/components/layout/Sidebar";

type View = "dashboard" | "strategies" | "brokers" | "tradingview" | "performance" | "backtest" | "chat";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [activeView, setActiveView] = useState<View>("dashboard");

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar activeView={activeView} onViewChange={setActiveView} />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <NavBar />
        <main className="flex-1 overflow-auto p-4">
          {children}
        </main>
      </div>
    </div>
  );
}
