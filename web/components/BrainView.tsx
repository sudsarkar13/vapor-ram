"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
	Layers,
	HardDriveDownload,
	Gauge,
	Play,
	Loader2,
	AlertTriangle,
	FileBox,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	fetchCortex,
	runStreamBenchmark,
	CortexReport,
	GgufLayer,
	StreamBenchmark,
} from "@/lib/api";

const QUANT_COLORS: Record<string, string> = {
	Q4_K: "bg-cyan-500",
	Q5_K: "bg-indigo-500",
	Q6_K: "bg-violet-500",
	Q8_0: "bg-fuchsia-500",
	F32: "bg-slate-500",
	F16: "bg-slate-400",
	BF16: "bg-slate-400",
};

function fmtBytes(n: number | undefined | null): string {
	if (n === undefined || n === null) return "—";
	if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
	if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
	if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
	return `${n} B`;
}

function fmtHex(n: number): string {
	return `0x${n.toString(16)}`;
}

/** Fixed-width figure with its unit, so columns line up down the page. */
function Figure({
	label,
	value,
	unit,
	hint,
}: {
	label: string;
	value: string;
	unit?: string;
	hint?: string;
}) {
	return (
		<div className="min-w-0">
			<div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
				{label}
			</div>
			<div className="mt-1 flex items-baseline gap-1.5">
				<span className="text-xl font-semibold text-slate-100 tabular-nums">
					{value}
				</span>
				{unit && <span className="text-xs text-slate-500">{unit}</span>}
			</div>
			{hint && <div className="mt-0.5 text-[11px] text-slate-500">{hint}</div>}
		</div>
	);
}

/** One row per real transformer block, width proportional to its byte span. */
function LayerRow({
	layer,
	maxBytes,
	measuredMs,
	maxMs,
}: {
	layer: GgufLayer;
	maxBytes: number;
	measuredMs?: number;
	maxMs?: number;
}) {
	const widthPct = (layer.nbytes / maxBytes) * 100;
	const primary = layer.quant_types.find((q) => q.startsWith("Q")) ?? "F32";
	const color = QUANT_COLORS[primary] ?? "bg-slate-600";

	return (
		<div className="group flex items-center gap-3 py-1">
			<div className="w-10 shrink-0 text-right text-[11px] tabular-nums text-slate-500">
				{layer.layer}
			</div>
			<div className="relative h-5 flex-1 overflow-hidden rounded bg-slate-900">
				<div
					className={`h-full ${color} opacity-70 transition-opacity group-hover:opacity-100`}
					style={{ width: `${widthPct}%` }}
				/>
				{measuredMs !== undefined && maxMs ? (
					<div
						className="absolute inset-y-0 left-0 border-r-2 border-amber-400"
						style={{ width: `${(measuredMs / maxMs) * 100}%` }}
						title={`measured read ${measuredMs.toFixed(1)} ms`}
					/>
				) : null}
			</div>
			<div className="w-16 shrink-0 text-right text-[11px] tabular-nums text-slate-400">
				{(layer.nbytes / 1024 ** 2).toFixed(1)} MB
			</div>
			<div className="w-16 shrink-0 text-right text-[11px] tabular-nums text-amber-400/90">
				{measuredMs !== undefined ? `${measuredMs.toFixed(1)} ms` : ""}
			</div>
			<div className="hidden w-40 shrink-0 truncate text-[11px] text-slate-600 lg:block">
				{fmtHex(layer.offset)}
			</div>
		</div>
	);
}

export function BrainView() {
	const [report, setReport] = useState<CortexReport | null>(null);
	const [running, setRunning] = useState(false);
	const [benchError, setBenchError] = useState<string | null>(null);
	const [bench, setBench] = useState<StreamBenchmark | null>(null);

	// Polling lives inside the effect and guards on a cancelled flag, so no
	// state is set synchronously during the effect body or after unmount.
	useEffect(() => {
		let cancelled = false;
		const tick = async () => {
			const r = await fetchCortex();
			if (cancelled || !r) return;
			setReport(r);
			if (r.stream_benchmark) setBench(r.stream_benchmark);
		};
		tick();
		const id = setInterval(tick, 5000);
		return () => {
			cancelled = true;
			clearInterval(id);
		};
	}, []);

	const startBenchmark = useCallback(async () => {
		setRunning(true);
		setBenchError(null);
		const res = await runStreamBenchmark();
		setRunning(false);
		if (res?.stream_benchmark) setBench(res.stream_benchmark);
		else setBenchError(res?.message || "The streaming run did not complete.");
	}, []);

	const layers = report?.layer_report?.layers ?? [];
	const maxBytes = useMemo(
		() => layers.reduce((m, l) => Math.max(m, l.nbytes), 1),
		[layers],
	);
	const msByLayer = useMemo(() => {
		const map = new Map<number, number>();
		bench?.layers.forEach((l) => {
			if (l.ok && l.ms !== undefined) map.set(l.layer, l.ms);
		});
		return map;
	}, [bench]);
	const maxMs = useMemo(
		() => Math.max(1, ...Array.from(msByLayer.values())),
		[msByLayer],
	);

	const lr = report?.layer_report;

	return (
		<div className="h-full overflow-y-auto bg-slate-950 p-6">
			<div className="mx-auto max-w-6xl space-y-6">
				<header>
					<h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-100">
						<Layers className="h-6 w-6 text-cyan-400" />
						Weight Layout & Streaming
					</h1>
					<p className="mt-1 text-sm text-slate-400">
						Read from the GGUF tensor directory. Every offset, size and
						quantisation below is a value in the file, not an estimate.
					</p>
				</header>

				{!lr && (
					<div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-sm text-slate-400">
						{report?.layer_report_error
							? `Could not read the GGUF: ${report.layer_report_error}`
							: "No GGUF model is active. Download or select one from the sidebar."}
					</div>
				)}

				{lr && (
					<>
						{/* --- what is in the file ------------------------------- */}
						<section className="rounded-lg border border-slate-800 bg-slate-900/40 p-5">
							<div className="mb-4 flex items-center gap-2">
								<FileBox className="h-4 w-4 text-slate-500" />
								<h2 className="text-sm font-semibold text-slate-200">
									{lr.file}
								</h2>
								<span className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-400">
									{lr.architecture} · GGUF v{lr.gguf_version}
								</span>
							</div>
							<div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-5">
								<Figure
									label="Blocks"
									value={String(lr.n_layers)}
									hint={
										lr.block_count_meta === lr.n_layers
											? "matches file metadata"
											: `metadata says ${lr.block_count_meta}`
									}
								/>
								<Figure label="Tensors" value={String(lr.n_tensors)} />
								<Figure
									label="Streamable"
									value={fmtBytes(lr.layer_bytes_total)}
									hint="all blocks"
								/>
								<Figure
									label="Resident"
									value={fmtBytes(lr.resident_bytes)}
									hint="embeddings, norms"
								/>
								<Figure label="File" value={fmtBytes(lr.file_size)} />
							</div>

							<div className="mt-5">
								<div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
									Quantisation
								</div>
								<div className="flex h-2 overflow-hidden rounded">
									{lr.quant_summary.map((q) => (
										<div
											key={q.type}
											className={QUANT_COLORS[q.type] ?? "bg-slate-600"}
											style={{ width: `${(q.bytes / lr.file_size) * 100}%` }}
											title={`${q.type}: ${fmtBytes(q.bytes)} across ${q.tensors} tensors`}
										/>
									))}
								</div>
								<div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
									{lr.quant_summary.map((q) => (
										<div
											key={q.type}
											className="flex items-center gap-1.5 text-[11px] text-slate-400">
											<span
												className={`h-2 w-2 rounded-sm ${QUANT_COLORS[q.type] ?? "bg-slate-600"}`}
											/>
											<span className="text-slate-300">{q.type}</span>
											<span className="tabular-nums">{fmtBytes(q.bytes)}</span>
										</div>
									))}
								</div>
							</div>
						</section>

						{/* --- measurement --------------------------------------- */}
						<section className="rounded-lg border border-slate-800 bg-slate-900/40 p-5">
							<div className="mb-4 flex flex-wrap items-center justify-between gap-3">
								<div>
									<h2 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
										<Gauge className="h-4 w-4 text-amber-400" />
										O_DIRECT streaming
									</h2>
									<p className="mt-1 text-xs text-slate-500">
										Reads each block&apos;s real byte range, bypassing the page
										cache. Moves {fmtBytes(lr.layer_bytes_total)} from disk.
									</p>
								</div>
								<Button
									onClick={startBenchmark}
									disabled={running}
									className="bg-amber-600 text-slate-950 hover:bg-amber-500">
									{running ? (
										<>
											<Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
											Streaming…
										</>
									) : (
										<>
											<Play className="mr-1.5 h-4 w-4" />
											Measure
										</>
									)}
								</Button>
							</div>

							{benchError && (
								<div className="mb-4 flex items-start gap-2 rounded border border-red-500/30 bg-red-950/40 p-3 text-xs text-red-300">
									<AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
									<span>{benchError}</span>
								</div>
							)}

							{bench ? (
								<div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-5">
									<Figure
										label="Throughput"
										value={bench.mb_per_s.toFixed(0)}
										unit="MB/s"
										hint={bench.o_direct ? "O_DIRECT" : "buffered fallback"}
									/>
									<Figure
										label="Per block"
										value={bench.layer_ms_mean?.toFixed(1) ?? "—"}
										unit="ms"
										hint={
											bench.layer_ms_min !== undefined
												? `${bench.layer_ms_min.toFixed(0)}–${bench.layer_ms_max?.toFixed(0)} ms`
												: undefined
										}
									/>
									<Figure
										label="Blocks read"
										value={String(bench.layers_read)}
										hint={bench.failures ? `${bench.failures} failed` : "no failures"}
									/>
									<Figure
										label="Total"
										value={(bench.total_ms / 1000).toFixed(2)}
										unit="s"
										hint={fmtBytes(bench.total_bytes)}
									/>
									<Figure
										label="If streamed"
										value={bench.seconds_per_token_if_streamed?.toFixed(2) ?? "—"}
										unit="s/token"
										hint="every block, per token"
									/>
								</div>
							) : (
								<p className="text-xs text-slate-500">
									Not measured yet.
								</p>
							)}

							{bench?.seconds_per_token_if_streamed ? (
								<p className="mt-4 border-t border-slate-800 pt-4 text-xs leading-relaxed text-slate-400">
									At the measured {bench.mb_per_s.toFixed(0)} MB/s, streaming
									every block for each token would cost{" "}
									<span className="text-amber-400">
										{bench.seconds_per_token_if_streamed.toFixed(2)}s per token
									</span>{" "}
									— about{" "}
									{(1 / bench.seconds_per_token_if_streamed).toFixed(2)} tok/s.
									Generation currently runs through llama.cpp, which memory-maps
									the file and keeps the weights resident instead. That is the
									trade the RAM ceiling would buy.
								</p>
							) : null}
						</section>

						{/* --- the map ------------------------------------------- */}
						<section className="rounded-lg border border-slate-800 bg-slate-900/40 p-5">
							<div className="mb-3 flex items-center gap-2">
								<HardDriveDownload className="h-4 w-4 text-slate-500" />
								<h2 className="text-sm font-semibold text-slate-200">
									Block map
								</h2>
								<span className="text-[11px] text-slate-500">
									bar = byte span
									{msByLayer.size > 0 && " · amber = measured read time"}
								</span>
							</div>
							<div className="flex items-center gap-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
								<div className="w-10 shrink-0 text-right">Blk</div>
								<div className="flex-1">Span</div>
								<div className="w-16 shrink-0 text-right">Size</div>
								<div className="w-16 shrink-0 text-right">Read</div>
								<div className="hidden w-40 shrink-0 lg:block">Offset</div>
							</div>
							<div className="divide-y divide-slate-800/50">
								{layers.map((l) => (
									<LayerRow
										key={l.layer}
										layer={l}
										maxBytes={maxBytes}
										measuredMs={msByLayer.get(l.layer)}
										maxMs={maxMs}
									/>
								))}
							</div>
							{layers[0] && (
								<p className="mt-4 border-t border-slate-800 pt-4 text-[11px] leading-relaxed text-slate-500">
									Each block holds {layers[0].tensor_count} tensors. Block data
									begins at {fmtHex(layers[0].offset)} — the{" "}
									{fmtBytes(layers[0].offset)} before it is the token embedding
									tables, which stay resident rather than streaming.
								</p>
							)}
						</section>
					</>
				)}
			</div>
		</div>
	);
}
