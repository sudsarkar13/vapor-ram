/**
 * Generation lifecycle, held outside React.
 *
 * The chat view unmounts whenever another tab is selected. When this state
 * lived inside that component, switching to Brain Cortex mid-reply destroyed
 * the AbortController, the "generating" flag and the timings — so the stop
 * button vanished, the run could no longer be cancelled, and the token/timing
 * footer never appeared, even though the stream was still running and still
 * appending to the message list.
 *
 * An in-flight HTTP stream is external state by nature, so it lives here and
 * components subscribe to it with useSyncExternalStore. Remounting re-reads
 * the current truth instead of starting from blank.
 */
import {
	streamChatCompletions,
	VaporMessage,
	GenerationTimings,
} from "./api";

export interface GenerationState {
	isGenerating: boolean;
	timings: GenerationTimings | null;
	/** Index of the assistant message currently being written, if any. */
	streamingIndex: number | null;
	error: string | null;
	/** Reasoning for the message at streamingIndex, accumulated as it streams. */
	reasoning: string;
	/** True while reasoning is arriving and the answer has not started. */
	isThinking: boolean;
	/** Reasoning for each completed assistant message, by message index. */
	reasoningByIndex: Record<number, string>;
}

const IDLE: GenerationState = {
	isGenerating: false,
	timings: null,
	streamingIndex: null,
	error: null,
	reasoning: "",
	isThinking: false,
	reasoningByIndex: {},
};

let state: GenerationState = IDLE;
let controller: AbortController | null = null;
const listeners = new Set<() => void>();

function setState(patch: Partial<GenerationState>) {
	// Replaced wholesale so useSyncExternalStore sees a new reference only
	// when something actually changed.
	state = { ...state, ...patch };
	listeners.forEach((fn) => fn());
}

export function subscribe(fn: () => void): () => void {
	listeners.add(fn);
	return () => {
		listeners.delete(fn);
	};
}

export function getSnapshot(): GenerationState {
	return state;
}

type Dispatch = React.Dispatch<React.SetStateAction<VaporMessage[]>>;

/**
 * Begin a generation. `setMessages` is a useState setter, whose identity React
 * guarantees is stable, so holding it across an unmount is safe — that is what
 * lets the reply keep landing in the transcript while another tab is open.
 */
export async function startGeneration(
	history: VaporMessage[],
	preset: string,
	setMessages: Dispatch,
) {
	if (state.isGenerating) return;

	const assistantIndex = history.length;
	setMessages([...history, { role: "assistant", content: "" }]);

	controller = new AbortController();
	setState({
		isGenerating: true,
		streamingIndex: assistantIndex,
		error: null,
		timings: null,
		reasoning: "",
		isThinking: false,
	});

	const finish = (patch: Partial<GenerationState>) => {
		controller = null;
		// Reasoning is kept against the message index so it stays readable in
		// the transcript after the run, not just while it is streaming.
		const kept = state.reasoning
			? { ...state.reasoningByIndex, [assistantIndex]: state.reasoning }
			: state.reasoningByIndex;
		setState({
			isGenerating: false,
			streamingIndex: null,
			isThinking: false,
			reasoningByIndex: kept,
			...patch,
		});
	};

	await streamChatCompletions(
		history,
		preset,
		(chunk) => {
			if (state.isThinking) setState({ isThinking: false });
			setMessages((prev) => {
				const next = [...prev];
				const current = next[assistantIndex];
				if (current) {
					// Assistant messages are always plain text; only user messages
					// can carry content parts.
					const existing =
						typeof current.content === "string" ? current.content : "";
					next[assistantIndex] = {
						...current,
						content: existing + chunk,
					};
				}
				return next;
			});
		},
		(timings) => finish({ timings: timings ?? null }),
		(err) => {
			setMessages((prev) => {
				const next = [...prev];
				const current = next[assistantIndex];
				if (current && !current.content) {
					next[assistantIndex] = {
						...current,
						content: `⚠️ Connection error: ${err.message}. Please verify the VaporRAM server is running.`,
					};
				}
				return next;
			});
			finish({ error: err.message });
		},
		controller.signal,
		(piece) => setState({ reasoning: state.reasoning + piece, isThinking: true }),
	);
}

export function stopGeneration() {
	if (controller) {
		controller.abort();
		controller = null;
	}
	setState({ isGenerating: false, streamingIndex: null });
}

/** Clears timings when the transcript is cleared, so stale figures don't linger. */
export function resetGeneration() {
	if (state.isGenerating) return;
	state = IDLE;
	listeners.forEach((fn) => fn());
}
