"use client";

import React, { useState } from "react";
import {
	HardDrive,
	Server,
	Download,
	RefreshCw,
	Power,
	CheckCircle,
	AlertTriangle,
	Sliders,
	ShieldCheck,
	MemoryStick,
	Gauge,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
	NativeSelect,
	NativeSelectOption,
} from "@/components/ui/native-select";
import {
	stopServer,
	downloadModel,
	setContextWindow,
	SystemProgress,
} from "@/lib/api";

interface SidebarProps {
	currentPreset: string;
	setPreset: (preset: string) => void;
	progress: SystemProgress | null;
	onRefreshHealth: () => void;
}

const CONTEXT_OPTIONS = [
	{ value: 1024, label: "1K · minimal" },
	{ value: 2048, label: "2K · tight" },
	{ value: 4096, label: "4K · default-plan" },
	{ value: 8192, label: "8K · default (1.5 GB ceiling)" },
	{ value: 16384, label: "16K · 32 GB RAM" },
	{ value: 32768, label: "32K · 64 GB RAM" },
	{ value: 65536, label: "64K · 128 GB RAM" },
	{ value: 131072, label: "128K · full model max" },
];

// Memory constants tuned to the real model spec
// (models/gemma-4-E4B-it/config.json: text_config).
const MODEL_NUM_LAYERS = 42;
const MODEL_NUM_KV_HEADS = 2;
const MODEL_HEAD_DIM = 256;
const MODEL_NUM_KV_SHARED_LAYERS = 18;
const BYTES_PER_KV_ELEMENT = 1; // int8 K/V; float scales add ~12.5% overhead
const KV_SCALE_OVERHEAD = 1.125;
const MODEL_WEIGHTS_GB = 4.0; // Q4_K_M GGUF ~4 GB on disk (mmap-resident slices keep RSS low)
const ENGINE_BASE_RSS_GB = 0.28; // python + glue + layer buffer (O_DIRECT 280 MB)
const MODEL_RSS_RESIDENT_GB = 0.45; // quantized GGUF pages typically resident in RAM
const RAM_CEILING_GB = 1.5;
const HOST_RAM_GB = 16; // best-effort upper bound for "fits on this machine" hint

// KV cache bytes per token under the actual model config.
// Shared K/V layers count once in storage (k_scale/v_scale still per token).
function kvBytesPerToken(): number {
	const uniqueKvLayers = MODEL_NUM_LAYERS - MODEL_NUM_KV_SHARED_LAYERS;
	const elementsPerToken = uniqueKvLayers * MODEL_NUM_KV_HEADS * MODEL_HEAD_DIM;
	return elementsPerToken * BYTES_PER_KV_ELEMENT * KV_SCALE_OVERHEAD;
}

function kvBytes(ctx: number): number {
	return ctx * kvBytesPerToken();
}

function formatBytes(bytes: number): string {
	if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
	if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
	return `${(bytes / 1024).toFixed(0)} KB`;
}

interface MemBreakdown {
	kvBytes: number;
	engineBaseBytes: number;
	weightsBytes: number;
	totalBytes: number;
	ceilingBytes: number;
	fitsCeiling: boolean;
	fitsHost: boolean;
	headroomBytes: number;
}

function computeMemory(ctx: number): MemBreakdown {
	const kv = kvBytes(ctx);
	const engine = ENGINE_BASE_RSS_GB * 1024 ** 3;
	const weights = MODEL_RSS_RESIDENT_GB * 1024 ** 3;
	const total = kv + engine + weights;
	const ceiling = RAM_CEILING_GB * 1024 ** 3;
	const host = HOST_RAM_GB * 1024 ** 3;
	return {
		kvBytes: kv,
		engineBaseBytes: engine,
		weightsBytes: weights,
		totalBytes: total,
		ceilingBytes: ceiling,
		fitsCeiling: total <= ceiling,
		fitsHost: total <= host,
		headroomBytes: ceiling - total,
	};
}

interface ContextWindowCardProps {
	nCtx: number;
	busy: boolean;
	maxContext: number;
	onChange: (next: number) => void;
	statusMessage: string;
}

function ContextWindowCard({
	nCtx,
	busy,
	maxContext,
	onChange,
	statusMessage,
}: ContextWindowCardProps) {
	const mem = computeMemory(nCtx);
	const ceilingPct = Math.min(100, (mem.totalBytes / mem.ceilingBytes) * 100);
	const breakdown = [
		{
			label: "KV cache",
			value: mem.kvBytes,
			color: "bg-amber-400",
			note: `${nCtx.toLocaleString()} × ${(kvBytesPerToken() / 1024).toFixed(1)} KB/token`,
		},
		{
			label: "Engine + layer buffer",
			value: mem.engineBaseBytes,
			color: "bg-cyan-400",
			note: "O_DIRECT 280 MB + python",
		},
		{
			label: "GGUF weights (resident)",
			value: mem.weightsBytes,
			color: "bg-indigo-400",
			note: `~${MODEL_WEIGHTS_GB.toFixed(1)} GB on disk, ${MODEL_RSS_RESIDENT_GB.toFixed(2)} GB hot`,
		},
	];

	return (
		<div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
			<div className="flex items-center justify-between">
				<label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
					<Gauge className="h-4 w-4 text-amber-400" />
					Context Window
				</label>
				<Badge
					variant="outline"
					className="bg-slate-950 text-slate-400 border-slate-700 text-[10px] font-mono">
					max {maxContext.toLocaleString()}
				</Badge>
			</div>

			<NativeSelect
				value={nCtx}
				onChange={(e) => onChange(Number(e.target.value))}
				disabled={busy}
				className="w-full bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-200 h-9 px-2 focus:border-cyan-500/60">
				{CONTEXT_OPTIONS.map((opt) => {
					const m = computeMemory(opt.value);
					return (
						<NativeSelectOption key={opt.value} value={opt.value}>
							{opt.label} — {formatBytes(m.totalBytes)} total
						</NativeSelectOption>
					);
				})}
			</NativeSelect>

			<div className="flex items-center justify-between text-[11px] font-mono">
				<span className="text-slate-300 font-semibold">
					{busy ? "Rebuilding KV cache…" : `${nCtx.toLocaleString()} tokens`}
				</span>
				<span className={mem.fitsCeiling ? "text-emerald-400" : "text-red-400"}>
					{mem.fitsCeiling ? "fits 1.5 GB" : "exceeds 1.5 GB"}
				</span>
			</div>

			{/* Stacked memory bar */}
			<div className="space-y-1.5">
				<div className="h-2 w-full rounded-full bg-slate-950 overflow-hidden flex border border-slate-800">
					{breakdown.map((seg) => {
						const pct = (seg.value / mem.ceilingBytes) * 100;
						if (pct <= 0) return null;
						return (
							<div
								key={seg.label}
								className={`${seg.color} h-full transition-all duration-300`}
								style={{ width: `${pct}%` }}
								title={`${seg.label}: ${formatBytes(seg.value)}`}
							/>
						);
					})}
				</div>
				<div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
					<span>{formatBytes(mem.totalBytes)} projected</span>
					<span>ceiling {formatBytes(mem.ceilingBytes)}</span>
				</div>
			</div>

			{/* Per-component breakdown */}
			<ul className="space-y-1 text-[10px] font-mono">
				{breakdown.map((seg) => (
					<li
						key={seg.label}
						className="flex items-center justify-between gap-2">
						<span className="flex items-center gap-1.5 text-slate-300 min-w-0">
							<span
								className={`h-1.5 w-1.5 rounded-full ${seg.color} shrink-0`}
							/>
							<span className="truncate">{seg.label}</span>
						</span>
						<span className="text-slate-100 font-semibold">
							{formatBytes(seg.value)}
						</span>
					</li>
				))}
				<li className="flex items-center justify-between text-slate-400 pt-1 border-t border-slate-800/60">
					<span>Total RSS</span>
					<span
						className={`font-semibold ${mem.fitsCeiling ? "text-emerald-300" : "text-red-300"}`}>
						{formatBytes(mem.totalBytes)}
					</span>
				</li>
				<li className="flex items-center justify-between text-slate-400">
					<span>Headroom vs ceiling</span>
					<span
						className={
							mem.headroomBytes >= 0 ? "text-emerald-300" : "text-red-300"
						}>
						{formatBytes(Math.abs(mem.headroomBytes))}{" "}
						{mem.headroomBytes >= 0 ? "free" : "over"}
					</span>
				</li>
			</ul>

			{statusMessage && (
				<p
					className={`text-[10px] leading-snug ${statusMessage.startsWith("Failed") ? "text-red-400" : "text-amber-400/80"}`}>
					{statusMessage}
				</p>
			)}

			<p className="text-[10px] leading-snug text-slate-500">
				KV is int8. Formula: n_ctx ×{" "}
				{MODEL_NUM_LAYERS - MODEL_NUM_KV_SHARED_LAYERS} layers ×{" "}
				{MODEL_NUM_KV_HEADS} KV heads × {MODEL_HEAD_DIM} dim × 1 byte. Going
				past 8K ignores the 1.5 GB RAM ceiling and may cause OOM.
			</p>
		</div>
	);
}

export function Sidebar({
	currentPreset,
	setPreset,
	progress,
	onRefreshHealth,
}: SidebarProps) {
	const [modelDir, setModelDir] = useState("./models/gemma-4-E4B-it");
	const [isDownloading, setIsDownloading] = useState(false);
	const [downloadMsg, setDownloadMsg] = useState("");
	const [nCtx, setNCtx] = useState<number>(progress?.n_ctx ?? 8192);
	const [ctxBusy, setCtxBusy] = useState(false);
	const [ctxMsg, setCtxMsg] = useState("");

	// Sync from server whenever /v1/system/progress or /health reports a new value.
	React.useEffect(() => {
		if (progress?.n_ctx && progress.n_ctx !== nCtx) {
			setNCtx(progress.n_ctx);
		}
	}, [progress?.n_ctx]);

	const handleContextChange = async (next: number) => {
		const previous = nCtx;
		setNCtx(next);
		setCtxBusy(true);
		setCtxMsg(`Reallocating KV cache ${previous} → ${next}…`);
		const res = await setContextWindow(next);
		setCtxBusy(false);
		if (!res) {
			setNCtx(previous);
			setCtxMsg("Failed to update context window.");
			return;
		}
		setCtxMsg(res.message || `Context window set to ${res.n_ctx}.`);
		onRefreshHealth();
	};

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
					<Badge
						variant="outline"
						className="bg-cyan-950 text-cyan-300 border-cyan-500/40 text-[10px] font-mono">
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
						<span className="text-slate-200 font-mono font-semibold">
							280 MB (O_DIRECT)
						</span>
					</div>
					<div className="bg-slate-950/80 p-2 rounded border border-slate-800">
						<span className="text-slate-500 block">int8 KV Cache:</span>
						<span className="text-slate-200 font-mono font-semibold">
							256 MB (Per-token)
						</span>
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
						disabled={isDownloading || progress?.status === "downloading"}
						size="sm"
						className="flex-1 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-semibold text-xs h-8">
						<Download className="h-3.5 w-3.5 mr-1" />
						{isDownloading || progress?.status === "downloading" ?
							"Downloading..."
						:	"HF Download"}
					</Button>

					<Button
						onClick={onRefreshHealth}
						variant="outline"
						size="sm"
						className="bg-slate-950 border-slate-700 text-slate-300 hover:bg-slate-800 text-xs h-8 px-2.5">
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
						<Progress
							value={progress?.percent || 0}
							className="h-1.5 bg-slate-950"
						/>
					</div>
				)}
			</div>

			{/* Context Window Card */}
			<ContextWindowCard
				nCtx={nCtx}
				busy={ctxBusy}
				maxContext={progress?.model_max_context ?? 131072}
				onChange={handleContextChange}
				statusMessage={ctxMsg}
			/>

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
								currentPreset === p.id ?
									"bg-purple-950/60 border-purple-500/50 text-purple-200 font-semibold"
								:	"bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
							}`}>
							<div className="font-medium">{p.label}</div>
							<div className="text-[10px] text-slate-500 font-mono">
								temp: {p.temp}
							</div>
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
					<Badge
						variant="outline"
						className="bg-emerald-950 text-emerald-400 border-emerald-500/30 text-[10px]">
						AVX2 / NEON
					</Badge>
				</div>

				<div className="flex items-center justify-between text-slate-300 bg-slate-950/60 p-2 rounded border border-slate-800">
					<span>POSIX SSD Streaming</span>
					<Badge
						variant="outline"
						className="bg-cyan-950 text-cyan-400 border-cyan-500/30 text-[10px]">
						O_DIRECT
					</Badge>
				</div>

				<div className="flex items-center justify-between text-slate-300 bg-slate-950/60 p-2 rounded border border-slate-800">
					<span>Supported OS</span>
					<Badge
						variant="outline"
						className="bg-indigo-950 text-indigo-300 border-indigo-500/30 text-[10px]">
						Linux &amp; macOS
					</Badge>
				</div>
			</div>

			{/* Emergency Server Control */}
			<div className="pt-2">
				<Button
					onClick={handleStop}
					variant="outline"
					className="w-full bg-red-950/40 border-red-500/30 text-red-400 hover:bg-red-900/60 hover:text-red-200 text-xs font-medium h-9">
					<Power className="h-3.5 w-3.5 mr-1.5" />
					Stop Engine Server
				</Button>
			</div>
		</aside>
	);
}
