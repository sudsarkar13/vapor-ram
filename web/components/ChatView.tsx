"use client";

import React, { useState, useRef, useEffect } from "react";
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
	Sparkles,
	Terminal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { VaporMessage, streamChatCompletions } from "@/lib/api";

// Soft visual counters only — the engine's KV cache (8,192 tokens in
// llama-cpp config) is the real ceiling, enforced server-side.
const COUNTER_WARN_AT = 10000;
const COUNTER_HARD_AT = 20000;

interface ChatViewProps {
	messages: VaporMessage[];
	setMessages: React.Dispatch<React.SetStateAction<VaporMessage[]>>;
	preset: string;
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

export function ChatView({ messages, setMessages, preset }: ChatViewProps) {
	const [input, setInput] = useState("");
	const [isGenerating, setIsGenerating] = useState(false);
	const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
	const abortControllerRef = useRef<AbortController | null>(null);
	const messagesEndRef = useRef<HTMLDivElement | null>(null);

	const scrollToBottom = () => {
		messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
	};

	useEffect(() => {
		scrollToBottom();
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

		const userMsg: VaporMessage = { role: "user", content: query };
		const updatedMessages = [...messages, userMsg];
		setMessages(updatedMessages);
		if (!textToSend) setInput("");
		setIsGenerating(true);

		// Placeholder assistant message
		const assistantIndex = updatedMessages.length;
		setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

		abortControllerRef.current = new AbortController();

		await streamChatCompletions(
			updatedMessages,
			preset !== "default" ? preset : null,
			(chunk) => {
				setMessages((prev) => {
					const next = [...prev];
					if (next[assistantIndex]) {
						next[assistantIndex] = {
							...next[assistantIndex],
							content: next[assistantIndex].content + chunk,
						};
					}
					return next;
				});
			},
			() => {
				setIsGenerating(false);
				abortControllerRef.current = null;
			},
			(err) => {
				console.error("Streaming error:", err);
				setMessages((prev) => {
					const next = [...prev];
					if (next[assistantIndex] && !next[assistantIndex].content) {
						next[assistantIndex].content =
							`⚠️ Connection error: ${err.message}. Please verify VaporRAM server is running.`;
					}
					return next;
				});
				setIsGenerating(false);
				abortControllerRef.current = null;
			},
			abortControllerRef.current.signal,
		);
	};

	const handleStop = () => {
		if (abortControllerRef.current) {
			abortControllerRef.current.abort();
			setIsGenerating(false);
		}
	};

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
							<Sparkles className="h-8 w-8 text-cyan-400 animate-pulse" />
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
								{msg.role === "user" ?
									<p className="whitespace-pre-wrap">{msg.content}</p>
								: isStreamingAssistant(idx) && !msg.content ?
									<TypingDots />
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
				<div className="max-w-4xl mx-auto">
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
