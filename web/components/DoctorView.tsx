"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
	Terminal,
	CheckCircle2,
	AlertCircle,
	AlertTriangle,
	RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchDoctor, DoctorReport } from "@/lib/api";

const CHECK_LABELS: Record<string, string> = {
	"system.os": "Operating System & Hardware",
	"cpu.vector": "SIMD Vector Acceleration",
	"memory.ram": "RAM Memory Ceiling Budget",
	"engine.runtime": "Model Execution Runtime",
};

const STATUS_STYLES = {
	ok: {
		wrap: "bg-emerald-950/60 text-emerald-400 border-emerald-500/30",
		Icon: CheckCircle2,
		label: "PASSED",
	},
	warn: {
		wrap: "bg-amber-950/60 text-amber-400 border-amber-500/30",
		Icon: AlertTriangle,
		label: "WARNING",
	},
	fail: {
		wrap: "bg-red-950/60 text-red-400 border-red-500/30",
		Icon: AlertCircle,
		label: "FAILED",
	},
} as const;

export function DoctorView() {
	const [report, setReport] = useState<DoctorReport | null>(null);
	const [loading, setLoading] = useState(false);
	const [offline, setOffline] = useState(false);

	const runDiagnostics = useCallback(async () => {
		setLoading(true);
		const data = await fetchDoctor();
		setReport(data);
		setOffline(data === null);
		setLoading(false);
	}, []);

	useEffect(() => {
		runDiagnostics();
	}, [runDiagnostics]);

	return (
		<div className="h-full bg-slate-950 p-6 overflow-y-auto space-y-6 text-slate-100 font-sans">
			<div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
				<div>
					<h2 className="text-xl font-bold text-cyan-400 flex items-center gap-2">
						<Terminal className="h-5 w-5" />
						VaporRAM Doctor Diagnostics
					</h2>
					<p className="text-xs text-slate-400 mt-1">
						Live hardware inspection from the engine host
						{report ? ` · engine v${report.version}` : ""}.
					</p>
				</div>

				<Button
					onClick={runDiagnostics}
					disabled={loading}
					size="sm"
					className="bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-semibold text-xs h-8">
					<RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
					Run Diagnostics
				</Button>
			</div>

			{offline && (
				<Card className="bg-red-950/30 border-red-500/40">
					<CardContent className="p-4 text-sm text-red-300 flex items-center gap-2">
						<AlertCircle className="h-4 w-4" />
						Engine unreachable — start it with{" "}
						<code className="font-mono text-red-200">./vapor serve</code>.
					</CardContent>
				</Card>
			)}

			<div className="space-y-3">
				{report?.checks.map((check) => {
					const style = STATUS_STYLES[check.status] ?? STATUS_STYLES.warn;
					const { Icon } = style;
					return (
						<Card key={check.check} className="bg-slate-900/60 border-slate-800">
							<CardContent className="p-4 flex items-start justify-between gap-4">
								<div className="space-y-1 min-w-0">
									<div className="flex items-center gap-2 flex-wrap">
										<Badge
											variant="outline"
											className="bg-slate-950 text-cyan-400 border-cyan-500/30 text-[10px] font-mono">
											{check.check}
										</Badge>
										<h3 className="text-sm font-bold text-slate-200">
											{CHECK_LABELS[check.check] ?? check.check}
										</h3>
									</div>
									<p className="text-xs text-slate-400 font-mono break-words">
										{check.detail}
									</p>
								</div>

								<div
									className={`flex items-center gap-1.5 border px-2.5 py-1 rounded-lg text-xs font-semibold shrink-0 ${style.wrap}`}>
									<Icon className="h-4 w-4" />
									{style.label}
								</div>
							</CardContent>
						</Card>
					);
				})}
			</div>

			{/* Live measured runtime figures */}
			{report && (
				<Card className="bg-slate-900/60 border-slate-800">
					<CardHeader className="py-2.5 px-4 border-b border-slate-800">
						<CardTitle className="text-xs font-bold uppercase tracking-wider text-cyan-400">
							Measured Runtime
						</CardTitle>
					</CardHeader>
					<CardContent className="p-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
						<div>
							<div className="text-slate-500">Engine RSS</div>
							<div className="text-slate-100 font-bold">
								{report.process_rss_mb !== null
									? `${(report.process_rss_mb / 1024).toFixed(2)} GB`
									: "unavailable"}
							</div>
						</div>
						<div>
							<div className="text-slate-500">Host RAM free</div>
							<div className="text-slate-100 font-bold">
								{report.avail_ram_gb.toFixed(1)} / {report.total_ram_gb.toFixed(1)} GB
							</div>
						</div>
						<div>
							<div className="text-slate-500">Context window</div>
							<div className="text-slate-100 font-bold">
								{report.n_ctx.toLocaleString()}{" "}
								<span className="text-slate-500 font-normal">
									/ {report.safe_max_context.toLocaleString()} max
								</span>
							</div>
						</div>
						<div>
							<div className="text-slate-500">Weights</div>
							<div
								className={`font-bold ${report.model_available ? "text-emerald-400" : "text-amber-400"}`}>
								{report.model_available ? "present" : "not found"}
							</div>
						</div>
					</CardContent>
				</Card>
			)}

			{/* Verbatim `./vapor doctor` output */}
			<Card className="bg-slate-950 border-slate-800">
				<CardHeader className="py-2.5 px-4 bg-slate-900/80 border-b border-slate-800">
					<CardTitle className="text-xs font-mono text-slate-400 flex items-center gap-2">
						<Terminal className="h-3.5 w-3.5 text-cyan-400" />
						./vapor doctor output
					</CardTitle>
				</CardHeader>
				<CardContent className="p-4 bg-slate-950">
					<pre className="font-mono text-xs text-emerald-400 whitespace-pre-wrap break-words">
						{report?.text ?? "Run diagnostics to collect output."}
					</pre>
				</CardContent>
			</Card>
		</div>
	);
}
