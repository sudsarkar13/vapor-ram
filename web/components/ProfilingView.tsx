"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Activity, RefreshCw, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface StatsPayload {
	version: string;
	model: string;
	backend: string;
	kv_slots: number;
	process_rss_mb: number | null;
	ram_usage_percent: number | null;
	total_ram_gb: number;
	avail_ram_gb: number;
	n_ctx: number;
	model_available: boolean;
	timings: {
		wall_time_ms?: number;
		first_token_ms?: number | null;
		completion_tokens?: number | null;
		tokens_per_second?: number | null;
	};
}

const getBaseUrl = () =>
	typeof window !== "undefined" && window.location.port === "3000"
		? "http://localhost:8000"
		: "";

export function ProfilingView() {
	const [stats, setStats] = useState<StatsPayload | null>(null);
	const [loading, setLoading] = useState(false);

	const load = useCallback(async () => {
		setLoading(true);
		try {
			const res = await fetch(`${getBaseUrl()}/v1/stats`, { cache: "no-store" });
			if (res.ok) setStats(await res.json());
		} catch {
			setStats(null);
		}
		setLoading(false);
	}, []);

	useEffect(() => {
		load();
		const id = setInterval(load, 5000);
		return () => clearInterval(id);
	}, [load]);

	const t = stats?.timings ?? {};
	const hasRun = t.completion_tokens != null || t.wall_time_ms != null;

	const metrics = [
		{
			label: "Engine RSS",
			value:
				stats?.process_rss_mb != null
					? `${(stats.process_rss_mb / 1024).toFixed(2)} GB`
					: "—",
			sub:
				stats?.ram_usage_percent != null
					? `${stats.ram_usage_percent.toFixed(1)}% of host RAM`
					: "measurement unavailable",
		},
		{
			label: "Host RAM free",
			value: stats ? `${stats.avail_ram_gb.toFixed(1)} GB` : "—",
			sub: stats ? `of ${stats.total_ram_gb.toFixed(1)} GB total` : "",
		},
		{
			label: "KV cache slots",
			value: stats ? stats.kv_slots.toLocaleString() : "—",
			sub: `context window ${stats?.n_ctx.toLocaleString() ?? "—"} tokens`,
		},
		{
			label: "Throughput",
			value: t.tokens_per_second != null ? `${t.tokens_per_second.toFixed(1)} tok/s` : "—",
			sub: hasRun ? "from last generation" : "no generation recorded yet",
		},
	];

	return (
		<div className="h-full bg-slate-950 p-6 overflow-y-auto space-y-6 text-slate-100 font-sans">
			<div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
				<div>
					<h2 className="text-xl font-bold text-cyan-400 flex items-center gap-2">
						<Activity className="h-5 w-5" />
						Runtime Profiling
					</h2>
					<p className="text-xs text-slate-400 mt-1">
						Measured from the running engine
						{stats?.backend ? ` · backend: ${stats.backend}` : ""}.
					</p>
				</div>
				<Button
					onClick={load}
					disabled={loading}
					size="sm"
					className="bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-semibold text-xs h-8">
					<RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
					Refresh
				</Button>
			</div>

			<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
				{metrics.map((m) => (
					<Card key={m.label} className="bg-slate-900/60 border-slate-800">
						<CardHeader className="pb-1.5">
							<CardTitle className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
								{m.label}
							</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="text-2xl font-bold text-cyan-300 font-mono">{m.value}</div>
							<div className="text-[10px] text-slate-500 font-mono mt-1">{m.sub}</div>
						</CardContent>
					</Card>
				))}
			</div>

			<Card className="bg-slate-900/40 border-slate-800">
				<CardHeader className="pb-2">
					<CardTitle className="text-sm font-bold text-slate-200 flex items-center justify-between">
						<span>Last Generation</span>
						<Badge
							variant="outline"
							className="bg-slate-950 text-slate-400 border-slate-700 text-[10px] font-mono">
							{hasRun ? "measured" : "awaiting first request"}
						</Badge>
					</CardTitle>
				</CardHeader>
				<CardContent>
					{hasRun ? (
						<div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
							<div>
								<div className="text-slate-500">Wall time</div>
								<div className="text-slate-100 font-bold">
									{t.wall_time_ms != null ? `${(t.wall_time_ms / 1000).toFixed(2)} s` : "—"}
								</div>
							</div>
							<div>
								<div className="text-slate-500">Time to first token</div>
								<div className="text-slate-100 font-bold">
									{t.first_token_ms != null
										? `${(t.first_token_ms / 1000).toFixed(2)} s`
										: "—"}
								</div>
							</div>
							<div>
								<div className="text-slate-500">Completion tokens</div>
								<div className="text-slate-100 font-bold">
									{t.completion_tokens ?? "—"}
								</div>
							</div>
							<div>
								<div className="text-slate-500">Tokens / second</div>
								<div className="text-slate-100 font-bold">
									{t.tokens_per_second?.toFixed(2) ?? "—"}
								</div>
							</div>
						</div>
					) : (
						<p className="text-xs text-slate-500 font-mono flex items-center gap-2">
							<Info className="h-3.5 w-3.5" />
							Send a chat message to record timings.
						</p>
					)}
				</CardContent>
			</Card>

			<Card className="bg-slate-900/40 border-amber-500/20">
				<CardContent className="p-4 text-[11px] text-slate-400 leading-relaxed flex gap-2">
					<Info className="h-4 w-4 text-amber-400 shrink-0 mt-px" />
					<span>
						Figures here are measured at runtime. Per-kernel attribution (attention
						vs. matmul vs. LM head) is not instrumented in the current GGUF backend,
						so it is not reported rather than estimated.
					</span>
				</CardContent>
			</Card>
		</div>
	);
}
