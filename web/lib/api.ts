/**
 * VaporRAM API Client Library
 * Connects to VaporRAM Python / C backend endpoints (/v1)
 */

export interface VaporMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface VaporHealth {
  status: string;
  version: string;
  engine: string;
  ram_ceiling: string;
  active_model: string;
}

export interface SystemProgress {
  status: "idle" | "downloading" | "loading" | "completed" | "error";
  percent: number;
  message: string;
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
    const res = await fetch(`${getBaseUrl()}/v1/system/progress`, { cache: "no-store" });
    if (res.ok) return await res.json();
  } catch (e) {
    console.warn("VaporRAM progress check offline:", e);
  }
  return null;
}

export async function stopServer(): Promise<boolean> {
  try {
    const res = await fetch(`${getBaseUrl()}/v1/system/stop`, { method: "POST" });
    return res.ok;
  } catch (e) {
    return false;
  }
}

export async function downloadModel(repo = "google/gemma-4-E4B-it", dest = "./models/gemma-4-E4B-it"): Promise<boolean> {
  try {
    const res = await fetch(`${getBaseUrl()}/v1/models/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo, dest }),
    });
    return res.ok;
  } catch (e) {
    return false;
  }
}

export async function streamChatCompletions(
  messages: VaporMessage[],
  preset: string | null,
  onChunk: (text: string) => void,
  onComplete: () => void,
  onError: (err: Error) => void,
  signal?: AbortSignal
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
          } catch (e) {
            // Raw text chunk fallback
            if (dataStr) onChunk(dataStr);
          }
        }
      }
    }
    onComplete();
  } catch (err: any) {
    if (err.name === "AbortError") {
      onComplete();
    } else {
      onError(err);
    }
  }
}
