"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, ChevronLeft, ChevronRight, ScanSearch, X } from "lucide-react";
import { Answer } from "./answer";
import { passageLabel, readPreview, verifyAnswer, type EvidenceAnswer, type OpenCitation, type Passage, type SourcePreview } from "./sources";

export function AnswerCheck({ id, index, onCitation }: {
  id: string; index: number; onCitation: OpenCitation;
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<EvidenceAnswer>();
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function check() {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError("");
    try {
      setResult(await verifyAnswer(id, index, controller.signal));
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Could not check this answer.");
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <>
    <button type="button" className="copy" onClick={check} disabled={busy}>
      <ScanSearch />{busy ? "Checking sources…" : result ? "Check again" : "Check this answer"}
    </button>
    {busy && <span className="sr-only" role="status">Searching for supporting and conflicting evidence.</span>}
    {error && <p className="error" role="alert">{error}</p>}
    {result && <section className="answer-check">
      <h2>Evidence check</h2>
      <Answer content={result.answer} citations={result.citations} onCitation={onCitation} />
    </section>}
  </>;
}

export function SourceDrawer({ id, name, passage, missingReference, turnIndex, onCitation, close }: {
  id: string; name: string; passage?: Passage; missingReference?: number; turnIndex?: number;
  onCitation: OpenCitation; close: () => void;
}) {
  const drawer = useRef<HTMLDialogElement>(null);
  const [item, setItem] = useState(passage?.location ?? 1);
  const [preview, setPreview] = useState<SourcePreview>();
  const [error, setError] = useState("");
  const canPreview = !passage || passage.kind !== "passage" || /\.(pdf|xlsx|pptx)$/i.test(name);
  const [loading, setLoading] = useState(canPreview);

  useEffect(() => {
    const element = drawer.current;
    if (!element) return;
    const mobile = matchMedia("(max-width: 900px)");
    function position() {
      if (!element) return;
      if (element.open) element.close();
      if (mobile.matches) element.showModal();
      else element.show();
    }
    position();
    mobile.addEventListener("change", position);
    return () => {
      mobile.removeEventListener("change", position);
      element.close();
    };
  }, []);

  useEffect(() => {
    if (!canPreview) return;
    const controller = new AbortController();
    let image: string | undefined;
    readPreview(id, item, controller.signal).then(result => {
      if (result.kind === "page") image = result.url;
      if (controller.signal.aborted) {
        if (image) URL.revokeObjectURL(image);
        return;
      }
      setPreview(result);
    }).catch(error => {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Could not open the preview.");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => {
      controller.abort();
      if (image) URL.revokeObjectURL(image);
    };
  }, [id, item, canPreview]);

  function move(step: number) {
    if (loading) return;
    setLoading(true); setError(""); setItem(item + step);
  }

  const location = preview?.kind === "sheet" ? "Sheet" : preview?.kind === "slide" ? "Slide" : "Page";
  return <dialog ref={drawer} className="source-drawer" aria-labelledby="source-drawer-title"
    onCancel={event => { event.preventDefault(); close(); }}
    onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); close(); } }}>
    <header className="drawer-head"><BookOpen />
      <div><h2 id="source-drawer-title">Source</h2><span title={name}>{name}</span></div>
      <button className="icon-btn" onClick={close} aria-label="Close source" autoFocus><X /></button>
    </header>
    <div className="drawer-content">
      {missingReference !== undefined && <section className="source-passage">
        <h3>Source {missingReference}</h3>
        <p className="preview-status">This saved answer has no excerpt or page number for this reference.</p>
        {turnIndex !== undefined && <AnswerCheck id={id} index={turnIndex} onCitation={onCitation} />}
      </section>}
      {passage && <section className="source-passage">
        <h3>{passageLabel(passage)} excerpt</h3>
        <Answer content={passage.text} />
      </section>}
      {canPreview && <section className="source-preview" aria-label="Document preview">
        {error && <p className="preview-status" role="status">{error}</p>}
        {preview && <nav className="preview-nav" aria-label={location + " navigation"}>
            <button className="icon-btn" aria-label={"Previous " + location.toLowerCase()} disabled={item <= 1} onClick={() => move(-1)}><ChevronLeft /></button>
            <span>{location} {item} of {preview.count}</span>
            <button className="icon-btn" aria-label={"Next " + location.toLowerCase()} disabled={item >= preview.count} onClick={() => move(1)}><ChevronRight /></button>
        </nav>}
        {loading && <p className="preview-status" role="status">Opening source preview…</p>}
        {preview && !loading && !error && <>
          {preview.kind === "page" ? <img src={preview.url} alt={name + ", page " + item} />
            : preview.kind === "slide" ? <div className="slide-preview"><h3>{preview.title}</h3><p>{preview.text || "No readable text on this slide."}</p></div>
            : <><h3>{preview.title}</h3>
              {preview.limited && <p className="preview-status">Showing the first 40 rows and 12 columns.</p>}
              <div className="answer-table" role="region" aria-label="Worksheet cells" tabIndex={0}>
                <table><tbody>{preview.rows.map((row, index) => <tr key={index}>{row.map((cell, column) => <td key={column}>{cell}</td>)}</tr>)}</tbody></table>
              </div></>}
        </>}
      </section>}
    </div>
  </dialog>;
}
