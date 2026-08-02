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
	SlidersHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	stopServer,
	downloadModel,
	updateServerConfig,
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
	{ value: 4096, label: "4K · default" },
	{ value: 8192, label: "8K · standard" },
	{ value: 16384, label: "16K · extended" },
	{ value: 32768, label: "32K · heavy" },
	{ value: 65536, label: "64K · extreme" },
	{ value: 131072, label: "128K · max context" },
];

const CEILING_OPTIONS = [
	{ value: 1.5, label: "1.5 GB · Default Low-RAM Target" },
	{ value: 2.0, label: "2.0 GB · Lightweight" },
	{ value: 3.0, label: "3.0 GB · Balanced" },
	{ value: 4.0, label: "4.0 GB · High Capacity" },
	{ value: 8.0, label: "8.0 GB · Performance" },
	{ value: 16.0, label: "16.0 GB · Workstation" },
	{ value: 32.0, label: "32.0 GB · Enterprise" },
];

// Gemma 4 E4B-it memory parameters
const MODEL_NUM_LAYERS = 42;
const MODEL_NUM_KV_HEADS = 2;
const MODEL_HEAD_DIM = 256;
const MODEL_NUM_KV_SHARED_LAYERS = 18;
const BYTES_PER_KV_ELEMENT = 1; // int8 K/V
const KV_SCALE_OVERHEAD = 1.125;
const ENGINE_BASE_RSS_GB = 0.28; // 280 MB layer double buffer + python glue
const MODEL_RSS_RESIDENT_GB = 0.20; // resident mmap pages

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

function computeMemory(ctx: number, ceilingGb: number, totalHostRamGb: number): MemBreakdown {
	const kv = kvBytes(ctx);
	const engine = ENGINE_BASE_RSS_GB * 1024 ** 3;
	const weights = MODEL_RSS_RESIDENT_GB * 1024 ** 3;
	const total = kv + engine + weights;
	const ceiling = ceilingGb * 1024 ** 3;
	const host = totalHostRamGb * 1024 ** 3;
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
	const [ramCeilingGb, setRamCeilingGb] = useState<number>(progress?.ram_ceiling_gb ?? 1.5);
	const [ctxBusy, setCtxBusy] = useState(false);
	const [ctxMsg, setCtxMsg] = useState("");

	const totalHostRamGb = progress?.total_ram_gb ?? 16.0;
	const availHostRamGb = progress?.avail_ram_gb ?? 8.0;

	// Sync from progress endpoint
	React.useEffect(() => {
		if (progress?.n_ctx) setNCtx(progress.n_ctx);
		if (progress?.ram_ceiling_gb) setRamCeilingGb(progress.ram_ceiling_gb);
	}, [progress?.n_ctx, progress?.ram_ceiling_gb]);

	const handleConfigUpdate = async (updatedCtx?: number, updatedCeilingGb?: number) => {
		const targetCtx = updatedCtx ?? nCtx;
		const targetCeiling = updatedCeilingGb ?? ramCeilingGb;

		setCtxBusy(true);
		setCtxMsg("Saving server settings & reallocating cache…");

		const res = await updateServerConfig({
			n_ctx: targetCtx,
			ram_ceiling_gb: targetCeiling,
			model_dir: modelDir,
		});

		setCtxBusy(false);

		if (!res) {
			setCtxMsg("Failed to update server configuration.");
			return;
		}

		if (res.n_ctx) setNCtx(res.n_ctx);
		if (res.ram_ceiling_gb) setRamCeilingGb(res.ram_ceiling_gb);
		setCtxMsg(res.message || "Server settings updated and saved to vapor.json.");
		onRefreshHealth();
	};

	const handleStop = async () => {
		if (confirm("Are you sure you want to stop the VaporRAM engine server?")) {
			await stopServer();
			onRefreshHealth();
		}
	};

	const mem = computeMemory(nCtx, ramCeilingGb, totalHostRamGb);
	const maxCtx = progress?.model_max_context ?? 131072;

	const breakdown = [
		{
			label: "int8 KV cache",
			value: mem.kvBytes,
			color: "bg-amber-400",
		},
		{
			label: "Engine + O_DIRECT buffer",
			value: mem.engineBaseBytes,
			color: "bg-cyan-400",
		},
		{
			label: "GGUF weights (resident)",
			value: mem.weightsBytes,
			color: "bg-indigo-400",
		},
	];

	return (
		<aside className="w-full md:w-80 flex-shrink-0 bg-slate-950/80 border-b md:border-b-0 md:border-r border-cyan-500/20 p-4 space-y-4 overflow-y-auto font-sans text-slate-200">
			{/* Memory Telemetry & System RAM Header */}
			<div className="rounded-xl border border-cyan-500/30 bg-slate-900/60 p-4 shadow-lg shadow-cyan-950/20">
				<div className="flex items-center justify-between mb-2">
					<span className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
						<MemoryStick className="h-4 w-4 text-cyan-400" />
						System Memory Inspector
					</span>
					<Badge variant="outline" className="bg-cyan-950 text-cyan-300 border-cyan-500/40 text-[10px] font-mono">
						Host: {totalHostRamGb.toFixed(1)} GB Total
					</Badge>
				</div>

				<div className="space-y-2 mt-3">
					<div className="flex justify-between text-xs font-mono">
						<span className="text-slate-400">Projected Peak RSS:</span>
						<span className={`font-bold ${mem.fitsCeiling ? "text-emerald-400" : "text-red-400"}`}>
							{formatBytes(mem.totalBytes)}
						</span>
					</div>

					<div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-cyan-500/20 flex">
						<div
							className={`h-full ${mem.fitsCeiling ? "bg-gradient-to-r from-cyan-500 to-emerald-400" : "bg-red-500"} transition-all duration-500 rounded-full`}
							style={{ width: `${Math.min(100, (mem.totalBytes / mem.ceilingBytes) * 100)}%` }}
						/>
					</div>

					<div className="flex justify-between text-[11px] font-mono text-slate-500">
						<span>Available Free: {availHostRamGb.toFixed(1)} GB</span>
						<span>Target Ceiling: {ramCeilingGb.toFixed(1)} GB</span>
					</div>
				</div>
			</div>

			{/* Target RAM Ceiling Selector */}
			<div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
				<div className="flex items-center justify-between">
					<label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
						<SlidersHorizontal className="h-4 w-4 text-emerald-400" />
						RAM Ceiling Target
					</label>
					<Badge variant="outline" className="bg-emerald-950 text-emerald-400 border-emerald-500/30 text-[10px] font-mono">
						{ramCeilingGb.toFixed(1)} GB
					</Badge>
				</div>

				<Select
					value={String(ramCeilingGb)}
					onValueChange={(v) => {
						const val = Number(v);
						setRamCeilingGb(val);
						handleConfigUpdate(nCtx, val);
					}}
					disabled={ctxBusy}>
					<SelectTrigger
						size="sm"
						className="w-full bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 h-9 px-2.5 focus:border-cyan-500/60">
						<SelectValue placeholder="Select RAM Ceiling Target">
							{`${ramCeilingGb.toFixed(1)} GB Ceiling Target`}
						</SelectValue>
					</SelectTrigger>
					<SelectContent className="bg-slate-900 border border-cyan-500/30 text-slate-100 rounded-lg shadow-2xl">
						{CEILING_OPTIONS.map((opt) => (
							<SelectItem key={opt.value} value={String(opt.value)} className="text-xs text-slate-200 hover:bg-cyan-500/20">
								{opt.label}
							</SelectItem>
						))}
					</SelectContent>
				</Select>
			</div>

			{/* Context Window Selector & Memory Calculator */}
			<div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
				<div className="flex items-center justify-between">
					<label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
						<Gauge className="h-4 w-4 text-amber-400" />
						Context Window
					</label>
					<Badge variant="outline" className="bg-slate-950 text-slate-400 border-slate-700 text-[10px] font-mono">
						max {maxCtx.toLocaleString()}
					</Badge>
				</div>

				<Select
					value={String(nCtx)}
					onValueChange={(v) => {
						const val = Number(v);
						setNCtx(val);
						handleConfigUpdate(val, ramCeilingGb);
					}}
					disabled={ctxBusy}>
					<SelectTrigger
						size="sm"
						className="w-full bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 h-9 px-2.5 focus:border-cyan-500/60">
						<SelectValue placeholder="Choose context window">
							{(() => {
								const opt = CONTEXT_OPTIONS.find((o) => o.value === nCtx);
								const m = computeMemory(nCtx, ramCeilingGb, totalHostRamGb);
								return `${opt ? opt.label : `${nCtx.toLocaleString()} tokens`} — ${formatBytes(m.totalBytes)} Peak RSS`;
							})()}
						</SelectValue>
					</SelectTrigger>
					<SelectContent className="bg-slate-900 border border-cyan-500/30 text-slate-100 rounded-lg shadow-2xl max-h-[260px]">
						{CONTEXT_OPTIONS.map((opt) => {
							const m = computeMemory(opt.value, ramCeilingGb, totalHostRamGb);
							const fits = m.totalBytes <= m.ceilingBytes;
							return (
								<SelectItem
									key={opt.value}
									value={String(opt.value)}
									className="text-xs text-slate-200 hover:bg-cyan-500/20">
									<span className="flex flex-col gap-0.5 leading-tight">
										<span className="font-medium">
											{opt.label}{" "}
											{!fits && (
												<span className="ml-1 text-[10px] font-mono text-red-400">
													&gt; {ramCeilingGb} GB
												</span>
											)}
										</span>
										<span className="text-[10px] font-mono text-slate-400">
											{formatBytes(m.totalBytes)} Peak RSS · {formatBytes(m.kvBytes)} KV
										</span>
									</span>
								</SelectItem>
							);
						})}
					</SelectContent>
				</Select>

				<div className="flex items-center justify-between text-[11px] font-mono">
					<span className="text-slate-300 font-semibold">
						{ctxBusy ? "Rebuilding KV cache…" : `${nCtx.toLocaleString()} tokens`}
					</span>
					<span className={mem.fitsCeiling ? "text-emerald-400" : "text-red-400"}>
						{mem.fitsCeiling ? `fits ${ramCeilingGb.toFixed(1)} GB ceiling` : `exceeds ${ramCeilingGb.toFixed(1)} GB ceiling`}
					</span>
				</div>

				{/* Breakdown list */}
				<ul className="space-y-1 text-[10px] font-mono pt-2 border-t border-slate-800">
					{breakdown.map((seg) => (
						<li key={seg.label} className="flex items-center justify-between gap-2">
							<span className="flex items-center gap-1.5 text-slate-300 min-w-0">
								<span className={`h-1.5 w-1.5 rounded-full ${seg.color} shrink-0`} />
								<span className="truncate">{seg.label}</span>
							</span>
							<span className="text-slate-100 font-semibold">{formatBytes(seg.value)}</span>
						</li>
					))}
					<li className="flex items-center justify-between text-slate-400 pt-1 border-t border-slate-800/60">
						<span>Headroom vs Ceiling</span>
						<span className={mem.headroomBytes >= 0 ? "text-emerald-300" : "text-red-300"}>
							{formatBytes(Math.abs(mem.headroomBytes))} {mem.headroomBytes >= 0 ? "free" : "over"}
						</span>
					</li>
				</ul>

				{ctxMsg && (
					<p className={`text-[10px] leading-snug ${ctxMsg.startsWith("Failed") ? "text-red-400" : "text-emerald-400"}`}>
						{ctxMsg}
					</p>
				)}
			</div>

			{/* Model Directory Target */}
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
						onClick={async () => {
							setIsDownloading(true);
							setDownloadMsg("Downloading model weights...");
							await downloadModel("google/gemma-4-E4B-it", modelDir);
							setIsDownloading(false);
						}}
						disabled={isDownloading || progress?.status === "downloading"}
						size="sm"
						className="flex-1 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-semibold text-xs h-8">
						<Download className="h-3.5 w-3.5 mr-1" />
						{isDownloading || progress?.status === "downloading" ? "Downloading..." : "HF Download"}
					</Button>

					<Button
						onClick={onRefreshHealth}
						variant="outline"
						size="sm"
						className="bg-slate-950 border-slate-700 text-slate-300 hover:bg-slate-800 text-xs h-8 px-2.5">
						<RefreshCw className="h-3.5 w-3.5" />
					</Button>
				</div>
			</div>

			{/* Persona Presets */}
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
							}`}>
							<div className="font-medium">{p.label}</div>
							<div className="text-[10px] text-slate-500 font-mono">temp: {p.temp}</div>
						</button>
					))}
				</div>
			</div>

			{/* Stop Server */}
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
