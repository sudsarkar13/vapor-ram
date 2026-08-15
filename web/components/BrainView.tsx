"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Cpu, HardDrive, Layers, MemoryStick, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchHealth, VaporHealth } from "@/lib/api";

export function BrainView() {
	const [health, setHealth] = useState<VaporHealth | null>(null);

	const load = useCallback(async () => {
		setHealth(await fetchHealth());
	}, []);

	useEffect(() => {
		let cancelled = false;
		const tick = () =>
			fetchHealth().then((h) => {
				if (!cancelled) setHealth(h);
			});
		tick();
		const id = setInterval(tick, 5000);
		return () => {
			cancelled = true;
			clearInterval(id);
		};
	}, []);

	const arch = health?.architecture;
	const layers = arch?.n_layers ?? 0;
	const uniqueKv = arch ? arch.n_layers - arch.kv_shared_layers : 0;
	const ready = health?.model_state.status === "ready";

	return (
		<div className="h-full bg-slate-950 p-6 overflow-y-auto space-y-6 text-slate-100 font-sans">
			<div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
				<div>
					<h2 className="text-xl font-bold text-cyan-400 flex items-center gap-2">
						<Cpu className="h-5 w-5" />
						Model Architecture
					</h2>
					<p className="text-xs text-slate-400 mt-1">
						Read from the active model&apos;s{" "}
						<span className="font-mono text-cyan-300">config.json</span>
						{health?.gguf_file ? ` · ${health.gguf_file}` : ""}.
					</p>
				</div>

				<Badge
					variant="outline"
					className={
						ready
							? "bg-emerald-950 text-emerald-400 border-emerald-500/30 text-xs"
							: "bg-slate-900 text-slate-400 border-slate-700 text-xs"
					}>
					{health?.model_state.status ?? "unknown"}
				</Badge>
			</div>

			{!health && (
				<Card className="bg-slate-900/60 border-slate-800">
					<CardContent className="p-4 text-xs text-slate-400 font-mono">
						Engine unreachable.
					</CardContent>
				</Card>
			)}

			{arch && (
				<>
					<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
						<Card className="bg-slate-900/60 border-cyan-500/30">
							<CardHeader className="pb-2">
								<CardTitle className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
									<HardDrive className="h-4 w-4" />
									Transformer Stack
								</CardTitle>
							</CardHeader>
							<CardContent className="space-y-1 text-xs font-mono">
								<Row label="Hidden layers" value={String(arch.n_layers)} />
								<Row label="Hidden dim" value={String(arch.hidden_dim)} />
								<Row label="Attention heads" value={String(arch.n_heads)} />
							</CardContent>
						</Card>

						<Card className="bg-slate-900/60 border-indigo-500/30">
							<CardHeader className="pb-2">
								<CardTitle className="text-xs font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
									<MemoryStick className="h-4 w-4" />
									KV Geometry
								</CardTitle>
							</CardHeader>
							<CardContent className="space-y-1 text-xs font-mono">
								<Row label="KV heads" value={String(arch.n_kv_heads)} />
								<Row label="Head dim" value={String(arch.head_dim)} />
								<Row
									label="Unique KV layers"
									value={`${uniqueKv} of ${arch.n_layers}`}
								/>
							</CardContent>
						</Card>

						<Card className="bg-slate-900/60 border-purple-500/30">
							<CardHeader className="pb-2">
								<CardTitle className="text-xs font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1.5">
									<Layers className="h-4 w-4" />
									Active Context
								</CardTitle>
							</CardHeader>
							<CardContent className="space-y-1 text-xs font-mono">
								<Row label="Context window" value={health.n_ctx.toLocaleString()} />
								<Row
									label="Engine maximum"
									value={health.safe_max_context.toLocaleString()}
								/>
								<Row label="Sliding window" value={String(arch.sliding_window)} />
							</CardContent>
						</Card>
					</div>

					<Card className="bg-slate-900/40 border-slate-800">
						<CardHeader>
							<CardTitle className="text-sm font-bold text-slate-200">
								Layer Map ({layers} layers)
							</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="grid grid-cols-4 sm:grid-cols-8 lg:grid-cols-12 gap-2">
								{Array.from({ length: layers }).map((_, idx) => {
									const sharesKv = idx >= layers - arch.kv_shared_layers;
									return (
										<div
											key={idx}
											title={
												sharesKv
													? `Layer ${idx + 1} — shares KV cache`
													: `Layer ${idx + 1} — own KV cache`
											}
											className={`p-2 rounded-lg border text-center transition-colors ${
												sharesKv
													? "border-slate-800 bg-slate-950/80"
													: "border-cyan-500/30 bg-cyan-950/20"
											}`}>
											<div className="text-[10px] font-mono text-slate-500">
												{idx + 1}
											</div>
										</div>
									);
								})}
							</div>
							<div className="flex items-center gap-4 mt-4 text-[10px] font-mono text-slate-500">
								<span className="flex items-center gap-1.5">
									<span className="h-2 w-2 rounded-sm border border-cyan-500/30 bg-cyan-950/20" />
									own KV cache ({uniqueKv})
								</span>
								<span className="flex items-center gap-1.5">
									<span className="h-2 w-2 rounded-sm border border-slate-800 bg-slate-950" />
									shared KV ({arch.kv_shared_layers})
								</span>
							</div>
						</CardContent>
					</Card>

					<Card className="bg-slate-900/40 border-amber-500/20">
						<CardContent className="p-4 text-[11px] text-slate-400 leading-relaxed flex gap-2">
							<Info className="h-4 w-4 text-amber-400 shrink-0 mt-px" />
							<span>
								Generation currently runs through llama.cpp, which memory-maps the
								full GGUF file. The O_DIRECT sequential layer streamer in{" "}
								<span className="font-mono text-slate-300">c/streaming_io.c</span> is
								built but not yet wired into the token path, so per-layer streaming
								state is not reported here.
							</span>
						</CardContent>
					</Card>
				</>
			)}
		</div>
	);
}

function Row({ label, value }: { label: string; value: string }) {
	return (
		<div className="flex justify-between">
			<span className="text-slate-400">{label}:</span>
			<span className="text-slate-100 font-semibold">{value}</span>
		</div>
	);
}
