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
}

const IDLE: GenerationState = {
	isGenerating: false,
	timings: null,
	streamingIndex: null,
	error: null,
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
	});

	const finish = (patch: Partial<GenerationState>) => {
		controller = null;
		setState({ isGenerating: false, streamingIndex: null, ...patch });
	};

	await streamChatCompletions(
		history,
		preset,
		(chunk) => {
			setMessages((prev) => {
				const next = [...prev];
				const current = next[assistantIndex];
				if (current) {
					next[assistantIndex] = {
						...current,
						content: current.content + chunk,
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
