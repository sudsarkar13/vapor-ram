"use client";

import React, { useState, useRef, useEffect, useSyncExternalStore } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/tokyo-night-dark.css";
import {
	Send,
	Square,
	Bot,
	User,
	Copy,
	Check,
	Terminal,
	Loader2,
	AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThinkingBlock } from "@/components/ThinkingBlock";
import { Textarea } from "@/components/ui/textarea";
import { VaporMessage, ModelState } from "@/lib/api";
import {
	subscribe as subscribeGeneration,
	getSnapshot as generationSnapshot,
	startGeneration,
	stopGeneration,
} from "@/lib/generation";

// Soft visual counters only — the server-side KV cache is the real ceiling.
const COUNTER_WARN_AT = 10000;
const COUNTER_HARD_AT = 20000;

interface ChatViewProps {
	messages: VaporMessage[];
	setMessages: React.Dispatch<React.SetStateAction<VaporMessage[]>>;
	preset: string;
	modelState?: ModelState;
	modelAvailable?: boolean;
}

// Three bouncing dots, staggered so they read as a wave.
function TypingDots() {
	return (
		<div className="flex items-center gap-1.5" aria-label="Assistant is typing">
			<span className="h-2 w-2 rounded-full bg-cyan-400 animate-bounce [animation-delay:-0.3s]" />
			<span className="h-2 w-2 rounded-full bg-cyan-400 animate-bounce [animation-delay:-0.15s]" />
			<span className="h-2 w-2 rounded-full bg-cyan-400 animate-bounce" />
		</div>
	);
}

/** Distinguishes "loading 4.7 GB of weights" from "generating tokens". */
function LoadingWeights({ message }: { message: string }) {
	return (
		<div className="flex items-center gap-2 text-amber-300">
			<Loader2 className="h-4 w-4 animate-spin shrink-0" />
			<span className="text-xs font-mono leading-snug">{message}</span>
		</div>
	);
}

export function ChatView({
	messages,
	setMessages,
	preset,
	modelState,
	modelAvailable = true,
}: ChatViewProps) {
	const [input, setInput] = useState("");
	const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

	// Generation lives outside React, so switching tabs mid-reply no longer
	// discards the stop button, the abort handle or the timings.
	const generation = useSyncExternalStore(
		subscribeGeneration,
		generationSnapshot,
		generationSnapshot,
	);
	const isGenerating = generation.isGenerating;
	const lastTimings = generation.timings;

	// Reasoning for a given assistant message: live while it streams, then from
	// the kept map so it stays readable in the transcript afterwards.
	const reasoningFor = (idx: number) =>
		generation.streamingIndex === idx
			? generation.reasoning
			: (generation.reasoningByIndex[idx] ?? "");
	const messagesEndRef = useRef<HTMLDivElement | null>(null);

	const isLoadingWeights = modelState?.status === "loading";

	const scrollToBottom = (smooth = false) => {
		messagesEndRef.current?.scrollIntoView({
			behavior: smooth ? "smooth" : "auto",
		});
	};

	useEffect(() => {
		// Snap to the latest message without per-frame smooth animation,
		// which would visibly stutter while tokens stream in.
		scrollToBottom(false);
	}, [messages, isGenerating]);

	// The "live" assistant bubble is the last message while it still has no
	// streaming content (or has content but generation is still going).
	const lastAssistantIndex = (() => {
		for (let i = messages.length - 1; i >= 0; i--) {
			if (messages[i].role === "assistant") return i;
		}
		return -1;
	})();
	const isStreamingAssistant = (idx: number) =>
		isGenerating && idx === lastAssistantIndex;

	const handleSend = async (textToSend?: string) => {
		const query = (textToSend || input).trim();
		if (!query || isGenerating) return;

		const updatedMessages: VaporMessage[] = [
			...messages,
			{ role: "user", content: query },
		];
		setMessages(updatedMessages);
		if (!textToSend) setInput("");

		await startGeneration(updatedMessages, preset, setMessages);
	};

	const handleStop = () => stopGeneration();

	const copyToClipboard = (text: string, idx: number) => {
		navigator.clipboard.writeText(text);
		setCopiedIndex(idx);
		setTimeout(() => setCopiedIndex(null), 2000);
	};

	return (
		<div className="flex flex-col h-full bg-slate-950 text-slate-100 font-sans relative overflow-hidden">
			{/* Messages Timeline */}
			<div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
				{messages.length === 0 ?
					<div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto py-12 space-y-5">
						<div className="h-16 w-16 rounded-2xl bg-cyan-950/60 border border-cyan-500/30 flex items-center justify-center shadow-xl shadow-cyan-950/50">
							<span
								aria-hidden="true"
								className="text-4xl leading-none select-none"
								style={{
									filter: "drop-shadow(0 0 10px rgba(34,211,238,0.45))",
								}}>
								💨
							</span>
						</div>

						<div>
							<h2 className="text-xl font-extrabold text-cyan-400">
								VaporRAM Dashboard
							</h2>
							<p className="text-xs text-slate-400 mt-1 leading-relaxed">
								Ultra-Low RAM SSD Streaming Engine running{" "}
								<span className="text-cyan-300 font-semibold">
									google/gemma-4-E4B-it
								</span>{" "}
								under a strict{" "}
								<span className="text-emerald-400 font-mono font-semibold">
									&lt; 1.5 GB RAM ceiling
								</span>
								.
							</p>
						</div>

						<div className="w-full space-y-2 pt-2">
							<span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
								Quick Prompt Templates
							</span>
							<div className="grid grid-cols-1 gap-2 text-left">
								{[
									"Explain quantum computing in simple terms.",
									"Write a C code snippet for O_DIRECT unbuffered SSD file reading.",
									"Summarize the architecture of Gemma 4 E4B-it sliding window attention.",
								].map((promptText, i) => (
									<button
										key={i}
										onClick={() => handleSend(promptText)}
										className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-cyan-500/40 hover:bg-slate-900 text-xs text-slate-300 hover:text-cyan-300 transition-all flex items-center justify-between group">
										<span>{promptText}</span>
										<Terminal className="h-3.5 w-3.5 text-slate-600 group-hover:text-cyan-400 transition-colors" />
									</button>
								))}
							</div>
						</div>
					</div>
				:	messages.map((msg, idx) => (
						<div
							key={idx}
							className={`flex gap-3 md:gap-4 max-w-4xl mx-auto ${
								msg.role === "user" ? "justify-end" : "justify-start"
							}`}>
							{msg.role === "assistant" && (
								<div className="h-8 w-8 rounded-lg bg-cyan-950 border border-cyan-500/40 flex items-center justify-center text-cyan-400 flex-shrink-0 mt-1 shadow-md">
									<Bot className="h-4 w-4" />
								</div>
							)}

							<div
								className={`relative group rounded-2xl px-4 py-3 text-sm max-w-[85%] leading-relaxed ${
									msg.role === "user" ?
										"bg-gradient-to-r from-cyan-600 to-cyan-700 text-slate-950 font-medium shadow-lg shadow-cyan-950/30"
									:	"bg-slate-900/80 border border-slate-800/90 text-slate-200 shadow-md"
								}`}>
								{msg.role === "assistant" && reasoningFor(idx) ? (
									<ThinkingBlock
										text={reasoningFor(idx)}
										active={
											generation.streamingIndex === idx &&
											generation.isThinking
										}
										durationMs={
											generation.streamingIndex === idx
												? null
												: lastTimings?.first_answer_ms
										}
										tokens={
											generation.streamingIndex === idx
												? null
												: lastTimings?.reasoning_tokens
										}
									/>
								) : null}

								{msg.role === "user" ?
									<p className="whitespace-pre-wrap">{msg.content}</p>
								: isStreamingAssistant(idx) && !msg.content ?
									// While reasoning streams the block above already shows
									// activity, so don't also show the generic typing dots.
									generation.isThinking && generation.streamingIndex === idx ?
										null
									: isLoadingWeights ?
										<LoadingWeights
											message={modelState?.message || "Loading model weights…"}
										/>
									:	<TypingDots />
								: msg.content ?
									<div className="prose prose-invert prose-sm max-w-none prose-headings:text-cyan-300 prose-headings:font-bold prose-a:text-cyan-400 prose-code:text-cyan-300 prose-code:bg-slate-950 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-pre:bg-slate-950 prose-pre:border prose-pre:border-slate-800">
										<ReactMarkdown
											remarkPlugins={[remarkGfm]}
											rehypePlugins={[rehypeHighlight]}>
											{msg.content}
										</ReactMarkdown>
									</div>
								:	null}

								{msg.role === "assistant" &&
									msg.content &&
									!isStreamingAssistant(idx) && (
										<button
											onClick={() => copyToClipboard(msg.content, idx)}
											className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-slate-400 hover:text-cyan-300 transition-all"
											title="Copy message">
											{copiedIndex === idx ?
												<Check className="h-3.5 w-3.5 text-emerald-400" />
											:	<Copy className="h-3.5 w-3.5" />}
										</button>
									)}
							</div>

							{msg.role === "user" && (
								<div className="h-8 w-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 flex-shrink-0 mt-1">
									<User className="h-4 w-4" />
								</div>
							)}
						</div>
					))
				}
				<div ref={messagesEndRef} />
			</div>

			{/* Input Form Bar */}
			<div className="p-4 border-t border-slate-800 bg-slate-950/90 backdrop-blur-md">
				<div className="max-w-4xl mx-auto space-y-2">
					{!modelAvailable && (
						<div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-950/30 px-3 py-2 text-[11px] text-amber-200">
							<AlertTriangle className="h-3.5 w-3.5 shrink-0" />
							No GGUF weights found. Use{" "}
							<span className="font-mono font-semibold">HF Download</span> in the
							sidebar, or run{" "}
							<code className="font-mono">./vapor download</code>.
						</div>
					)}

					{lastTimings?.completion_tokens != null && !isGenerating && (
						<div className="flex items-center gap-3 text-[10px] font-mono text-slate-500 justify-end">
							<span>{lastTimings.completion_tokens} tokens</span>
							{lastTimings.tokens_per_second != null && (
								<span>{lastTimings.tokens_per_second.toFixed(1)} tok/s</span>
							)}
							{lastTimings.first_token_ms != null && (
								<span>
									first token {(lastTimings.first_token_ms / 1000).toFixed(1)}s
								</span>
							)}
						</div>
					)}

					<div
						className={`relative flex items-end gap-2 rounded-xl border bg-slate-900/80 pl-3 pr-2 py-2 transition-colors ${
							input.trim() ?
								"border-cyan-500/50 shadow-[0_0_0_3px_rgba(6,182,212,0.08)]"
							:	"border-slate-800 focus-within:border-cyan-500/40 focus-within:shadow-[0_0_0_3px_rgba(6,182,212,0.06)]"
						}`}>
						<Textarea
							value={input}
							onChange={(e) => setInput(e.target.value)}
							onKeyDown={(e) => {
								if (
									e.key === "Enter" &&
									!e.shiftKey &&
									!e.nativeEvent.isComposing
								) {
									e.preventDefault();
									handleSend();
								}
							}}
							placeholder="Ask VaporRAM anything (Enter to send · Shift+Enter for newline)"
							className="min-h-[40px] max-h-36 bg-transparent border-0 text-slate-100 placeholder:text-slate-500 text-sm focus-visible:ring-0 focus-visible:border-0 rounded-none px-0 py-2 resize-none"
							rows={1}
						/>

						<div className="flex items-center gap-1.5 mb-1 shrink-0">
							{input.length >= COUNTER_WARN_AT && (
								<span
									className={`text-[10px] font-mono tabular-nums ${
										input.length >= COUNTER_HARD_AT ?
											"text-red-400"
										:	"text-amber-400"
									}`}
									title="VaporRAM is sized for 8K-token contexts; very long prompts may exceed the KV cache.">
									{input.length.toLocaleString()} chars
								</span>
							)}

							{isGenerating ?
								<Button
									onClick={handleStop}
									size="sm"
									className="h-8 px-3 bg-red-950 border border-red-500/40 hover:bg-red-900 text-red-300 rounded-lg font-semibold text-xs flex items-center gap-1.5">
									<Square className="h-3.5 w-3.5 fill-red-400" />
									Stop
								</Button>
							:	<Button
									onClick={() => handleSend()}
									disabled={!input.trim()}
									size="sm"
									className="h-8 px-3 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold rounded-lg text-xs flex items-center gap-1.5 shadow-md shadow-cyan-500/20 disabled:bg-slate-800 disabled:text-slate-500 disabled:shadow-none"
									title={
										input.trim() ? "Send message" : "Type a message to send"
									}>
									<Send className="h-3.5 w-3.5" />
									Send
								</Button>
							}
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
