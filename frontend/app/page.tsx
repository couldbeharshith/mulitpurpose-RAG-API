"use client";

import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { ArrowDown, AudioLines, BookOpen, Check, ChevronDown, ChevronRight, CircleHelp, Clipboard, FileText, FolderOpen, Link2, List, Menu, MessagesSquare, MoreHorizontal, PanelLeftClose, PanelLeftOpen, Pin, Plus, Search, Send, Square, Table2, Upload, X } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Mark, SourceArt } from "./art";
import { ResizableSidebar } from "./sidebar";
import { ThemeControl } from "./theme";
import { accepted, api, ApiError, askSource, changeConversation, createConversation, deleteConversation, examples, isClip, listConversations, sizeLabel, type Conversation, type RagMode, type Source } from "./sources";

type Chat = Conversation & { draft?: string; error?: string; pending?: string; ragMode?: RagMode };
type Settings = { max_file_mb: number; direct_media_mb: number };

function activityDate(value: string) {
  const date = new Date(value);
  return date.toDateString() === new Date().toDateString()
    ? "Today"
    : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function fitComposer(field: HTMLTextAreaElement) {
  field.style.height = "auto";
  field.style.height = Math.min(field.scrollHeight + 2, 144) + "px";
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
  const [chatFilter, setChatFilter] = useState("");
  const chat = chats.find(c => c.id === active);
  const [mode, setMode] = useState<"file" | "link">("file");
  const [url, setUrl] = useState("");
  const [sourceError, setSourceError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [settings, setSettings] = useState<Settings>();
  const [panel, setPanel] = useState<"formats" | "navigation" | "rename" | "delete" | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [opening, setOpening] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [historyAttempt, setHistoryAttempt] = useState(0);
  const [optionsId, setOptionsId] = useState<string | null>(null);
  const [managedId, setManagedId] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [manageBusy, setManageBusy] = useState(false);
  const [manageError, setManageError] = useState("");
  const [awayFromLatest, setAwayFromLatest] = useState(false);
  const managedChat = chats.find(c => c.id === managedId);
  const dialog = useRef<HTMLDialogElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const thread = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const sourceOpening = useRef(false);
  const requests = useRef(new Map<string, AbortController>());

  useEffect(() => {
    const controller = new AbortController();
    listConversations(controller.signal).then(saved => {
      setChats(current => [...current, ...saved.filter(item => !current.some(chat => chat.id === item.id))]);
      try {
        const last = sessionStorage.getItem("plexrag-active-chat");
        if (last && saved.some(item => item.id === last)) setActive(current => current ?? last);
      } catch { /* The saved conversations remain available in the sidebar. */ }
      setHistoryError("");
    }).catch(() => {
      if (!controller.signal.aborted) setHistoryError("Couldn’t load chat history.");
    }).finally(() => {
      if (!controller.signal.aborted) setHistoryLoading(false);
    });
    return () => controller.abort();
  }, [historyAttempt]);

  useEffect(() => {
    const ctrl = new AbortController();
    fetch(api + "/api/v1/workspace", { signal: ctrl.signal }).then(async r => {
      if (!r.ok) throw new Error();
      const value = await r.json();
      setSettings(value);
    }).catch(() => {});
    return () => ctrl.abort();
  }, []);
  useEffect(() => {
    if (panel && !dialog.current?.open) dialog.current?.showModal();
    if (!panel && dialog.current?.open) dialog.current.close();
  }, [panel]);
  useLayoutEffect(() => {
    const field = composer.current;
    if (field) fitComposer(field);
  }, [active, chat?.draft]);
  useEffect(() => {
    const field = composer.current;
    if (!field) return;
    let width = field.clientWidth;
    const observer = new ResizeObserver(() => {
      if (field.clientWidth === width) return;
      width = field.clientWidth;
      fitComposer(field);
    });
    observer.observe(field);
    return () => observer.disconnect();
  }, [active]);
  useLayoutEffect(() => {
    const element = thread.current;
    if (element && followLatest.current) element.scrollTop = element.scrollHeight;
  }, [active, chat?.pending, chat?.turns.length, chat?.error, chat?.draft]);
  useEffect(() => {
    const controllers = requests.current;
    return () => controllers.forEach(c => c.abort());
  }, []);

  function update(id: string, changes: Partial<Chat>) {
    setChats(all => all.map(c => c.id === id ? { ...c, ...changes } : c));
  }
  function select(id: string | null) {
    const fromDrawer = panel === "navigation";
    followLatest.current = true;
    setAwayFromLatest(false);
    setActive(id); setPanel(null); setSourceError(""); setOptionsId(null);
    try {
      if (id) sessionStorage.setItem("plexrag-active-chat", id);
      else sessionStorage.removeItem("plexrag-active-chat");
    } catch { /* The conversation can still be selected in this tab. */ }
    if (fromDrawer) requestAnimationFrame(() => {
      document.getElementById(id ? "conversation-title" : "intake-title")?.focus({ preventScroll: true });
    });
  }
  async function openSource(source: Source, starter?: string) {
    if (sourceOpening.current) return;
    sourceOpening.current = true;
    setOpening(true); setSourceError("");
    try {
      const saved = await createConversation(source, starter);
      setChats(all => [saved, ...all.filter(c => c.id !== saved.id)]);
      select(saved.id); setChatFilter(""); setUrl(""); setMode("file");
    } catch (error) {
      setSourceError(error instanceof ApiError ? error.message : "Couldn’t save this source. Check the server and try again.");
    } finally {
      sourceOpening.current = false; setOpening(false);
    }
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
  async function send(e: FormEvent) {
    e.preventDefault();
    if (!chat || requests.current.has(chat.id)) return;
    const question = chat.draft?.trim() ?? "";
    if (question.length < 3) { update(chat.id, { error: "Enter at least 3 characters." }); return; }
    const { id } = chat;
    const ctrl = new AbortController();
    requests.current.set(id, ctrl);
    followLatest.current = true; setAwayFromLatest(false);
    setOptionsId(null);
    update(id, { pending: question, draft: "", error: "" });
    try {
      const result = await askSource(id, question, chat.ragMode ?? "fast", ctrl.signal);
      update(id, { ...result, pending: undefined });
    } catch (e) {
      if ((e instanceof ApiError && e.status === 409) || ctrl.signal.aborted) {
        const latest = await listConversations().catch(() => []);
        const saved = latest.find(item => item.id === id);
        if (saved) update(id, saved);
      }
      const error = ctrl.signal.aborted ? "Request stopped. Your question is ready to edit." :
        e instanceof TypeError ? "Could not reach the API. Check the server connection and try again." :
        e instanceof Error ? e.message : "Could not finish the answer. Try again.";
      update(id, { pending: undefined, draft: question, error });
    } finally { requests.current.delete(id); }
  }
  function startPrompt(q: string) {
    if (chat) update(chat.id, { draft: q, error: "" });
    composer.current?.focus();
  }
  function syncScroll() {
    const element = thread.current;
    if (!element) return;
    followLatest.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
    setAwayFromLatest(!followLatest.current);
  }
  function jumpToLatest() {
    if (thread.current) thread.current.scrollTop = thread.current.scrollHeight;
    followLatest.current = true; setAwayFromLatest(false);
  }
  function openManage(chat: Chat, action: "rename" | "delete") {
    setManagedId(chat.id); setTitleDraft(chat.title);
    setManageError(""); setOptionsId(null); setPanel(action);
  }
  async function manage(event: FormEvent) {
    event.preventDefault();
    if (!managedChat || manageBusy) return;
    setManageBusy(true); setManageError("");
    try {
      if (panel === "delete") {
        await deleteConversation(managedChat.id);
        setChats(all => all.filter(c => c.id !== managedChat.id));
        if (active === managedChat.id) select(null);
      } else {
        const renamed = await changeConversation(managedChat.id, { title: titleDraft });
        update(managedChat.id, { title: renamed.title });
      }
      setPanel(null);
    } catch (error) {
      setManageError(error instanceof ApiError ? error.message : "Couldn’t update this conversation. Try again.");
    } finally { setManageBusy(false); }
  }
  async function togglePin(chat: Chat) {
    setOptionsId(null);
    try {
      const saved = await changeConversation(chat.id, { pinned: !chat.pinned });
      update(chat.id, { pinned: saved.pinned });
    }
    catch { setHistoryError("Couldn’t update this pin. Try again."); }
  }
  const query = chatFilter.trim().toLowerCase();
  const visibleChats = chats.filter(c => c.title.toLowerCase().includes(query) ||
    c.source.name.toLowerCase().includes(query) || c.turns.some(turn => turn.question.toLowerCase().includes(query)))
    .sort((first, second) => Number(second.pinned) - Number(first.pinned) ||
      Date.parse(second.updated_at) - Date.parse(first.updated_at));
  const navigation = <>
    <button className="new-chat" disabled={opening} onClick={() => select(null)}><Plus size={18} />New conversation</button>
    <h2 className="nav-heading">Conversations {chats.length > 0 && <span>{chats.length}</span>}</h2>
    {chats.length > 0 && <label className="chat-search"><Search />
      <input aria-label="Search conversations" type="search" placeholder="Search conversations" value={chatFilter} onChange={e => setChatFilter(e.target.value)} />
    </label>}
    {historyLoading && <p className="nav-empty" role="status">Loading conversations…</p>}
    {historyError && <div className="history-error" role="alert">{historyError}
      <button onClick={() => { setHistoryError(""); setHistoryLoading(true); setHistoryAttempt(n => n + 1); }}>Reload history</button>
    </div>}
    <nav className="chat-nav" aria-label="Conversations">{visibleChats.map(c => {
      const Icon = c.source.url ? Link2 : isClip(c.source.name) ? AudioLines : FileText;
      return <div className="chat-entry" key={c.id} onKeyDown={event => { if (event.key === "Escape") setOptionsId(null); }}>
        <div className="chat-row" data-current={active === c.id}>
        <button className="chat-link" onClick={() => select(c.id)} aria-current={active === c.id ? "page" : undefined} title={c.title}>
          <span className="chat-entry-icon"><Icon /></span>
          <span className="chat-entry-text"><strong>{c.pinned && <Pin className="chat-pin" aria-label="Pinned" />}{c.title}</strong>
            <small><span>{c.pending ? "Working…" : c.source.name}</span><time dateTime={c.updated_at}>{activityDate(c.updated_at)}</time></small>
          </span>
          {c.pending && <span className="chat-activity" aria-hidden="true" />}
        </button>
        <button className="chat-options icon-btn" aria-label={"Options for " + c.title}
          aria-expanded={optionsId === c.id} disabled={!!c.pending}
          onClick={() => setOptionsId(optionsId === c.id ? null : c.id)}><MoreHorizontal /></button>
        </div>
        {optionsId === c.id && <div className="chat-actions" role="group" aria-label={"Manage " + c.title}>
          <button onClick={() => openManage(c, "rename")}>Rename</button>
          <button onClick={() => togglePin(c)}>{c.pinned ? "Unpin" : "Pin"}</button>
          <button className="danger-text" onClick={() => openManage(c, "delete")}>Delete</button>
        </div>}
        {active === c.id && c.turns.length > 0 && <ol className="edge-tabs" aria-label="Questions in this conversation">
          {c.turns.map((turn, index) => <li key={index}><button title={turn.question} onClick={() => {
            setPanel(null);
            document.getElementById("turn-" + index)?.scrollIntoView({ block: "start" });
          }}>{turn.question}</button></li>)}
        </ol>}
      </div>;
    })}</nav>
    {!chats.length && !historyLoading && !historyError && <div className="nav-empty"><MessagesSquare /><p>Open a source to start a conversation.</p></div>}
    {chats.length > 0 && !visibleChats.length && <p className="nav-empty" role="status">No matching conversations.</p>}
    <div className="rail-bottom"><button onClick={() => setPanel("formats")}><CircleHelp />Supported sources</button>
    <small>History is saved on this server.</small></div>
  </>;

  return <div className="app-shell">
    <ResizableSidebar collapsed={collapsed}>
      <div className="rail-head"><button className="brand" aria-label="PlexRAG home" onClick={() => select(null)}><Mark /><span>PlexRAG</span></button>
        <button className="rail-collapse icon-btn" aria-label={collapsed ? "Expand conversations" : "Collapse conversations"}
          aria-expanded={!collapsed} aria-controls="desktop-history" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
        </button></div>
      <div className="rail-content" id="desktop-history" hidden={collapsed}>{navigation}</div>
      {collapsed && <button className="rail-new icon-btn" aria-label="New conversation" title="New conversation" disabled={opening} onClick={() => select(null)}><Plus /></button>}
    </ResizableSidebar>
    <main className="main">
      <header className={"topbar" + (chat ? " conversation-bar" : "")} data-rail-collapsed={collapsed}>
        <button className="mobile-toggle icon-btn" aria-label="Open conversations" onClick={() => setPanel("navigation")}><Menu /></button>
        {chat ? <>
          <div className="conversation-source">
            <div className="source-icon">{chat.source.url ? <Link2 /> : <FileText />}</div>
            <div className="source-caption">
              <h1 id="conversation-title" tabIndex={-1} title={chat.title}>{chat.title}</h1>
              <span className="source-description" title={chat.source.name}>{chat.source.name}{chat.source.size != null ? " / " + sizeLabel(chat.source.size) : ""}</span>
            </div>
          </div>
          {chat.turns.length > 0 && <details className="question-index" key={chat.id}><summary aria-label="Questions"><List /><span>Questions</span><ChevronDown /></summary><div>{chat.turns.map((t,i) =>
            <button key={i} onClick={e => { e.currentTarget.closest("details")?.removeAttribute("open"); document.getElementById("turn-"+i)?.scrollIntoView({block:"start"}); }}>{t.question}</button>)}</div></details>}
        </> : <>
          <button className="mobile-brand" onClick={() => select(null)} aria-label="PlexRAG home"><Mark />PlexRAG</button>
          <span className="crumb"><FolderOpen />Workspace</span>
        </>}
        <ThemeControl /></header>
      {!chat ? <div className="landing-scroll"><div className="landing">
        <section className="intro"><div><h1 id="intake-title" tabIndex={-1}>Open a source.</h1><p>Bring a document, a dataset, or a link.<br />Ask questions and follow the details.</p></div><SourceArt /></section>
        <section className="intake" aria-label="Choose your source">
          <div className="intake-tabs" role="group" aria-label="Source input"><button aria-pressed={mode === "file"} onClick={() => { setMode("file"); setSourceError(""); }}><Upload />Upload file</button>
            <button aria-pressed={mode === "link"} onClick={() => { setMode("link"); setSourceError(""); }}><Link2 />Paste link</button></div>
          {mode === "file" ? <div className={"drop-zone" + (dragging ? " dragging" : "")} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
            onDrop={e => { e.preventDefault(); setDragging(false); acceptFile(e.dataTransfer.files); }}>
            <div className="upload-symbol"><Upload /></div><h2>{dragging ? "Drop to open your source" : "Drop your file here"}</h2>
            <p>PDFs, documents, spreadsheets, slides, and more</p><button className="primary" disabled={opening} onClick={() => picker.current?.click()}>{opening ? "Saving source…" : "Choose a file"}</button>
            <input ref={picker} type="file" accept={accepted} hidden onChange={e => { acceptFile(e.target.files); e.target.value = ""; }} />
          </div> : <form className="link-form" onSubmit={openLink}><label htmlFor="source-url">Source link</label>
            <p>Paste a direct link that the server can open.</p><div className="link-row"><input id="source-url" autoFocus type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://example.org/report.pdf" required maxLength={2048} />
            <button className="primary" disabled={opening}>{opening ? "Saving source…" : "Open source"}</button></div></form>}
          {sourceError && <p className="error" role="alert">{sourceError}</p>}
        </section>
        <section className="sample-section"><h2>Try a sample source</h2><div className="examples">{examples.map((ex, i) =>
          <button key={ex.filename} onClick={() => chooseExample(ex)}><span className={"sample-icon s"+i}>{i === 0 ? <AudioLines /> : <Table2 />}</span><span><strong>{ex.title}</strong><small>{ex.kind}</small></span><ChevronRight /></button>)}</div></section>
      </div></div> :
      <div className="chat-view">
        <div className="thread" ref={thread} key={chat.id} onScroll={syncScroll}><div className="thread-inner">
          {!chat.turns.length && !chat.pending && <section className="chat-start"><Mark /><h2>What would you like to know?</h2><p>Ask about this source, then follow up as you read.</p>
            <div className="suggestions">{[chat.starter || "Summarize the key points.", "Which details deserve a closer look?"].map(q => <button onClick={() => startPrompt(q)} key={q}>{q}</button>)}</div></section>}
          {chat.turns.map((t,i) => <article id={"turn-"+i} className="exchange" key={i}><p className="user-message">{t.question}</p><div className="answer-name"><Mark />PlexRAG</div>
            <div className="answer"><Markdown remarkPlugins={[remarkGfm]} components={{img: () => null}}>{t.answer}</Markdown></div><CopyAnswer answer={t.answer} /></article>)}
          {chat.pending && <article className="exchange"><p className="user-message">{chat.pending}</p><div className="thinking" role="status">
            <span className="scan-mark"><Mark /></span>
            <span>{chat.turns.length ? "Working on your follow-up" : "Working through your source"}<span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span></span>
          </div></article>}
          </div></div>
        <div className="composer-area">{awayFromLatest && <button className="jump-latest" onClick={jumpToLatest}><ArrowDown />Jump to latest</button>}{chat.error && <p className="error" role="alert">{chat.error}</p>}
          <form className="composer" onSubmit={send}><textarea ref={composer} aria-label="Your question" rows={1} maxLength={1000} value={chat.draft ?? ""} disabled={!!chat.pending}
            placeholder={chat.turns.length ? "Ask a follow-up question…" : "Ask about this source…"}
            onChange={e => update(chat.id, { draft: e.target.value, error: "" })}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
            {chat.pending ? <button type="button" aria-label="Stop waiting for answer" className="send" onClick={() => requests.current.get(chat.id)?.abort()}><Square /></button>
              : <button className="send" aria-label="Send question" disabled={!chat.draft?.trim()}><Send /></button>}</form>
          <div className="composer-options">
            <label className="answer-mode">Answer mode
              <select value={chat.ragMode ?? "fast"} disabled={!!chat.pending}
                onChange={event => update(chat.id, { ragMode: event.target.value === "agentic" ? "agentic" : "fast" })}>
                <option value="fast">Fast</option>
                <option value="agentic">Agentic</option>
              </select>
            </label>
            <small>Enter to send <span>/</span> Shift + Enter for a new line</small>
          </div></div>
      </div>}
    </main>
    <dialog ref={dialog} className={panel === "navigation" ? "history-drawer" : undefined}
      onCancel={event => { if (manageBusy) event.preventDefault(); else setPanel(null); }}
      onClose={() => { setPanel(null); setOptionsId(null); }} aria-labelledby="dialog-title"
      onClick={e => { if (e.target === e.currentTarget && !manageBusy) setPanel(null); }}>
      <div className="modal-body"><button className="modal-close icon-btn" aria-label="Close dialog" disabled={manageBusy} onClick={() => setPanel(null)}><X /></button>
        {panel === "navigation" ? <><h2 id="dialog-title">Workspace</h2><div className="mobile-nav">{navigation}</div></> : panel === "formats" ? <>
          <BookOpen className="modal-icon" /><h2 id="dialog-title">Supported sources</h2><dl className="format-list"><dt>Documents and data</dt><dd>PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), email (.eml), and plain-text files including Markdown, CSV, and code.</dd>
          <dt>Images</dt><dd>PNG, JPEG, GIF, BMP, and WebP.</dd><dt>Audio and video</dt><dd>{settings ? "Short clips under "+settings.direct_media_mb+" MB use direct analysis." : "Short clips use your server’s direct analysis limit."} For longer recordings, open a transcript.</dd></dl>
          {settings && <p>Maximum source size on this server: {settings.max_file_mb} MB.</p>}</> : managedChat && panel ? <>
          <h2 id="dialog-title">{panel === "delete" ? "Delete conversation?" : "Rename conversation"}</h2>
          <form className="manage-form" onSubmit={manage}>
            {panel === "delete" ? <p>This removes “{managedChat.title}” and its saved source from local history.</p>
              : <label>Conversation title<input autoFocus value={titleDraft} maxLength={100} required onChange={e => setTitleDraft(e.target.value)} /></label>}
            {manageError && <p className="error" role="alert">{manageError}</p>}
            <div className="manage-buttons"><button type="button" disabled={manageBusy} onClick={() => setPanel(null)}>Cancel</button>
              <button className={panel === "delete" ? "primary delete-confirm" : "primary"} disabled={manageBusy || (panel === "rename" && !titleDraft.trim())}>{panel === "delete" ? "Delete conversation" : "Save title"}</button></div>
          </form>
        </> : null}
      </div></dialog>
  </div>;
}
