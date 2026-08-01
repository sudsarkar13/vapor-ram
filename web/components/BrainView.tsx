"use client";

import React from "react";
import { Cpu, HardDrive, Layers, MemoryStick, Zap, Activity } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function BrainView() {
  const totalLayers = 32;

  return (
    <div className="h-full bg-slate-950 p-6 overflow-y-auto space-y-6 text-slate-100 font-sans">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-xl font-bold text-cyan-400 flex items-center gap-2">
            <Cpu className="h-5 w-5 text-cyan-400" />
            VaporRAM Brain Cortex — Sequential Layer Pipeline (SLP)
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Visualizing zero-copy <span className="text-cyan-300 font-mono">O_DIRECT</span> NVMe SSD layer streaming for <span className="text-emerald-400 font-semibold font-mono">google/gemma-4-E4B-it</span> under a strict 1.5 GB RAM ceiling.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="outline" className="bg-emerald-950 text-emerald-400 border-emerald-500/30 text-xs">
            Double Buffer Active (140 MB / layer)
          </Badge>
        </div>
      </div>

      {/* Pipeline Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-slate-900/60 border-cyan-500/30 shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
              <HardDrive className="h-4 w-4" />
              SSD I/O Prefetching
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs">
            <div className="flex justify-between font-mono">
              <span className="text-slate-400">Mode:</span>
              <span className="text-cyan-300 font-semibold">O_DIRECT (Zero-Copy)</span>
            </div>
            <div className="flex justify-between font-mono">
              <span className="text-slate-400">Prefetch Hint:</span>
              <span className="text-emerald-400">POSIX_FADV_WILLNEED</span>
            </div>
            <div className="flex justify-between font-mono">
              <span className="text-slate-400">Layer Weight Size:</span>
              <span className="text-slate-200">140.0 MB</span>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/60 border-indigo-500/30 shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
              <MemoryStick className="h-4 w-4" />
              Double Buffer Allocation
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs">
            <div className="flex justify-between font-mono">
              <span className="text-slate-400">Buffer A:</span>
              <span className="text-indigo-300 font-semibold">140 MB (Compute Active)</span>
            </div>
            <div className="flex justify-between font-mono">
              <span className="text-slate-400">Buffer B:</span>
              <span className="text-cyan-300 font-semibold">140 MB (SSD Loading)</span>
            </div>
            <div className="flex justify-between font-mono">
              <span className="text-slate-400">Total Buffer Footprint:</span>
              <span className="text-slate-200">280.0 MB</span>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/60 border-purple-500/30 shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1.5">
              <Layers className="h-4 w-4" />
              int8 KV Cache State
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs">
            <div className="flex justify-between font-mono">
              <span className="text-slate-400">Quantization:</span>
              <span className="text-purple-300 font-semibold">int8 + Per-Token Scale</span>
            </div>
            <div className="flex justify-between font-mono">
              <span className="text-slate-400">Context Limit:</span>
              <span className="text-slate-200">8,192 Tokens</span>
            </div>
            <div className="flex justify-between font-mono">
              <span className="text-slate-400">Cache Footprint:</span>
              <span className="text-emerald-400">256 MB (vs 1024 MB fp16)</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 32 Transformer Layers Interactive Grid */}
      <Card className="bg-slate-900/40 border-slate-800">
        <CardHeader>
          <CardTitle className="text-sm font-bold text-slate-200 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-cyan-400" />
              Gemma 4 Transformer Layers (32 Layers)
            </span>
            <span className="text-xs font-mono text-cyan-400 font-normal">
              100% NVMe Streaming Supported
            </span>
          </CardTitle>
        </CardHeader>

        <CardContent>
          <div className="grid grid-cols-4 sm:grid-cols-8 gap-2.5">
            {Array.from({ length: totalLayers }).map((_, idx) => {
              const layerNum = idx + 1;
              return (
                <div
                  key={layerNum}
                  className="p-3 rounded-lg border border-cyan-500/20 bg-slate-950/80 hover:border-cyan-500/60 hover:bg-slate-900 text-center transition-all group"
                >
                  <div className="text-[10px] font-mono text-slate-500 group-hover:text-cyan-400 transition-colors">
                    Layer #{layerNum}
                  </div>
                  <div className="text-xs font-bold text-slate-200 mt-1">140 MB</div>
                  <div className="mt-2 h-1.5 w-full bg-slate-900 rounded-full overflow-hidden border border-slate-800">
                    <div className="h-full bg-cyan-400 w-full animate-pulse" />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
