"use client";

import React, { useState } from "react";
import { Brain, ChevronRight } from "lucide-react";

interface ThinkingBlockProps {
	text: string;
	/** True while reasoning is still arriving, which drives the animation. */
	active: boolean;
	/** Milliseconds spent reasoning, once the answer has started. */
	durationMs?: number | null;
	tokens?: number | null;
}

/**
 * Collapsed by default: the reasoning is working-out, not the answer, and
 * should not push the reply off screen. Clicking opens it.
 */
export function ThinkingBlock({
	text,
	active,
	durationMs,
	tokens,
}: ThinkingBlockProps) {
	const [open, setOpen] = useState(false);
	if (!text && !active) return null;

	const summary = active
		? "Thinking"
		: durationMs
			? `Thought for ${(durationMs / 1000).toFixed(1)}s`
			: "Thought process";

	return (
		<div className="mb-2 rounded-lg border border-violet-500/25 bg-violet-950/20">
			<button
				type="button"
				onClick={() => setOpen((v) => !v)}
				aria-expanded={open}
				className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-violet-300 transition-colors hover:bg-violet-500/10">
				<Brain
					className={`h-3.5 w-3.5 shrink-0 ${active ? "animate-pulse" : ""}`}
				/>
				<span className="font-medium">{summary}</span>
				{active && (
					<span className="flex gap-1" aria-hidden="true">
						{[0, 150, 300].map((delay) => (
							<span
								key={delay}
								className="h-1 w-1 animate-bounce rounded-full bg-violet-400"
								style={{ animationDelay: `${delay}ms` }}
							/>
						))}
					</span>
				)}
				{!active && tokens ? (
					<span className="text-violet-400/60">· {tokens} tokens</span>
				) : null}
				<ChevronRight
					className={`ml-auto h-3.5 w-3.5 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
				/>
			</button>
			{open && (
				<div className="border-t border-violet-500/20 px-3 py-2">
					<pre className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-slate-400">
						{text || "…"}
					</pre>
				</div>
			)}
		</div>
	);
}
