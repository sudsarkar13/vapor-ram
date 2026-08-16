"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
	HardDrive,
	Download,
	RefreshCw,
	Power,
	Sliders,
	MemoryStick,
	Gauge,
	SlidersHorizontal,
	Sparkles,
	CheckCircle2,
	AlertTriangle,
	Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
	setModelPath,
	fetchPresets,
	SystemProgress,
	VaporPreset,
	ModelArchitecture,
} from "@/lib/api";

interface SidebarProps {
	currentPreset: string;
	setPreset: (preset: string) => void;
	progress: SystemProgress | null;
	onRefreshHealth: () => void;
}

const ALL_CONTEXT_OPTIONS = [
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

// Fallbacks only — real values arrive from the server's `architecture` block,
// which is read from the active model's config.json.
const FALLBACK_ARCH: ModelArchitecture = {
	n_layers: 42,
	hidden_dim: 2560,
	n_heads: 8,
	n_kv_heads: 2,
	head_dim: 256,
	kv_shared_layers: 18,
	sliding_window: 512,
	layer_buffer_mb: 140,
};

// llama.cpp allocates K and V separately, in f16 unless type_k/type_v are
// overridden -- not the int8 the planning docs assume. Measured against the
// running engine: n_ctx 4096 -> 6.80 GB RSS, 16384 -> 8.07 GB, i.e. ~108 KB
// per token. The previous constants counted K only, at 1 byte, over just the
// unique-KV layers, and so under-reported the cache by roughly 8x (216 MB
// shown against ~1.7 GB actually allocated at 16384).
const BYTES_PER_KV_ELEMENT = 2; // f16 K/V, llama.cpp default
const KV_TENSORS = 2; // K and V
const KV_SCALE_OVERHEAD = 1.125;

function kvBytes(ctx: number, arch: ModelArchitecture): number {
	// Every layer is counted, not just the unique-KV ones: llama.cpp reports
	// "using full-size SWA cache" for this architecture, so the sliding-window
	// layers are allocated at full context too.
	const elementsPerToken = arch.n_layers * arch.n_kv_heads * arch.head_dim;
	return (
		ctx *
		elementsPerToken *
		KV_TENSORS *
		BYTES_PER_KV_ELEMENT *
		KV_SCALE_OVERHEAD
	);
}

function formatBytes(bytes: number): string {
	if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
	if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
	return `${(bytes / 1024).toFixed(0)} KB`;
}

/** Projected KV growth on top of whatever the process already occupies. */
function projectMemory(
	ctx: number,
	ceilingGb: number,
	measuredRssMb: number | null,
	arch: ModelArchitecture,
) {
	const kv = kvBytes(ctx, arch);
	const measured = (measuredRssMb ?? 0) * 1024 ** 2;
	const projected = measured > 0 ? measured + kv : kv;
	const ceiling = ceilingGb * 1024 ** 3;
	return {
		kvBytes: kv,
		measuredBytes: measured,
		projectedBytes: projected,
		ceilingBytes: ceiling,
		fitsCeiling: projected <= ceiling,
		headroomBytes: ceiling - projected,
	};
}

function getRecommendedCeiling(availRamGb: number, totalRamGb: number): number {
	if (availRamGb <= 2.5) return 1.5;
	if (availRamGb <= 4.0) return 2.0;
	if (availRamGb <= 6.0) return 3.0;
	if (availRamGb <= 10.0) return 4.0;
	if (availRamGb <= 20.0) return 8.0;
	return Math.min(32.0, Math.floor(totalRamGb * 0.75));
}

export function Sidebar({
	currentPreset,
	setPreset,
	progress,
	onRefreshHealth,
}: SidebarProps) {
	// Server state is the source of truth. Local state holds only a pending edit,
	// which is preferred until the next poll confirms the server agrees. Deriving
	// rather than mirroring avoids a setState-in-effect cascade on every 3s poll.
	const [pendingCtx, setPendingCtx] = useState<number | null>(null);
	const [pendingCeiling, setPendingCeiling] = useState<number | null>(null);
	const [modelDirDraft, setModelDirDraft] = useState<string | null>(null);
	const [downloadRequested, setDownloadRequested] = useState(false);
	const [presets, setPresets] = useState<VaporPreset[]>([]);
	const [busy, setBusy] = useState(false);
	const [statusMsg, setStatusMsg] = useState("");
	const [statusIsError, setStatusIsError] = useState(false);

	const arch = progress?.architecture ?? FALLBACK_ARCH;
	const totalHostRamGb = progress?.total_ram_gb ?? 16.0;
	const availHostRamGb = progress?.avail_ram_gb ?? 8.0;
	const measuredRssMb = progress?.process_rss_mb ?? null;
	const safeMaxCtx = progress?.safe_max_context ?? 16384;
	const download = progress?.download_progress;
	const modelState = progress?.model_state;

	// A pending edit wins until the server reports the same value, at which point
	// the two agree and the server value is used.
	const serverCtx = progress?.n_ctx ?? 8192;
	const serverCeiling = progress?.ram_ceiling_gb ?? 1.5;
	const nCtx = pendingCtx !== null && pendingCtx !== serverCtx ? pendingCtx : serverCtx;
	const ramCeilingGb =
		pendingCeiling !== null && pendingCeiling !== serverCeiling
			? pendingCeiling
			: serverCeiling;
	// While the user is editing the field, their draft wins over the polled path.
	const modelDir = modelDirDraft ?? progress?.model_path ?? "";
	const modelDirTouched = modelDirDraft !== null;

	// The engine refuses anything above safe_max_context, so don't offer it.
	const contextOptions = ALL_CONTEXT_OPTIONS.filter((o) => o.value <= safeMaxCtx);

	const recommendedCeiling = getRecommendedCeiling(availHostRamGb, totalHostRamGb);
	const recommendedCtx = (() => {
		const budget = Math.min(availHostRamGb, ramCeilingGb);
		const fitting = contextOptions.filter(
			(o) => projectMemory(o.value, budget, measuredRssMb, arch).fitsCeiling,
		);
		return fitting.length ? fitting[fitting.length - 1].value : contextOptions[0]?.value ?? 4096;
	})();

	useEffect(() => {
		fetchPresets().then((p) => {
			if (p.length) setPresets(p);
		});
	}, []);

	const report = (msg: string, isError = false) => {
		setStatusMsg(msg);
		setStatusIsError(isError);
	};

	const saveSetting = useCallback(
		async (params: { n_ctx?: number; ram_ceiling_gb?: number }) => {
			setBusy(true);
			report("Applying settings…");
			if (params.n_ctx !== undefined) setPendingCtx(params.n_ctx);
			if (params.ram_ceiling_gb !== undefined) setPendingCeiling(params.ram_ceiling_gb);
			// model_dir is deliberately omitted: it has its own explicit action, so
			// changing the context window can never overwrite the active model path.
			const res = await updateServerConfig(params);
			setBusy(false);
			if (!res) {
				// Roll the optimistic value back; the server never took it.
				setPendingCtx(null);
				setPendingCeiling(null);
				return report("Server unreachable — settings not applied.", true);
			}
			if (res.n_ctx !== undefined) setPendingCtx(res.n_ctx);
			if (res.ram_ceiling_gb !== undefined) setPendingCeiling(res.ram_ceiling_gb);
			report(res.message || "Settings saved to vapor.json.", !!res.warnings?.length);
			onRefreshHealth();
		},
		[onRefreshHealth],
	);

	const applyModelDir = async () => {
		setBusy(true);
		report("Validating model directory…");
		const res = await setModelPath(modelDir);
		setBusy(false);
		if (!res) return report("Server unreachable.", true);
		// Drop the draft so the field follows the server again.
		if (!res.error) setModelDirDraft(null);
		report(res.message || "Model directory updated.", !!res.error);
		onRefreshHealth();
	};

	const startDownload = async () => {
		setDownloadRequested(true);
		report("Requesting GGUF download…");
		const res = await downloadModel(undefined, modelDir || undefined);
		if (!res) {
			setDownloadRequested(false);
			return report("Could not start download.", true);
		}
		report(res.message || "Download started.");
		onRefreshHealth();
	};

	const handleStop = async () => {
		if (confirm("Stop the VaporRAM engine server?")) {
			await stopServer();
			onRefreshHealth();
		}
	};

	const mem = projectMemory(nCtx, ramCeilingGb, measuredRssMb, arch);
	// Show the downloading state from the moment the user clicks until the server
	// reports a terminal status, without mirroring server state into local state.
	const downloadActive =
		download?.status === "downloading" ||
		(downloadRequested && (!download || download.status === "idle"));
	const ramUsedPct = measuredRssMb
		? Math.min(100, (measuredRssMb / (totalHostRamGb * 1024)) * 100)
		: 0;

	return (
		<aside className="w-full md:w-80 flex-shrink-0 bg-slate-950/80 border-b md:border-b-0 md:border-r border-cyan-500/20 p-4 space-y-4 overflow-y-auto font-sans text-slate-200">
			{/* Live memory telemetry */}
			<div className="rounded-xl border border-cyan-500/30 bg-slate-900/60 p-4 shadow-lg shadow-cyan-950/20">
				<div className="flex items-center justify-between mb-2">
					<span className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
						<MemoryStick className="h-4 w-4" />
						System Memory Inspector
					</span>
					<Badge
						variant="outline"
						className="bg-cyan-950 text-cyan-300 border-cyan-500/40 text-[10px] font-mono">
						Host: {totalHostRamGb.toFixed(1)} GB
					</Badge>
				</div>

				<div className="space-y-2 mt-3">
					<div className="flex justify-between text-xs font-mono">
						<span className="text-slate-400">Measured engine RSS:</span>
						<span className="font-bold text-cyan-300">
							{measuredRssMb !== null ? `${(measuredRssMb / 1024).toFixed(2)} GB` : "—"}
						</span>
					</div>

					<div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-cyan-500/20">
						<div
							className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 transition-all duration-500 rounded-full"
							style={{ width: `${ramUsedPct}%` }}
						/>
					</div>

					<div className="flex justify-between text-[11px] font-mono text-slate-500">
						<span>Free: {availHostRamGb.toFixed(1)} GB</span>
						<span>Ceiling target: {ramCeilingGb.toFixed(1)} GB</span>
					</div>

					{measuredRssMb !== null && measuredRssMb / 1024 > ramCeilingGb && (
						<p className="text-[10px] leading-snug text-amber-400 flex items-start gap-1">
							<AlertTriangle className="h-3 w-3 mt-px shrink-0" />
							Engine RSS exceeds the ceiling target. The ceiling is a planning
							guide — llama.cpp maps the full GGUF and is not capped by it.
						</p>
					)}
				</div>

				<div className="mt-3 pt-2.5 border-t border-cyan-500/20 flex items-center justify-between gap-2">
					<div className="text-[10px] font-mono text-cyan-300 flex items-center gap-1 min-w-0">
						<Sparkles className="h-3 w-3 text-amber-400 shrink-0" />
						<span className="truncate">
							Rec: {recommendedCeiling.toFixed(1)} GB · {recommendedCtx / 1024}K ctx
						</span>
					</div>
					<button
						onClick={() =>
							saveSetting({ n_ctx: recommendedCtx, ram_ceiling_gb: recommendedCeiling })
						}
						disabled={busy}
						className="text-[10px] bg-cyan-950 border border-cyan-500/40 hover:bg-cyan-900 disabled:opacity-40 text-cyan-200 px-2 py-0.5 rounded font-medium transition-colors shrink-0">
						Apply Optimal
					</button>
				</div>
			</div>

			{/* Model lifecycle */}
			{modelState && modelState.status !== "idle" && (
				<div
					className={`rounded-xl border p-3 text-xs font-mono flex items-start gap-2 ${
						modelState.status === "error"
							? "border-red-500/40 bg-red-950/30 text-red-300"
							: modelState.status === "loading"
								? "border-amber-500/40 bg-amber-950/30 text-amber-200"
								: "border-emerald-500/30 bg-emerald-950/20 text-emerald-300"
					}`}>
					{modelState.status === "loading" ? (
						<Loader2 className="h-3.5 w-3.5 mt-px shrink-0 animate-spin" />
					) : modelState.status === "error" ? (
						<AlertTriangle className="h-3.5 w-3.5 mt-px shrink-0" />
					) : (
						<CheckCircle2 className="h-3.5 w-3.5 mt-px shrink-0" />
					)}
					<span className="leading-snug break-words">{modelState.message}</span>
				</div>
			)}

			{/* RAM ceiling */}
			<div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
				<div className="flex items-center justify-between">
					<label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
						<SlidersHorizontal className="h-4 w-4 text-emerald-400" />
						RAM Ceiling Target
					</label>
					<Badge
						variant="outline"
						className="bg-emerald-950 text-emerald-400 border-emerald-500/30 text-[10px] font-mono">
						{ramCeilingGb.toFixed(1)} GB
					</Badge>
				</div>

				<Select
					value={String(ramCeilingGb)}
					onValueChange={(v) => saveSetting({ ram_ceiling_gb: Number(v) })}
					disabled={busy}>
					<SelectTrigger
						size="sm"
						className="w-full bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 h-9 px-2.5">
						<SelectValue />
					</SelectTrigger>
					<SelectContent className="bg-slate-900 border border-cyan-500/30 text-slate-100 rounded-lg shadow-2xl">
						{CEILING_OPTIONS.map((opt) => (
							<SelectItem key={opt.value} value={String(opt.value)} className="text-xs">
								{opt.label} {opt.value === recommendedCeiling ? "★" : ""}
							</SelectItem>
						))}
					</SelectContent>
				</Select>
				<p className="text-[10px] text-slate-500 leading-snug">
					Planning target for the KV-cache calculator below. It is not enforced by
					the GGUF backend.
				</p>
			</div>

			{/* Context window */}
			<div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
				<div className="flex items-center justify-between">
					<label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
						<Gauge className="h-4 w-4 text-amber-400" />
						Context Window
					</label>
					<Badge
						variant="outline"
						className="bg-slate-950 text-slate-400 border-slate-700 text-[10px] font-mono">
						engine max {safeMaxCtx.toLocaleString()}
					</Badge>
				</div>

				<Select
					value={String(nCtx)}
					onValueChange={(v) => saveSetting({ n_ctx: Number(v) })}
					disabled={busy}>
					<SelectTrigger
						size="sm"
						className="w-full bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 h-9 px-2.5">
						<SelectValue />
					</SelectTrigger>
					<SelectContent className="bg-slate-900 border border-cyan-500/30 text-slate-100 rounded-lg shadow-2xl max-h-[260px]">
						{contextOptions.map((opt) => {
							const m = projectMemory(opt.value, ramCeilingGb, measuredRssMb, arch);
							return (
								<SelectItem key={opt.value} value={String(opt.value)} className="text-xs">
									<span className="flex flex-col gap-0.5 leading-tight">
										<span className="font-medium">
											{opt.label} {opt.value === recommendedCtx ? "★" : ""}
										</span>
										<span className="text-[10px] font-mono text-slate-400">
											{formatBytes(m.kvBytes)} KV cache
										</span>
									</span>
								</SelectItem>
							);
						})}
					</SelectContent>
				</Select>

				<div className="flex items-center justify-between text-[11px] font-mono">
					<span className="text-slate-300 font-semibold">
						{busy ? "Applying…" : `${nCtx.toLocaleString()} tokens`}
					</span>
					<span className={mem.fitsCeiling ? "text-emerald-400" : "text-amber-400"}>
						{formatBytes(mem.kvBytes)} KV
					</span>
				</div>

				<p className="text-[10px] text-slate-500 leading-snug">
					KV estimate uses the active model&apos;s real geometry: {arch.n_layers} layers
					(full-size SWA cache), {arch.n_kv_heads} KV heads
					&times; {arch.head_dim}.
				</p>

				{statusMsg && (
					<p
						className={`text-[10px] leading-snug ${statusIsError ? "text-red-400" : "text-emerald-400"}`}>
						{statusMsg}
					</p>
				)}
			</div>

			{/* Model directory + download */}
			<div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
				<label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
					<HardDrive className="h-4 w-4 text-indigo-400" />
					Model Directory Target
				</label>

				<Input
					value={modelDir}
					onChange={(e) => {
						setModelDirDraft(e.target.value);
					}}
					placeholder="./models/gemma-4-E4B-it"
					className="bg-slate-950 border-slate-700 text-slate-200 font-mono text-[11px] focus:border-cyan-500"
				/>

				{modelDirTouched && (
					<Button
						onClick={applyModelDir}
						disabled={busy}
						size="sm"
						className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs h-8">
						Apply Directory
					</Button>
				)}

				{/* Detected model locations from the server-side scan */}
				{progress?.scanned_models && progress.scanned_models.length > 0 && (
					<div className="space-y-1 max-h-32 overflow-y-auto pr-1">
						{progress.scanned_models
							.filter((m) => m.available || m.is_active)
							.map((m) => (
								<button
									key={m.path}
									onClick={() => {
										setModelDirDraft(m.path);
									}}
									className={`w-full text-left px-2 py-1.5 rounded-md border text-[10px] font-mono transition-colors ${
										m.is_active
											? "border-cyan-500/50 bg-cyan-950/40 text-cyan-200"
											: "border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-700"
									}`}>
									<div className="truncate">{m.path}</div>
									<div className="text-[9px] text-slate-500">
										{m.has_gguf
											? `${m.gguf_name} · ${m.size_gb} GB`
											: "no .gguf present"}
										{m.is_active ? " · active" : ""}
									</div>
								</button>
							))}
					</div>
				)}

				<div className="flex gap-2">
					<Button
						onClick={startDownload}
						disabled={downloadActive || busy}
						size="sm"
						className="flex-1 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-semibold text-xs h-8 disabled:opacity-60">
						{downloadActive ? (
							<Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
						) : (
							<Download className="h-3.5 w-3.5 mr-1" />
						)}
						{downloadActive ? "Downloading…" : "HF Download"}
					</Button>

					<Button
						onClick={onRefreshHealth}
						variant="outline"
						size="sm"
						className="bg-slate-950 border-slate-700 text-slate-300 hover:bg-slate-800 text-xs h-8 px-2.5">
						<RefreshCw className="h-3.5 w-3.5" />
					</Button>
				</div>

				{/* Download progress meter — real bytes against real Content-Length */}
				{download && download.status !== "idle" && (
					<div className="space-y-1.5 pt-1">
						<div className="flex items-center justify-between text-[10px] font-mono">
							<span
								className={
									download.status === "error"
										? "text-red-400"
										: download.status === "completed"
											? "text-emerald-400"
											: "text-cyan-300"
								}>
								{download.status === "error"
									? "Failed"
									: download.status === "completed"
										? "Complete"
										: `${download.percent}%`}
							</span>
							{download.speed_mbps > 0 && (
								<span className="text-slate-400">
									{download.speed_mbps.toFixed(1)} MB/s
								</span>
							)}
						</div>

						<div
							className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800"
							role="progressbar"
							aria-valuenow={download.percent}
							aria-valuemin={0}
							aria-valuemax={100}
							aria-label="Model download progress">
							<div
								className={`h-full transition-all duration-500 rounded-full ${
									download.status === "error"
										? "bg-red-500"
										: download.status === "completed"
											? "bg-emerald-400"
											: "bg-gradient-to-r from-cyan-500 to-emerald-400"
								}`}
								style={{ width: `${Math.max(2, download.percent)}%` }}
							/>
						</div>

						<p className="text-[10px] font-mono text-slate-400 leading-snug break-words">
							{download.message}
						</p>

						{download.total_mb > 0 && (
							<p className="text-[10px] font-mono text-slate-500">
								{download.downloaded_mb.toFixed(0)} / {download.total_mb.toFixed(0)} MB
							</p>
						)}
					</div>
				)}
			</div>

			{/* Persona presets — sourced from presets/*.json via the server */}
			<div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
				<label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
					<Sliders className="h-4 w-4 text-purple-400" />
					Persona Presets
				</label>

				<div className="grid grid-cols-2 gap-1.5">
					{presets.map((p) => (
						<button
							key={p.id}
							onClick={() => setPreset(p.id)}
							title={p.system_instruction || "No system instruction"}
							className={`p-2 rounded-lg border text-left text-xs transition-all ${
								currentPreset === p.id
									? "bg-purple-950/60 border-purple-500/50 text-purple-200 font-semibold"
									: "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
							}`}>
							<div className="font-medium truncate">{p.name}</div>
							<div className="text-[10px] text-slate-500 font-mono">
								temp {p.temperature} · top_p {p.top_p}
							</div>
						</button>
					))}
					{presets.length === 0 && (
						<p className="col-span-2 text-[10px] text-slate-500 font-mono">
							Loading presets from server…
						</p>
					)}
				</div>
			</div>

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
