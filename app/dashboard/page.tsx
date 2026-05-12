"use client";

import { useState } from "react";
import { DashboardView } from "@/components/views/DashboardView";
import { StrategiesView } from "@/components/views/StrategiesView";
import { BrokersView } from "@/components/views/BrokersView";
import { TradingViewPanel } from "@/components/views/TradingViewPanel";
import { PerformanceView } from "@/components/views/PerformanceView";
import { BacktestView } from "@/components/views/BacktestView";
import { AiChatView } from "@/components/views/AiChatView";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  LayoutDashboard,
  Zap,
  ArrowLeftRight,
  LineChart,
  BarChart3,
  FlaskConical,
  MessageSquare,
} from "lucide-react";

export default function DashboardPage() {
  return (
    <Tabs defaultValue="dashboard" className="h-full flex flex-col">
      <TabsList className="flex-none bg-card border border-border rounded-xl px-1 py-1 mb-4 w-full justify-start overflow-x-auto">
        <TabsTrigger value="dashboard" className="gap-2">
          <LayoutDashboard className="w-4 h-4" />
          Dashboard
        </TabsTrigger>
        <TabsTrigger value="strategies" className="gap-2">
          <Zap className="w-4 h-4" />
          Strategies
        </TabsTrigger>
        <TabsTrigger value="brokers" className="gap-2">
          <ArrowLeftRight className="w-4 h-4" />
          Brokers
        </TabsTrigger>
        <TabsTrigger value="tradingview" className="gap-2">
          <LineChart className="w-4 h-4" />
          Chart
        </TabsTrigger>
        <TabsTrigger value="performance" className="gap-2">
          <BarChart3 className="w-4 h-4" />
          Performance
        </TabsTrigger>
        <TabsTrigger value="backtest" className="gap-2">
          <FlaskConical className="w-4 h-4" />
          Backtest
        </TabsTrigger>
        <TabsTrigger value="chat" className="gap-2">
          <MessageSquare className="w-4 h-4" />
          AI Chat
        </TabsTrigger>
      </TabsList>

      <div className="flex-1 min-h-0 overflow-auto">
        <TabsContent value="dashboard" className="h-full mt-0">
          <DashboardView />
        </TabsContent>
        <TabsContent value="strategies" className="h-full mt-0">
          <StrategiesView />
        </TabsContent>
        <TabsContent value="brokers" className="h-full mt-0">
          <BrokersView />
        </TabsContent>
        <TabsContent value="tradingview" className="h-full mt-0">
          <TradingViewPanel />
        </TabsContent>
        <TabsContent value="performance" className="h-full mt-0">
          <PerformanceView />
        </TabsContent>
        <TabsContent value="backtest" className="h-full mt-0">
          <BacktestView />
        </TabsContent>
        <TabsContent value="chat" className="h-full mt-0">
          <AiChatView />
        </TabsContent>
      </div>
    </Tabs>
  );
}
