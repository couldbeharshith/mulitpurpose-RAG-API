export type Source = { name: string; file?: File; url?: string };
export type Turn = { question: string; answer: string };
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

export async function askSource(id: string, question: string, signal: AbortSignal) {
  const body = new FormData();
  body.set("conversation_id", id);
  body.set("payload", JSON.stringify({ questions: [question] }));
  const result = await request<{ conversation: Conversation }>("chat", { method: "POST", body, signal });
  if (!result?.conversation) throw new Error("The server returned an unreadable answer.");
  return result.conversation;
}
