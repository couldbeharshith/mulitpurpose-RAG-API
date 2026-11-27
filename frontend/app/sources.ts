export type Source = { name: string; file?: File; url?: string };
export type Passage = { id: number; text: string; kind: "page" | "slide" | "sheet" | "passage"; location: number | null };
export type OpenCitation = (passage: Passage | undefined, missingReference?: number, turnIndex?: number) => void;
export const citationMarker = /[\[【［]\s*source\s*[:：]\s*([0-9０-９]{1,5})\s*[\]】］]/gi;
export type EvidenceAnswer = { answer: string; citations?: Passage[] };
export type Turn = EvidenceAnswer & { question: string };
export type ChatStage = "reading" | "searching" | "writing";
export type SourcePreview =
  | { kind: "page"; count: number; url: string }
  | { kind: "sheet"; count: number; title: string; rows: string[][]; limited: boolean }
  | { kind: "slide"; count: number; title: string; text: string };
export type Conversation = {
  id: string;
  title: string;
  source: { name: string; url?: string | null; size?: number | null };
  turns: Turn[];
  updated_at: string;
  pinned: boolean;
  starter?: string | null;
};

export const examples = [
  { title: "Field recording notes", kind: "Field notes", filename: "Estuary field notes.md",
    prompt: "How did the sound change with the tide?",
    content: "# Estuary field notes\n\nA two-day listening survey at North Inlet.\n\n## Low tide · Monday, 06:15\nThe exposed mudflat carried short, bright sandpiper calls. Wind from the north rattled the reeds. The east microphone picked up a distant ferry at 06:27.\n\n## High tide · Tuesday, 07:05\nWater reached the lower boardwalk. Lapping water covered the reed noise. Sandpipers had moved inland. A hydrophone below the boardwalk captured shrimp clicks that the microphones on land missed.\n\n## Next visit\nRepeat both recordings at dusk. Fit a windscreen to the east microphone and log ferry crossings separately." },
  { title: "Materials comparison", kind: "Research table", filename: "Packaging trials.csv",
    prompt: "Which material held up best in the humidity trial?",
    content: "Material,Drop trial (surviving units of 20),Humidity trial (hours before deformation),Mass per insert (g),Notes\nMolded pulp,18,6,32,Local recycled fiber\nCorrugated board,16,4,24,Flat packs for transit\nCork composite,19,18,41,Highest unit cost\n\nPilot conditions: all samples held at 85% relative humidity. Drop trial used identical glass vessels dropped from 80 cm. These are pilot results from one production batch." }
];

export const accepted = ".pdf,.docx,.pptx,.xlsx,.eml,.txt,.md,.csv,.json,.xml,.html,.htm,.css,.js,.py,.log,.png,.jpg,.jpeg,.gif,.bmp,.webp,.wav,.mp3,.aiff,.aac,.ogg,.flac,.mp4,.mpeg,.mov,.avi,.webm,.wmv,.3gp";
export const isClip = (name: string) => /\.(wav|mp3|aiff|aac|ogg|flac|mp4|mpeg|mov|avi|webm|wmv|3gp)$/i.test(name);
export const api = process.env.NEXT_PUBLIC_API_ORIGIN ?? (process.env.NODE_ENV === "development" ? "http://127.0.0.1:7860" : "");

export function sizeLabel(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(api + "/api/v1/" + path, { cache: "no-store", ...init });
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof result?.detail === "string" ? result.detail : "The server could not finish this request. Try again.";
    throw new ApiError(response.status, message);
  }
  return result as T;
}

export const listConversations = (signal?: AbortSignal) => request<Conversation[]>("conversations", { signal });

export function createConversation(source: Source, starter?: string) {
  const body = new FormData();
  body.set("name", source.name);
  if (starter) body.set("starter", starter);
  if (source.file) body.set("file", source.file);
  else if (source.url) body.set("url", source.url);
  return request<Conversation>("conversations", { method: "POST", body });
}

export function changeConversation(id: string, changes: { title?: string; pinned?: boolean }) {
  return request<Conversation>("conversations/" + id, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes),
  });
}

export const deleteConversation = (id: string) => request("conversations/" + id, { method: "DELETE" });

export function passageLabel(passage: Passage) {
  if (!passage.location) return "Passage " + passage.id;
  const labels = { page: "Page", slide: "Slide", sheet: "Sheet", passage: "Passage" };
  return labels[passage.kind] + " " + passage.location;
}

export const verifyAnswer = (id: string, index: number, signal: AbortSignal) =>
  request<EvidenceAnswer>("conversations/" + id + "/turns/" + index + "/verify", { method: "POST", signal });

export async function readPreview(id: string, item: number, signal: AbortSignal): Promise<SourcePreview> {
  const response = await fetch(api + "/api/v1/conversations/" + id + "/preview?item=" + item, { signal });
  if (!response.ok) {
    const result = await response.json().catch(() => null);
    throw new ApiError(response.status, typeof result?.detail === "string" ? result.detail : "Could not open the source preview.");
  }
  if (response.headers.get("Content-Type")?.startsWith("image/png")) {
    const count = Number(response.headers.get("X-Preview-Count")) || item;
    return { kind: "page", count, url: URL.createObjectURL(await response.blob()) };
  }
  return response.json();
}

type ChatEvent =
  | { type: "stage"; stage: ChatStage }
  | { type: "result"; data: { conversation: Conversation } }
  | { type: "error"; message: string; status: number };

export async function askSource(id: string, question: string, signal: AbortSignal,
                                onStage: (stage: ChatStage) => void) {
  const body = new FormData();
  body.set("conversation_id", id);
  body.set("payload", JSON.stringify({ questions: [question] }));
  const response = await fetch(api + "/api/v1/chat?stream=true", { method: "POST", body, signal });
  if (!response.ok || !response.body) {
    const result = await response.json().catch(() => null);
    throw new ApiError(response.status, typeof result?.detail === "string" ? result.detail : "Could not start this answer.");
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let pending = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      const lines = (pending + value).split("\n");
      pending = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event: ChatEvent = JSON.parse(line);
        if (event.type === "stage") onStage(event.stage);
        if (event.type === "error") throw new ApiError(event.status, event.message);
        if (event.type === "result" && event.data.conversation) return event.data.conversation;
      }
    }
    throw new Error("The connection closed before the answer arrived. Try again.");
  } finally {
    await reader.cancel().catch(() => {});
  }
}
