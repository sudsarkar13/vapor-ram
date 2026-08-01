"use client";

import React from "react";
import {
	MessageSquare,
	Cpu,
	Activity,
	Terminal,
	Trash2,
	Zap,
	Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export type ActiveTab = "chat" | "brain" | "profiling" | "doctor";

export interface VaporSlots {
	active: number;
	total: number;
}

interface HeaderProps {
	activeTab: ActiveTab;
	setActiveTab: (tab: ActiveTab) => void;
	onClearChat: () => void;
	isOnline: boolean;
	activeModel: string;
	slots?: VaporSlots;
}

const TABS: { id: ActiveTab; label: string; Icon: typeof MessageSquare }[] = [
	{ id: "chat", label: "Chat", Icon: MessageSquare },
	{ id: "brain", label: "Brain Cortex", Icon: Cpu },
	{ id: "profiling", label: "Profiling", Icon: Activity },
	{ id: "doctor", label: "Doctor", Icon: Terminal },
];

export function Header({
	activeTab,
	setActiveTab,
	onClearChat,
	isOnline,
	activeModel,
	slots,
}: HeaderProps) {
	return (
		<header className="sticky top-0 z-50 w-full border-b border-cyan-500/20 bg-slate-950/90 backdrop-blur-md">
			<div className="flex h-11 items-center gap-3 px-3">
				{/* Brand */}
				<div className="flex shrink-0 items-center gap-1.5">
					<Zap className="h-4 w-4 fill-cyan-400/20 text-cyan-400 animate-pulse" />
					<span className="text-sm font-extrabold tracking-tight text-cyan-400">
						VaporRAM
					</span>
					<Badge
						variant="outline"
						className="h-5 px-1.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-cyan-400/90 border-cyan-500/40 bg-cyan-950/60">
						v1.0.6
					</Badge>
				</div>

				<div className="h-5 w-px bg-slate-800" />

				{/* Status */}
				<Badge
					variant="outline"
					className={`h-6 shrink-0 gap-1.5 px-2 text-[11px] font-medium ${
						isOnline ?
							"bg-emerald-950/40 text-emerald-400 border-emerald-500/30"
						:	"bg-amber-950/40 text-amber-400 border-amber-500/30"
					}`}>
					<span className="relative inline-flex h-1.5 w-1.5">
						{isOnline && (
							<span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
						)}
						<span
							className={`relative inline-flex h-1.5 w-1.5 rounded-full ${isOnline ? "bg-emerald-400" : "bg-amber-400"}`}
						/>
					</span>
					<span className="truncate max-w-[180px]">
						{isOnline ? activeModel : "Engine Offline"}
					</span>
				</Badge>

				<div className="flex-1" />

				{/* Tabs */}
				<div className="flex shrink-0 items-center gap-0.5 rounded-md bg-slate-900/80 p-0.5 border border-slate-800">
					{TABS.map(({ id, label, Icon }) => {
						const active = activeTab === id;
						return (
							<button
								key={id}
								onClick={() => setActiveTab(id)}
								className={`flex items-center gap-1.5 rounded-[5px] px-2.5 py-1 text-[11px] font-semibold transition-all ${
									active ?
										"bg-cyan-500 text-slate-950 shadow-sm shadow-cyan-500/30"
									:	"text-slate-400 hover:text-slate-100 hover:bg-slate-800/70"
								}`}>
								<Icon className="h-3.5 w-3.5" />
								<span className="hidden sm:inline">{label}</span>
							</button>
						);
					})}
				</div>

				{/* Right actions */}
				<div className="flex shrink-0 items-center gap-1.5">
					<Badge
						variant="outline"
						title="Active KV-cache slots reserved for the live chat session"
						className={`h-6 gap-1.5 px-2 text-[10px] font-mono uppercase tracking-wider ${
							slots && slots.active > 0 ?
								"text-emerald-300/90 bg-emerald-950/40 border-emerald-500/30"
							:	"text-cyan-300/90 bg-cyan-950/40 border-cyan-500/30"
						}`}>
						<Layers className="h-3 w-3" />
						slot {slots?.active ?? 0}/{slots?.total ?? 1}
					</Badge>
					<Button
						onClick={onClearChat}
						variant="outline"
						size="sm"
						className="h-7 px-2 text-[11px] font-medium bg-slate-900/60 border-red-500/30 text-red-400 hover:bg-red-950/40 hover:text-red-300 hover:border-red-500/50 transition-all">
						<Trash2 className="h-3 w-3" />
						<span className="hidden sm:inline ml-1">Clear</span>
					</Button>
				</div>
			</div>
		</header>
	);
}
