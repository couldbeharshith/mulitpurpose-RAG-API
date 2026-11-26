"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

const minimum = 216;
const maximum = 420;
const defaultWidth = 256;
const storageKey = "plexrag-sidebar-width";

function clampWidth(value: number) {
  return Math.round(Math.min(Math.max(value, minimum), maximum));
}

export function ResizableSidebar({ collapsed, children }: { collapsed: boolean; children: ReactNode }) {
  const [width, setWidth] = useState(defaultWidth);
  const [viewportLimit, setViewportLimit] = useState(maximum);
  const [resizing, setResizing] = useState(false);
  const rail = useRef<HTMLElement>(null);
  const drag = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null);

  useEffect(() => {
    function measure() {
      setViewportLimit(clampWidth(window.innerWidth * .45));
    }
    measure();
    window.addEventListener("resize", measure);
    try {
      const saved = Number(localStorage.getItem(storageKey));
      if (saved > 0) setWidth(clampWidth(saved));
    } catch { /* The default still works with storage disabled. */ }
    return () => window.removeEventListener("resize", measure);
  }, []);

  function update(value: number, persist = false) {
    const width = clampWidth(value);
    setWidth(width);
    if (persist) {
      try { localStorage.setItem(storageKey, String(width)); } catch { /* The width still applies to this tab. */ }
    }
  }

  return <aside className="rail" ref={rail} data-collapsed={collapsed} style={{ "--rail-width": width + "px" } as CSSProperties}>
    {children}
    {!collapsed && <div
      className="rail-resize"
      data-resizing={resizing}
      tabIndex={0}
      role="separator"
      aria-label="Resize conversation sidebar"
      aria-orientation="vertical"
      aria-controls="desktop-history"
      aria-valuemin={minimum}
      aria-valuemax={viewportLimit}
      aria-valuenow={Math.min(width, viewportLimit)}
      title="Drag to resize. Double-click to reset."
      onPointerDown={event => {
        if (!event.isPrimary || event.button !== 0) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { pointerId: event.pointerId, startX: event.clientX, startWidth: rail.current?.offsetWidth ?? width };
        setResizing(true);
      }}
      onPointerMove={event => {
        const active = drag.current;
        if (active?.pointerId === event.pointerId) {
          update(Math.min(viewportLimit, active.startWidth + event.clientX - active.startX));
        }
      }}
      onPointerUp={event => {
        const active = drag.current;
        if (active?.pointerId !== event.pointerId) return;
        if (event.clientX !== active.startX) {
          update(Math.min(viewportLimit, active.startWidth + event.clientX - active.startX), true);
        }
      }}
      onLostPointerCapture={() => { drag.current = null; setResizing(false); }}
      onDoubleClick={() => update(defaultWidth, true)}
      onKeyDown={event => {
        const measured = rail.current?.offsetWidth ?? width;
        const step = event.shiftKey ? 32 : 12;
        const next = {
          ArrowLeft: measured - step, ArrowRight: measured + step, Home: minimum, End: viewportLimit,
        }[event.key];
        if (next !== undefined) {
          event.preventDefault();
          update(Math.min(next, viewportLimit), true);
        }
      }}
    />}
  </aside>;
}
