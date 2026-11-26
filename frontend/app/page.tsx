"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { AudioLines, BookOpen, Check, ChevronDown, ChevronRight, CircleHelp, Clipboard, FileText, FolderOpen, KeyRound, Link2, List, Menu, MessageSquare, Plus, Send, Settings2, Square, Table2, Upload, X } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Mark, SourceArt } from "./art";
import { accepted, api, ApiError, askSource, examples, isClip, sizeLabel, type Source, type Turn } from "./sources";

type Chat = {
  id: string; source: Source; turns: Turn[]; draft: string; error?: string;
  pending?: string; sourceId?: string; starter?: string;
};
type Settings = { requires_token: boolean; max_file_mb: number; direct_media_mb: number };

function sourceLabel(source: Source) {
  if (source.url) return new URL(source.url).hostname;
  const ext = source.name.split(".").pop();
  return ext && ext !== source.name ? ext.toUpperCase() + " file" : "File";
}

function CopyAnswer({ answer }: { answer: string }) {
  const [label, setLabel] = useState("Copy");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  async function copy() {
    try { await navigator.clipboard.writeText(answer); setLabel("Copied"); }
    catch { setLabel("Select text to copy"); }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setLabel("Copy"), 2000);
  }
  return <button className="copy" onClick={copy}>{label === "Copied" ? <Check /> : <Clipboard />}{label}</button>;
}

export default function Workspace() {
  const [chats, setChats] = useState<Chat[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const chat = chats.find(c => c.id === active);
  const [mode, setMode] = useState<"file" | "link">("file");
  const [url, setUrl] = useState("");
  const [sourceError, setSourceError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [settings, setSettings] = useState<Settings>();
  const [offline, setOffline] = useState(false);
  const [token, setToken] = useState("");
  const [keyDraft, setKeyDraft] = useState("");
  const [panel, setPanel] = useState<"formats" | "access" | "navigation" | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const requests = useRef(new Map<string, AbortController>());
  const [connectionAttempt, setConnectionAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    fetch(api + "/api/v1/workspace", { signal: ctrl.signal }).then(async r => {
      if (!r.ok) throw new Error();
      const value = await r.json();
      setSettings(value); setOffline(false);
    }).catch(() => { if (!ctrl.signal.aborted) setOffline(true); });
    return () => ctrl.abort();
  }, [connectionAttempt]);
  useEffect(() => {
    if (panel && !dialog.current?.open) dialog.current?.showModal();
    if (!panel && dialog.current?.open) dialog.current.close();
  }, [panel]);
  useEffect(() => {
    if (chat?.turns.length || chat?.pending) bottom.current?.scrollIntoView({ block: "end" });
  }, [active, chat?.pending, chat?.turns.length]);
  useEffect(() => {
    const controllers = requests.current;
    return () => controllers.forEach(c => c.abort());
  }, []);

  function update(id: string, changes: Partial<Chat>) {
    setChats(all => all.map(c => c.id === id ? { ...c, ...changes } : c));
  }
  function select(id: string | null) {
    setActive(id); setPanel(null); setSourceError("");
  }
  function openSource(source: Source, starter?: string) {
    const id = crypto.randomUUID?.() ?? String(Date.now());
    setChats(all => [{ id, source, turns: [], draft: "", starter }, ...all]);
    select(id); setUrl(""); setMode("file");
  }
  function acceptFile(files: FileList | null) {
    if (!files?.length) return;
    const f = files[0];
    let error = "";
    if (files.length > 1) error = "Choose one source for this conversation.";
    else if (!f.size) error = "This file is empty. Choose a file with readable content.";
    else if (!accepted.split(",").some(ext => f.name.toLowerCase().endsWith(ext)) && !f.type.startsWith("text/")) error = "This file type is unsupported. See supported sources for other formats.";
    else if (settings && f.size > settings.max_file_mb * 1024 ** 2) error = "This file exceeds the server limit of " + settings.max_file_mb + " MB.";
    else if (settings && isClip(f.name) && f.size >= settings.direct_media_mb * 1024 ** 2) error = "Choose a clip under " + settings.direct_media_mb + " MB or upload its transcript.";
    if (error) setSourceError(error);
    else openSource({ name: f.name, file: f });
  }
  function openLink(e: FormEvent) {
    e.preventDefault();
    try {
      const link = new URL(url.trim());
      if (!["http:", "https:"].includes(link.protocol) || link.href.length > 2048) throw new Error();
      const last = link.pathname.split("/").filter(Boolean).pop();
      openSource({ name: last ? decodeURIComponent(last) : link.hostname, url: link.href });
    } catch { setSourceError("Enter a complete http or https link to the source."); }
  }
  function chooseExample(example: typeof examples[number]) {
    const file = new File([example.content], example.filename, { type: "text/plain" });
    openSource({ name: file.name, file }, example.prompt);
  }
  function openAccess() { setKeyDraft(token); setPanel("access"); }
  async function send(e: FormEvent) {
    e.preventDefault();
    if (!chat || requests.current.has(chat.id)) return;
    const question = chat.draft.trim();
    if (question.length < 3) { update(chat.id, { error: "Enter at least 3 characters." }); return; }
    if (settings?.requires_token && !token) { openAccess(); return; }
    const { id, source, sourceId, turns } = chat;
    const ctrl = new AbortController();
    requests.current.set(id, ctrl);
    update(id, { pending: question, draft: "", error: "" });
    try {
      let result;
      try { result = await askSource(source, sourceId, turns, question, token, ctrl.signal); }
      catch (e) {
        if (!(e instanceof ApiError && e.status === 410 && sourceId)) throw e;
        result = await askSource(source, undefined, turns, question, token, ctrl.signal);
      }
      update(id, { turns: [...turns, { question, answer: result.answer }], sourceId: result.sourceId, pending: undefined });
    } catch (e) {
      const auth = e instanceof ApiError && e.status === 401;
      const error = ctrl.signal.aborted ? "Request stopped. Your question is ready to edit." :
        auth ? "This server requires a valid access token. Open Access to update it." :
        e instanceof TypeError ? "Could not reach the API. Check the server connection and try again." :
        e instanceof Error ? e.message : "Could not finish the answer. Try again.";
      update(id, { pending: undefined, draft: question, error });
    } finally { requests.current.delete(id); }
  }
  function startPrompt(q: string) {
    if (chat) update(chat.id, { draft: q, error: "" });
    composer.current?.focus();
  }
  const navigation = <>
    <button className="new-chat" onClick={() => select(null)}><Plus size={18} />New conversation</button>
    <div className="nav-heading">Conversations <span>{chats.length}</span></div>
    <nav aria-label="Conversations">{chats.map(c =>
      <button key={c.id} className={"chat-link" + (active === c.id ? " current" : "")} onClick={() => select(c.id)} aria-current={active === c.id ? "page" : undefined}>
        <MessageSquare /><span>{c.source.name}</span>
      </button>)}</nav>
    {!chats.length && <p className="nav-empty">Your conversations will appear here once you open a source.</p>}
    <div className="rail-bottom"><button onClick={() => setPanel("formats")}><CircleHelp />Supported sources</button>
    <small>Conversations last for this tab.</small></div>
  </>;

  return <div className="app-shell">
    <aside className="rail"><button className="brand" aria-label="Folio home" onClick={() => select(null)}><Mark />Folio</button>{navigation}</aside>
    <main className="main">
      <header className="topbar"><button className="mobile-toggle icon-btn" aria-label="Open conversations" onClick={() => setPanel("navigation")}><Menu /></button>
        <button className="mobile-brand" onClick={() => select(null)} aria-label="Folio home"><Mark />Folio</button><span className="crumb"><FolderOpen />Workspace</span><ChevronRight className="crumb-sep" /><span className="crumb-current">{chat ? "Conversation" : "New conversation"}</span>
        <button className="access-btn" onClick={openAccess}><Settings2 />Access</button></header>
      {!chat ? <div className="landing-scroll"><div className="landing">
        <section className="intro"><div><h1>Open a source.</h1><p>Bring a document, a dataset, or a link.<br />Ask questions and follow the details.</p></div><SourceArt /></section>
        <section className="intake" aria-label="Choose your source">
          <div className="intake-tabs" role="group" aria-label="Source input"><button aria-pressed={mode === "file"} onClick={() => { setMode("file"); setSourceError(""); }}><Upload />Upload file</button>
            <button aria-pressed={mode === "link"} onClick={() => { setMode("link"); setSourceError(""); }}><Link2 />Paste link</button></div>
          {mode === "file" ? <div className={"drop-zone" + (dragging ? " dragging" : "")} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
            onDrop={e => { e.preventDefault(); setDragging(false); acceptFile(e.dataTransfer.files); }}>
            <div className="upload-symbol"><Upload /></div><h2>{dragging ? "Drop to open your source" : "Drop your file here"}</h2>
            <p>PDFs, documents, spreadsheets, slides, and more</p><button className="primary" onClick={() => picker.current?.click()}>Choose a file</button>
            <input ref={picker} type="file" accept={accepted} hidden onChange={e => { acceptFile(e.target.files); e.target.value = ""; }} />
          </div> : <form className="link-form" onSubmit={openLink}><label htmlFor="source-url">Source link</label>
            <p>Paste a direct link that the server can open.</p><div className="link-row"><input id="source-url" autoFocus type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://example.org/report.pdf" required maxLength={2048} />
            <button className="primary">Open source</button></div></form>}
          {sourceError && <p className="error" role="alert">{sourceError}</p>}
        </section>
        <section className="sample-section"><h2>Try a sample source</h2><div className="examples">{examples.map((ex, i) =>
          <button key={ex.filename} onClick={() => chooseExample(ex)}><span className={"sample-icon s"+i}>{i === 0 ? <AudioLines /> : <Table2 />}</span><span><strong>{ex.title}</strong><small>{ex.kind}</small></span><ChevronRight /></button>)}</div></section>
      </div></div> :
      <div className="chat-view"><header className="source-head"><div className="source-icon"><FileText /></div><div><span>{sourceLabel(chat.source)}{chat.source.file ? " / " + sizeLabel(chat.source.file.size) : ""}</span><h1>{chat.source.name}</h1></div>
        {chat.turns.length > 0 && <details className="question-index" key={chat.id}><summary><List /><span>Questions</span><ChevronDown /></summary><div>{chat.turns.map((t,i) =>
          <button key={i} onClick={e => { e.currentTarget.closest("details")?.removeAttribute("open"); document.getElementById("turn-"+i)?.scrollIntoView({block:"start"}); }}>{t.question}</button>)}</div></details>}</header>
        <div className="thread" key={chat.id}><div className="thread-inner">
          {!chat.turns.length && !chat.pending && <section className="chat-start"><Mark /><h2>What would you like to know?</h2><p>Ask about this source, then follow up as you read.</p>
            <div className="suggestions">{[chat.starter || "Summarize the key points.", "Which details deserve a closer look?"].map(q => <button onClick={() => startPrompt(q)} key={q}>{q}</button>)}</div></section>}
          {chat.turns.map((t,i) => <article id={"turn-"+i} className="exchange" key={i}><p className="user-message">{t.question}</p><div className="answer-name"><Mark />Folio</div>
            <div className="answer"><Markdown remarkPlugins={[remarkGfm]} components={{img: () => null}}>{t.answer}</Markdown></div><CopyAnswer answer={t.answer} /></article>)}
          {chat.pending && <article className="exchange"><p className="user-message">{chat.pending}</p><div className="thinking" role="status"><Mark />{chat.turns.length ? "Reading your follow-up…" : "Reading your source…"}</div></article>}
          <div ref={bottom} /></div></div>
        <div className="composer-area">{chat.error && <p className="error" role="alert">{chat.error} {chat.error.includes("token") && <button onClick={openAccess}>Access</button>}</p>}
          <form className="composer" onSubmit={send}><textarea ref={composer} aria-label="Your question" rows={2} maxLength={1000} value={chat.draft} disabled={!!chat.pending}
            placeholder={chat.turns.length ? "Ask a follow-up question…" : "Ask about this source…"}
            onChange={e => update(chat.id, { draft: e.target.value, error: "" })}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
            {chat.pending ? <button type="button" aria-label="Stop waiting for answer" className="send" onClick={() => requests.current.get(chat.id)?.abort()}><Square /></button>
              : <button className="send" aria-label="Send question" disabled={!chat.draft.trim()}><Send /></button>}</form>
          <small>Enter to send <span>/</span> Shift + Enter for a new line</small></div>
      </div>}
    </main>
    <dialog ref={dialog} onCancel={() => setPanel(null)} onClose={() => setPanel(null)} aria-labelledby="dialog-title" onClick={e => { if (e.target === e.currentTarget) setPanel(null); }}>
      <div className="modal-body"><button className="modal-close icon-btn" aria-label="Close dialog" onClick={() => setPanel(null)}><X /></button>
        {panel === "navigation" ? <><h2 id="dialog-title">Workspace</h2><div className="mobile-nav">{navigation}</div></> : panel === "formats" ? <>
          <BookOpen className="modal-icon" /><h2 id="dialog-title">Supported sources</h2><dl className="format-list"><dt>Documents and data</dt><dd>PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), email (.eml), and plain-text files including Markdown, CSV, and code.</dd>
          <dt>Images</dt><dd>PNG, JPEG, GIF, BMP, and WebP.</dd><dt>Audio and video</dt><dd>{settings ? "Short clips under "+settings.direct_media_mb+" MB use direct analysis." : "Short clips use your server’s direct analysis limit."} For longer recordings, open a transcript.</dd></dl>
          {settings && <p>Maximum source size on this server: {settings.max_file_mb} MB.</p>}</> : <>
          <KeyRound className="modal-icon" /><h2 id="dialog-title">Server access</h2><p>{offline ? "Could not reach the API to check its settings." : settings ? settings.requires_token ? "This server requires a bearer token." : "This server allows requests without a token." : "Checking the server settings…"}</p>
          {offline && <button onClick={() => setConnectionAttempt(n => n+1)}>Check connection</button>}
          <form className="access-form" onSubmit={e => { e.preventDefault(); setToken(keyDraft.trim()); setPanel(null); }}>
            <label htmlFor="key">Bearer token</label><input id="key" type="password" autoComplete="off" value={keyDraft} onChange={e => setKeyDraft(e.target.value)} placeholder="Enter your server token" />
            <small>Held in memory until you close or refresh this tab.</small><button className="primary">Save access settings</button></form></>}
      </div></dialog>
  </div>;
}
