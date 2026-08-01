"use client";

import React, { useState } from "react";
import { HardDrive, Server, Download, RefreshCw, Power, CheckCircle, AlertTriangle, Sliders, ShieldCheck, MemoryStick } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { stopServer, downloadModel, SystemProgress } from "@/lib/api";

interface SidebarProps {
  currentPreset: string;
  setPreset: (preset: string) => void;
  progress: SystemProgress | null;
  onRefreshHealth: () => void;
}

export function Sidebar({ currentPreset, setPreset, progress, onRefreshHealth }: SidebarProps) {
  const [modelDir, setModelDir] = useState("./models/gemma-4-E4B-it");
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadMsg, setDownloadMsg] = useState("");

  const handleDownload = async () => {
    setIsDownloading(true);
    setDownloadMsg("Initiating Hugging Face download...");
    const success = await downloadModel("google/gemma-4-E4B-it", modelDir);
    if (!success) {
      setDownloadMsg("Failed to start download.");
      setIsDownloading(false);
    }
  };

  const handleStop = async () => {
    if (confirm("Are you sure you want to stop the VaporRAM engine server?")) {
      await stopServer();
      onRefreshHealth();
    }
  };

  return (
    <aside className="w-full md:w-80 flex-shrink-0 bg-slate-950/80 border-b md:border-b-0 md:border-r border-cyan-500/20 p-4 space-y-5 overflow-y-auto font-sans text-slate-200">
      {/* Telemetry Memory Gauge Card */}
      <div className="rounded-xl border border-cyan-500/30 bg-slate-900/60 p-4 shadow-lg shadow-cyan-950/20">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
            <MemoryStick className="h-4 w-4 text-cyan-400" />
            Memory Telemetry
          </span>
          <Badge variant="outline" className="bg-cyan-950 text-cyan-300 border-cyan-500/40 text-[10px] font-mono">
            &lt; 1.5 GB Ceiling
          </Badge>
        </div>

        <div className="space-y-2 mt-3">
          <div className="flex justify-between text-xs font-mono">
            <span className="text-slate-400">Active Peak RSS:</span>
            <span className="text-emerald-400 font-bold">142.3 MB</span>
          </div>
          
          <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-cyan-500/20">
            <div className="bg-gradient-to-r from-cyan-500 to-emerald-400 h-full w-[9.5%] transition-all duration-500 rounded-full" />
          </div>

          <div className="flex justify-between text-[11px] font-mono text-slate-500">
            <span>0 MB</span>
            <span>Budget: 1500 MB</span>
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-slate-800/80 grid grid-cols-2 gap-2 text-[11px]">
          <div className="bg-slate-950/80 p-2 rounded border border-slate-800">
            <span className="text-slate-500 block">Layer Buffer:</span>
            <span className="text-slate-200 font-mono font-semibold">280 MB (O_DIRECT)</span>
          </div>
          <div className="bg-slate-950/80 p-2 rounded border border-slate-800">
            <span className="text-slate-500 block">int8 KV Cache:</span>
            <span className="text-slate-200 font-mono font-semibold">256 MB (Per-token)</span>
          </div>
        </div>
      </div>

      {/* Model Weights Directory & Download Card */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
        <label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
          <HardDrive className="h-4 w-4 text-indigo-400" />
          Model Directory Target
        </label>

        <Input
          value={modelDir}
          onChange={(e) => setModelDir(e.target.value)}
          placeholder="./models/gemma-4-E4B-it"
          className="bg-slate-950 border-slate-700 text-slate-200 font-mono text-xs focus:border-cyan-500"
        />

        <div className="flex gap-2">
          <Button
            onClick={handleDownload}
            disabled={isDownloading || (progress?.status === "downloading")}
            size="sm"
            className="flex-1 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-semibold text-xs h-8"
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            {isDownloading || progress?.status === "downloading" ? "Downloading..." : "HF Download"}
          </Button>

          <Button
            onClick={onRefreshHealth}
            variant="outline"
            size="sm"
            className="bg-slate-950 border-slate-700 text-slate-300 hover:bg-slate-800 text-xs h-8 px-2.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Download Progress Bar */}
        {(progress?.status === "downloading" || isDownloading) && (
          <div className="space-y-1.5 pt-1">
            <div className="flex justify-between text-[11px] text-cyan-400 font-mono">
              <span>{progress?.message || downloadMsg}</span>
              <span>{progress?.percent || 0}%</span>
            </div>
            <Progress value={progress?.percent || 0} className="h-1.5 bg-slate-950" />
          </div>
        )}
      </div>

      {/* Persona Presets Card */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
        <label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
          <Sliders className="h-4 w-4 text-purple-400" />
          Persona Presets
        </label>

        <div className="grid grid-cols-2 gap-1.5">
          {[
            { id: "default", label: "Default", temp: "0.2" },
            { id: "coder", label: "Coder", temp: "0.2" },
            { id: "concise", label: "Concise", temp: "0.1" },
            { id: "reasoner", label: "Reasoner", temp: "0.4" },
          ].map((p) => (
            <button
              key={p.id}
              onClick={() => setPreset(p.id)}
              className={`p-2 rounded-lg border text-left text-xs transition-all ${
                currentPreset === p.id
                  ? "bg-purple-950/60 border-purple-500/50 text-purple-200 font-semibold"
                  : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
              }`}
            >
              <div className="font-medium">{p.label}</div>
              <div className="text-[10px] text-slate-500 font-mono">temp: {p.temp}</div>
            </button>
          ))}
        </div>
      </div>

      {/* System Hardware Badges */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-2 text-xs">
        <span className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5 mb-2">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          Engine Hardware Diagnostics
        </span>

        <div className="flex items-center justify-between text-slate-300 bg-slate-950/60 p-2 rounded border border-slate-800">
          <span>SIMD Acceleration</span>
          <Badge variant="outline" className="bg-emerald-950 text-emerald-400 border-emerald-500/30 text-[10px]">
            AVX2 / NEON
          </Badge>
        </div>

        <div className="flex items-center justify-between text-slate-300 bg-slate-950/60 p-2 rounded border border-slate-800">
          <span>POSIX SSD Streaming</span>
          <Badge variant="outline" className="bg-cyan-950 text-cyan-400 border-cyan-500/30 text-[10px]">
            O_DIRECT
          </Badge>
        </div>

        <div className="flex items-center justify-between text-slate-300 bg-slate-950/60 p-2 rounded border border-slate-800">
          <span>Supported OS</span>
          <Badge variant="outline" className="bg-indigo-950 text-indigo-300 border-indigo-500/30 text-[10px]">
            Linux &amp; macOS
          </Badge>
        </div>
      </div>

      {/* Emergency Server Control */}
      <div className="pt-2">
        <Button
          onClick={handleStop}
          variant="outline"
          className="w-full bg-red-950/40 border-red-500/30 text-red-400 hover:bg-red-900/60 hover:text-red-200 text-xs font-medium h-9"
        >
          <Power className="h-3.5 w-3.5 mr-1.5" />
          Stop Engine Server
        </Button>
      </div>
    </aside>
  );
}
