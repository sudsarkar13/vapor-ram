/**
 * VaporRAM API Client Library
 * Connects to VaporRAM Python / C backend endpoints (/v1)
 */

export interface VaporMessage {
	role: "system" | "user" | "assistant";
	content: string;
}

export interface VaporSlots {
	active: number;
	total: number;
}

export interface VaporHealth {
	status: string;
	version: string;
	engine: string;
	ram_ceiling: string;
	active_model: string;
	slots?: VaporSlots;
	n_ctx?: number;
	model_max_context?: number;
}

export interface ServerConfig {
	status: string;
	version: string;
	n_ctx: number;
	model_max_context: number;
	ram_ceiling_gb: number;
	total_ram_gb: number;
	avail_ram_gb: number;
	model_path: string;
	message?: string;
}

export interface SystemProgress {
	status: "idle" | "downloading" | "loading" | "completed" | "error";
	percent: number;
	message: string;
	slots?: VaporSlots;
	n_ctx?: number;
	model_max_context?: number;
	ram_ceiling_gb?: number;
	total_ram_gb?: number;
	avail_ram_gb?: number;
}

const getBaseUrl = () => {
	if (typeof window !== "undefined") {
		// If hosted on localhost:8000 directly or via dev proxy
		return window.location.port === "3000" ? "http://localhost:8000" : "";
	}
	return "http://localhost:8000";
};

export async function fetchHealth(): Promise<VaporHealth | null> {
	try {
		const res = await fetch(`${getBaseUrl()}/health`, { cache: "no-store" });
		if (res.ok) return await res.json();
	} catch (e) {
		console.warn("VaporRAM health check offline:", e);
	}
	return null;
}

export async function fetchProgress(): Promise<SystemProgress | null> {
	try {
		const res = await fetch(`${getBaseUrl()}/v1/system/progress`, {
			cache: "no-store",
		});
		if (res.ok) return await res.json();
	} catch (e) {
		console.warn("VaporRAM progress check offline:", e);
	}
	return null;
}

export async function stopServer(): Promise<boolean> {
	try {
		const res = await fetch(`${getBaseUrl()}/v1/system/stop`, {
			method: "POST",
		});
		return res.ok;
	} catch {
		return false;
	}
}

export async function downloadModel(
	repo = "google/gemma-4-E4B-it",
	dest = "./models/gemma-4-E4B-it",
): Promise<boolean> {
	try {
		const res = await fetch(`${getBaseUrl()}/v1/models/download`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ repo, dest }),
		});
		return res.ok;
	} catch {
		return false;
	}
}

export async function fetchServerConfig(): Promise<ServerConfig | null> {
	try {
		const res = await fetch(`${getBaseUrl()}/v1/system/config`, { cache: "no-store" });
		if (res.ok) return await res.json();
	} catch (e) {
		console.warn("VaporRAM fetchServerConfig failed:", e);
	}
	return null;
}

export async function updateServerConfig(params: {
	ram_ceiling_gb?: number;
	n_ctx?: number;
	model_dir?: string;
}): Promise<ServerConfig | null> {
	try {
		const res = await fetch(`${getBaseUrl()}/v1/system/config`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(params),
		});
		if (res.ok) return await res.json();
	} catch (e) {
		console.warn("VaporRAM updateServerConfig failed:", e);
	}
	return null;
}

export async function setContextWindow(n_ctx: number): Promise<{
	n_ctx: number;
	model_max_context?: number;
	message?: string;
} | null> {
	try {
		const res = await fetch(`${getBaseUrl()}/v1/system/context`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ n_ctx }),
		});
		if (res.ok) return await res.json();
	} catch (e) {
		console.warn("VaporRAM setContextWindow failed:", e);
	}
	return null;
}

export async function streamChatCompletions(
	messages: VaporMessage[],
	preset: string | null,
	onChunk: (text: string) => void,
	onComplete: () => void,
	onError: (err: Error) => void,
	signal?: AbortSignal,
) {
	try {
		const formattedMessages = [...messages];
		if (preset) {
			formattedMessages.unshift({
				role: "system",
				content: `Preset: ${preset}`,
			});
		}

		const response = await fetch(`${getBaseUrl()}/v1/chat/completions`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify({
				model: "google/gemma-4-E4B-it",
				messages: formattedMessages,
				stream: true,
				max_tokens: 8192,
			}),
			signal,
		});

		if (!response.ok) {
			throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
		}

		if (!response.body) {
			throw new Error("No response body received from server");
		}

		const reader = response.body.getReader();
		const decoder = new TextDecoder("utf-8");
		let buffer = "";

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split("\n");
			buffer = lines.pop() || "";

			for (const line of lines) {
				const trimmed = line.trim();
				if (!trimmed || trimmed.startsWith(":")) continue;

				if (trimmed.startsWith("data: ")) {
					const dataStr = trimmed.slice(6);
					if (dataStr === "[DONE]") {
						onComplete();
						return;
					}

					try {
						const parsed = JSON.parse(dataStr);
						const content = parsed?.choices?.[0]?.delta?.content;
						if (content) {
							onChunk(content);
						}
					} catch {
						// Raw text chunk fallback
						if (dataStr) onChunk(dataStr);
					}
				}
			}
		}
		onComplete();
	} catch (err) {
		if (err instanceof Error && err.name === "AbortError") {
			onComplete();
		} else if (err instanceof Error) {
			onError(err);
		} else {
			onError(new Error("Stream failed"));
		}
	}
}
