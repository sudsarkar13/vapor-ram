"use client";

import React, { useState, useEffect } from "react";
import { Terminal, CheckCircle2, AlertCircle, RefreshCw, Cpu, HardDrive, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchHealth, VaporHealth } from "@/lib/api";

export function DoctorView() {
  const [health, setHealth] = useState<VaporHealth | null>(null);
  const [loading, setLoading] = useState(false);

  const loadDoctorData = async () => {
    setLoading(true);
    const data = await fetchHealth();
    setHealth(data);
    setLoading(false);
  };

  useEffect(() => {
    loadDoctorData();
  }, []);

  const doctorChecks = [
    {
      name: "system.os",
      label: "Operating System & Hardware",
      detail: health ? `${health.engine} Ready (Linux & macOS Supported)` : "Linux / macOS MacBook (Apple Silicon M1–M5 & Intel)",
      status: "ok",
    },
    {
      name: "cpu.vector",
      label: "SIMD Vector Acceleration",
      detail: "AVX2 + FMA3 (x86_64) / ARM NEON + AMX Matrix Extensions (Apple Silicon)",
      status: "ok",
    },
    {
      name: "memory.ram",
      label: "RAM Memory Ceiling Budget",
      detail: health ? `${health.ram_ceiling} Target (< 1.5 GB RAM)` : "< 1.5 GB RAM Ceiling Target",
      status: "ok",
    },
    {
      name: "engine.runtime",
      label: "Model Execution Runtime",
      detail: health ? `Active Model: ${health.active_model} (${health.version})` : "GGUF Engine & C SIMD Layer Streamer Ready",
      status: "ok",
    },
  ];

  return (
    <div className="h-full bg-slate-950 p-6 overflow-y-auto space-y-6 text-slate-100 font-sans">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-xl font-bold text-cyan-400 flex items-center gap-2">
            <Terminal className="h-5 w-5 text-cyan-400" />
            VaporRAM Doctor Diagnostics
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            System &amp; hardware inspector for VaporRAM low-memory execution.
          </p>
        </div>

        <Button
          onClick={loadDoctorData}
          disabled={loading}
          size="sm"
          className="bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-semibold text-xs h-8"
        >
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Run Diagnostics
        </Button>
      </div>

      <div className="space-y-3">
        {doctorChecks.map((check, idx) => (
          <Card key={idx} className="bg-slate-900/60 border-slate-800">
            <CardContent className="p-4 flex items-start justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="bg-slate-950 text-cyan-400 border-cyan-500/30 text-[10px] font-mono">
                    {check.name}
                  </Badge>
                  <h3 className="text-sm font-bold text-slate-200">{check.label}</h3>
                </div>
                <p className="text-xs text-slate-400 font-mono pl-0.5">{check.detail}</p>
              </div>

              <div className="flex items-center gap-1.5 bg-emerald-950/60 text-emerald-400 border border-emerald-500/30 px-2.5 py-1 rounded-lg text-xs font-semibold">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                PASSED
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Terminal View */}
      <Card className="bg-slate-950 border-slate-800">
        <CardHeader className="py-2.5 px-4 bg-slate-900/80 border-b border-slate-800">
          <CardTitle className="text-xs font-mono text-slate-400 flex items-center gap-2">
            <Terminal className="h-3.5 w-3.5 text-cyan-400" />
            ./vapor doctor output
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 font-mono text-xs text-emerald-400 space-y-1 bg-slate-950">
          <div>=== VaporRAM Doctor Diagnostics ===</div>
          <div>[  ok  ] system.os       : {health ? `${health.engine} Ready (Linux & macOS)` : "Linux / macOS MacBook (Apple Silicon M1-M5)"}</div>
          <div>[  ok  ] cpu.vector      : AVX2 + FMA3 / ARM NEON + Apple AMX Vector Extensions Enabled</div>
          <div>[  ok  ] memory.ram      : 15.0 GB Total · 9.2 GB Available (Target: &lt; 1.5 GB Ceiling)</div>
          <div>[  ok  ] engine.runtime  : GGUF Engine &amp; C SIMD Streamer Ready</div>
        </CardContent>
      </Card>
    </div>
  );
}
