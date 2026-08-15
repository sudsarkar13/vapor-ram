/**
 * VaporRAM API Client Library
 *
 * These interfaces mirror the payloads emitted by openai_server.py exactly.
 * Every status endpoint embeds the same TelemetrySnapshot block, so one contract
 * covers /health, /v1/models, /v1/system/config, /v1/system/progress and /v1/stats.
 */

export interface VaporMessage {
	role: "system" | "user" | "assistant";
	content: string;
}

export interface VaporSlots {
	active: number;
	total: number;
}

export type ModelLifecycle = "idle" | "loading" | "ready" | "error";

export interface ModelState {
	status: ModelLifecycle;
	message: string;
	model_path: string | null;
	n_ctx: number | null;
}

export interface ModelArchitecture {
	n_layers: number;
	hidden_dim: number;
	n_heads: number;
	n_kv_heads: number;
	head_dim: number;
	kv_shared_layers: number;
	sliding_window: number;
	layer_buffer_mb: number;
}

/** Shared live-metrics block returned by every status endpoint. */
export interface Telemetry {
	n_ctx: number;
	model_max_context: number;
	safe_max_context: number;
	min_context: number;
	architecture: ModelArchitecture;
	ram_ceiling_gb: number;
	total_ram_gb: number;
	avail_ram_gb: number;
	/** Measured RSS of the engine process; null when the platform can't report it. */
	process_rss_mb: number | null;
	model_path: string;
	model_available: boolean;
	model_state: ModelState;
	slots: VaporSlots;
}

export interface VaporHealth extends Telemetry {
	status: string;
	engine: string;
	version: string;
	model: string;
	active_model: string;
	format: string;
	gguf_file: string | null;
	connection: "CONNECTED" | "NO_WEIGHTS";
}

export interface DownloadProgress {
	status: "idle" | "downloading" | "completed" | "error";
	percent: number;
	message: string;
	downloaded_mb: number;
	total_mb: number;
	speed_mbps: number;
}

export interface ScannedModel {
	path: string;
	available: boolean;
	has_gguf: boolean;
	gguf_name: string | null;
	size_gb: number | null;
	is_active: boolean;
}

export interface SystemProgress extends Telemetry {
	status: string;
	version: string;
	message: string;
	active_path: string;
	scanned_models: ScannedModel[];
	/** Download state lives here — it is NOT the top-level `status` field. */
	download_progress: DownloadProgress;
}

export interface ServerConfig extends Telemetry {
	status: string;
	version: string;
	updated?: boolean;
	warnings?: string[];
	message?: string;
}

export interface VaporPreset {
	id: string;
	name: string;
	system_instruction: string;
	temperature: number;
	top_p: number;
}

export interface DoctorCheck {
	check: string;
	status: "ok" | "warn" | "fail";
	detail: string;
}

export interface DoctorReport extends Telemetry {
	status: string;
	version: string;
	checks: DoctorCheck[];
	text: string;
}

export interface GenerationTimings {
	wall_time_ms?: number;
	first_token_ms?: number | null;
	completion_tokens?: number | null;
	tokens_per_second?: number | null;
}

const getBaseUrl = () => {
	if (typeof window !== "undefined") {
		// Next dev server runs on :3000; the engine always serves the API on :8000.
		return window.location.port === "3000" ? "http://localhost:8000" : "";
	}
	return "http://localhost:8000";
};

async function getJson<T>(path: string, label: string): Promise<T | null> {
	try {
		const res = await fetch(`${getBaseUrl()}${path}`, { cache: "no-store" });
		if (res.ok) return (await res.json()) as T;
	} catch (e) {
		console.warn(`VaporRAM ${label} unreachable:`, e);
	}
	return null;
}

async function postJson<T>(
	path: string,
	body: unknown,
	label: string,
): Promise<T | null> {
	try {
		const res = await fetch(`${getBaseUrl()}${path}`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(body),
		});
		// 4xx bodies carry an actionable `message`, so parse them rather than
		// discarding the response.
		const data = (await res.json().catch(() => null)) as T | null;
		return data;
	} catch (e) {
		console.warn(`VaporRAM ${label} failed:`, e);
		return null;
	}
}

export const fetchHealth = () => getJson<VaporHealth>("/health", "health check");

export const fetchProgress = () =>
	getJson<SystemProgress>("/v1/system/progress", "progress poll");

export const fetchServerConfig = () =>
	getJson<ServerConfig>("/v1/system/config", "config fetch");

export const fetchDoctor = () => getJson<DoctorReport>("/v1/doctor", "doctor");

export async function fetchPresets(): Promise<VaporPreset[]> {
	const res = await getJson<{ data: VaporPreset[] }>("/v1/presets", "presets");
	return res?.data ?? [];
}

export async function stopServer(): Promise<boolean> {
	try {
		const res = await fetch(`${getBaseUrl()}/v1/system/stop`, { method: "POST" });
		return res.ok;
	} catch {
		return false;
	}
}

export async function restartServer(): Promise<boolean> {
	try {
		const res = await fetch(`${getBaseUrl()}/v1/system/restart`, { method: "POST" });
		return res.ok;
	} catch {
		return false;
	}
}

/** Kicks off a background download. Progress arrives via fetchProgress(). */
export const downloadModel = (repo?: string, dest?: string) =>
	postJson<{ status: string; message: string; download_progress: DownloadProgress }>(
		"/v1/models/download",
		{ repo, dest },
		"model download",
	);

export const updateServerConfig = (params: {
	ram_ceiling_gb?: number;
	n_ctx?: number;
	/** Only send this when the user actually intends to change the model directory. */
	model_dir?: string;
}) => postJson<ServerConfig>("/v1/system/config", params, "config update");

export const setContextWindow = (n_ctx: number) =>
	postJson<ServerConfig & { error?: string; old_n_ctx?: number }>(
		"/v1/system/context",
		{ n_ctx },
		"context update",
	);

export const setModelPath = (path: string) =>
	postJson<ServerConfig & { error?: string; active_path?: string }>(
		"/v1/system/set_model_path",
		{ path },
		"model path update",
	);

export async function streamChatCompletions(
	messages: VaporMessage[],
	preset: string | null,
	onChunk: (text: string) => void,
	onComplete: (timings?: GenerationTimings) => void,
	onError: (err: Error) => void,
	signal?: AbortSignal,
) {
	try {
		const response = await fetch(`${getBaseUrl()}/v1/chat/completions`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				model: "google/gemma-4-E4B-it",
				messages,
				// The server resolves the persona and applies its system instruction
				// and sampling parameters; the full history above is used as context.
				preset: preset ?? "default",
				stream: true,
				max_tokens: 8192,
			}),
			signal,
		});

		if (!response.ok) {
			let detail = `HTTP ${response.status}`;
			try {
				const body = await response.json();
				if (body?.message) detail = body.message;
			} catch {
				/* non-JSON error body */
			}
			throw new Error(detail);
		}
		if (!response.body) throw new Error("No response body received from server");

		const reader = response.body.getReader();
		const decoder = new TextDecoder("utf-8");
		let buffer = "";
		let timings: GenerationTimings | undefined;

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split("\n");
			buffer = lines.pop() || "";

			for (const line of lines) {
				const trimmed = line.trim();
				if (!trimmed || trimmed.startsWith(":")) continue;
				if (!trimmed.startsWith("data: ")) continue;

				const dataStr = trimmed.slice(6);
				if (dataStr === "[DONE]") {
					onComplete(timings);
					return;
				}

				try {
					const parsed = JSON.parse(dataStr);
					const choice = parsed?.choices?.[0];
					const content = choice?.delta?.content;
					if (content) onChunk(content);
					if (parsed?.timings) timings = parsed.timings;
					if (choice?.finish_reason === "error") {
						throw new Error(content || "Engine reported an error");
					}
				} catch (parseErr) {
					if (parseErr instanceof Error && parseErr.message !== "Unexpected end of JSON input") {
						// Surface engine-side errors; ignore partial-frame parse noise.
						if (!dataStr.startsWith("{")) onChunk(dataStr);
					}
				}
			}
		}
		onComplete(timings);
	} catch (err) {
		if (err instanceof Error && err.name === "AbortError") {
			onComplete();
		} else {
			onError(err instanceof Error ? err : new Error("Stream failed"));
		}
	}
}
