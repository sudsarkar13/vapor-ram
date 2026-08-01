"use client";

import React from "react";
import { MessageSquare, Cpu, Activity, Terminal, Trash2, Zap, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export type ActiveTab = "chat" | "brain" | "profiling" | "doctor";

interface HeaderProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  onClearChat: () => void;
  isOnline: boolean;
  activeModel: string;
}

export function Header({ activeTab, setActiveTab, onClearChat, isOnline, activeModel }: HeaderProps) {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-cyan-500/20 bg-slate-950/90 backdrop-blur-md px-4 py-2.5 transition-all">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left Section: Brand & Engine Specs */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-2">
            <span className="text-lg font-extrabold tracking-tight text-cyan-400 flex items-center gap-1.5">
              <Zap className="h-5 w-5 fill-cyan-400/20 text-cyan-400 animate-pulse" />
              VaporRAM
              <span className="text-xs font-semibold text-cyan-500/80 bg-cyan-950/60 px-1.5 py-0.5 rounded border border-cyan-500/30">
                v1.0.6
              </span>
            </span>
          </div>

          <Badge variant="outline" className={isOnline ? "bg-emerald-950/50 text-emerald-400 border-emerald-500/30 text-xs font-medium" : "bg-amber-950/50 text-amber-400 border-amber-500/30 text-xs font-medium"}>
            <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${isOnline ? "bg-emerald-400 animate-ping" : "bg-amber-400"}`} />
            {isOnline ? `● Weights Loaded (${activeModel})` : "○ Engine Offline"}
          </Badge>

          <Badge variant="outline" className="hidden lg:inline-flex bg-slate-900 text-slate-300 border-slate-700/60 text-xs font-normal">
            <Database className="mr-1 h-3.5 w-3.5 text-indigo-400" />
            NVMe O_DIRECT GGUF Streaming (RAM &lt; 1.5 GB Ceiling)
          </Badge>
        </div>

        {/* Center Section: Navigation View Tabs */}
        <div className="flex items-center gap-1 bg-slate-900/80 p-1 rounded-lg border border-slate-800">
          <button
            onClick={() => setActiveTab("chat")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              activeTab === "chat"
                ? "bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
            }`}
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Chat
          </button>

          <button
            onClick={() => setActiveTab("brain")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              activeTab === "brain"
                ? "bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
            }`}
          >
            <Cpu className="h-3.5 w-3.5" />
            Brain Cortex
          </button>

          <button
            onClick={() => setActiveTab("profiling")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              activeTab === "profiling"
                ? "bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
            }`}
          >
            <Activity className="h-3.5 w-3.5" />
            Profiling
          </button>

          <button
            onClick={() => setActiveTab("doctor")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              activeTab === "doctor"
                ? "bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
            }`}
          >
            <Terminal className="h-3.5 w-3.5" />
            Doctor
          </button>
        </div>

        {/* Right Section: Slot Badge & Clear Button */}
        <div className="flex items-center gap-2">
          <Badge className="bg-cyan-950/80 text-cyan-300 border border-cyan-500/30 text-xs font-mono font-medium">
            slot 1
          </Badge>
          
          <Button
            onClick={onClearChat}
            variant="outline"
            size="sm"
            className="h-8 px-2.5 bg-slate-900 border-red-500/30 text-red-400 hover:bg-red-950/40 hover:text-red-300 hover:border-red-500/50 text-xs font-medium transition-all"
          >
            <Trash2 className="h-3.5 w-3.5 mr-1" />
            Clear
          </Button>
        </div>
      </div>
    </header>
  );
}
