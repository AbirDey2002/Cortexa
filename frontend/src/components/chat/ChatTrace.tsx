import React, { useMemo, useState } from "react";

type ToolCall = {
  name: string;
  started_at?: string;
  finished_at?: string;
  duration_ms?: number;
  ok?: boolean;
  args_preview?: string;
  result_preview?: string;
  chars_read?: number | null;
  error?: string | null;
};

export type Traces = {
  engine?: string | null;
  tool_calls?: ToolCall[];
  planning?: {
    todos?: any[];
    subagents?: any[];
    filesystem_ops?: any[];
  };
  messages?: {
    assistant_final?: string;
  };
};

function truncate(text: string | undefined, n = 160): string {
  if (!text) return "";
  return text.length > n ? text.slice(0, n) + "…" : text;
}

function formatDuration(ms?: number): string {
  if (typeof ms !== "number") return "";
  if (ms < 1000) return `${ms}ms`;
  const s = (ms / 1000).toFixed(1);
  return `${s}s`;
}

function formatTime(ts?: string): string {
  try {
    if (!ts) return "";
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString();
  } catch {
    return ts || "";
  }
}

export const ChatTrace: React.FC<{ traces: Traces; defaultOpen?: boolean }> = ({ traces, defaultOpen = false }) => {
  const [open, setOpen] = useState<boolean>(defaultOpen);

  const toolsSorted: ToolCall[] = useMemo(() => {
    const arr = [...(traces.tool_calls || [])];
    arr.sort((a, b) => (a.started_at || "").localeCompare(b.started_at || ""));
    return arr;
  }, [traces.tool_calls]);

  const totalMs = useMemo(() => toolsSorted.reduce((acc, t) => acc + (t.duration_ms || 0), 0), [toolsSorted]);
  const toolsCount = toolsSorted.length;
  const todosCount = traces.planning?.todos?.length || 0;
  const subagentsCount = traces.planning?.subagents?.length || 0;

  return (
    <div className="mt-2 border border-border rounded-md bg-background/40">
      {/* Header */}
      <button
        className="w-full text-left px-3 py-2 flex items-center justify-between hover:bg-card-hover transition-colors"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
      >
        <div className="flex items-center gap-2 text-xs">
          {traces.engine && (
            <span className="inline-flex items-center px-2 py-0.5 rounded bg-muted border border-border">
              {traces.engine}
            </span>
          )}
          <span className="inline-flex items-center px-2 py-0.5 rounded bg-muted border border-border">
            {toolsCount} tool{toolsCount === 1 ? "" : "s"}
          </span>
          {!!totalMs && (
            <span className="inline-flex items-center px-2 py-0.5 rounded bg-muted border border-border">
              {formatDuration(totalMs)} total
            </span>
          )}
          {todosCount > 0 && (
            <span className="inline-flex items-center px-2 py-0.5 rounded bg-muted border border-border">
              {todosCount} planner{todosCount === 1 ? "" : "s"}
            </span>
          )}
          {subagentsCount > 0 && (
            <span className="inline-flex items-center px-2 py-0.5 rounded bg-muted border border-border">
              {subagentsCount} subagent{subagentsCount === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <span className="text-xs text-foreground/80 flex items-center gap-1">
          Traces {open ? '▲' : '▼'}
        </span>
      </button>

      {/* Collapsible content */}
      {open && (
        <div className="px-3 pb-3 pt-1 space-y-3">
          {/* Traces (assistant thinking or normalized final) */}
          <div>
            <div className="text-xs font-semibold mb-1">Traces</div>
            {traces.messages?.assistant_final ? (
              <div className="text-xs whitespace-pre-wrap break-words opacity-90">
                {(() => {
                  const s = traces.messages?.assistant_final || "";
                  try {
                    const t = extractFromChunkArrayText(s);
                    return t || truncate(s, 500);
                  } catch {
                    return truncate(s, 500);
                  }
                })()}
              </div>
            ) : (
              <div className="text-xs opacity-70">No trace text</div>
            )}
          </div>

          {/* Tools timeline */}
          <div>
            <div className="text-xs font-semibold mb-1">Tools</div>
            {toolsSorted.length === 0 ? (
              <div className="text-xs opacity-70">No tools used</div>
            ) : (
              <ul className="space-y-2">
                {toolsSorted.map((t, i) => (
                  <li key={`${t.name}-${i}`} className="border border-border rounded p-2 bg-background/50">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold">{t.name}{toolsSorted.filter(x => x.name === t.name).length > 1 ? ` #${i + 1}` : ""}</span>
                      {typeof t.ok === "boolean" && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${t.ok ? "bg-green-900/40 text-green-300" : "bg-red-900/40 text-red-300"}`}>
                          {t.ok ? "ok" : "error"}
                        </span>
                      )}
                      {typeof t.duration_ms === "number" && (
                        <span className="text-[10px] opacity-70">{formatDuration(t.duration_ms)}</span>
                      )}
                      {t.chars_read != null && (
                        <span className="text-[10px] opacity-70">chars {t.chars_read}</span>
                      )}
                      {t.started_at && (
                        <span className="text-[10px] opacity-50">{formatTime(t.started_at)}</span>
                      )}
                    </div>
                    <div className="mt-1 grid gap-1 text-xs">
                      {t.args_preview && (
                        <div className="font-mono opacity-80 break-words">
                          <span className="opacity-60">args:</span> {truncate(t.args_preview)}
                        </div>
                      )}
                      {t.result_preview && (
                        <div className="font-mono opacity-80 break-words">
                          <span className="opacity-60">result:</span> {truncate(t.result_preview)}
                        </div>
                      )}
                      {t.error && (
                        <div className="font-mono text-red-300 break-words">
                          <span className="opacity-60">error:</span> {truncate(t.error)}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Planners */}
          <div>
            <div className="text-xs font-semibold mb-1">Planners</div>
            {!(traces.planning?.todos && traces.planning?.todos.length > 0) ? (
              <div className="text-xs opacity-70">No planners</div>
            ) : (
              <ul className="text-xs space-y-1">
                {traces.planning?.todos?.map((item: any, idx: number) => (
                  <li key={idx} className="border border-border rounded p-2 bg-background/50 font-mono break-words opacity-90">
                    {truncate(safeString(item), 300)}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Sub agents */}
          <div>
            <div className="text-xs font-semibold mb-1">Sub agents</div>
            {!(traces.planning?.subagents && traces.planning?.subagents.length > 0) ? (
              <div className="text-xs opacity-70">No sub agents</div>
            ) : (
              <ul className="text-xs space-y-1">
                {traces.planning?.subagents?.map((item: any, idx: number) => (
                  <li key={idx} className="border border-border rounded p-2 bg-background/50 font-mono break-words opacity-90">
                    {truncate(safeString(item), 300)}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Filesystem ops (optional) */}
          <div>
            <div className="text-xs font-semibold mb-1">Filesystem</div>
            {!(traces.planning?.filesystem_ops && traces.planning?.filesystem_ops.length > 0) ? (
              <div className="text-xs opacity-70">No filesystem ops</div>
            ) : (
              <ul className="text-xs space-y-1">
                {traces.planning?.filesystem_ops?.map((item: any, idx: number) => (
                  <li key={idx} className="border border-border rounded p-2 bg-background/50 font-mono break-words opacity-90">
                    {truncate(safeString(item), 300)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

function safeString(val: any): string {
  try {
    if (typeof val === "string") return val;
    return JSON.stringify(val);
  } catch {
    return String(val);
  }
}

function extractFromChunkArrayText(value: string): string {
  const s = (value || "").trim();
  if (!s.startsWith("[")) return s;
  try {
    const re = /(?:'text'|\"text\")\s*:\s*(?:'([^']*)'|\"([^\"]*)\")/g;
    const parts: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = re.exec(s)) !== null) {
      const val = m[1] || m[2] || "";
      if (val) parts.push(val);
    }
    return parts.join("\n\n") || s;
  } catch {
    return s;
  }
}


