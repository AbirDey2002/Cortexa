import React, { useEffect, useState, useRef } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { API_BASE_URL } from "@/lib/utils";

type TraceStep = {
  step_number: number;
  step_type: "thought" | "tool_start" | "tool_end" | "error";
  content: Record<string, any> | null;
  created_at: string | null;
};

type ThinkingStreamProps = {
  usecaseId: string;
  isProcessing: boolean;
  turnId?: string | null;  // Filter traces by turn ID
  onComplete?: () => void;
};

function formatStepType(type: string): { label: string; color: string } {
  switch (type) {
    case "thought":
      return { label: "Thinking", color: "text-blue-400" };
    case "tool_start":
      return { label: "Tool", color: "text-yellow-400" };
    case "tool_end":
      return { label: "Result", color: "text-green-400" };
    case "error":
      return { label: "Error", color: "text-red-400" };
    default:
      return { label: type, color: "text-gray-400" };
  }
}

function truncateContent(content: Record<string, any> | null, maxLen = 150): string {
  if (!content) return "";
  try {
    if (content.text) {
      const text = String(content.text);
      return text.length > maxLen ? text.slice(0, maxLen) + "…" : text;
    }
    if (content.tool) {
      return `${content.tool}: ${truncateContent({ text: content.input }, maxLen - content.tool.length - 2)}`;
    }
    if (content.output) {
      const out = typeof content.output === "string" ? content.output : JSON.stringify(content.output);
      return out.length > maxLen ? out.slice(0, maxLen) + "…" : out;
    }
    const str = JSON.stringify(content);
    return str.length > maxLen ? str.slice(0, maxLen) + "…" : str;
  } catch {
    return "[content]";
  }
}

export const ThinkingStream: React.FC<ThinkingStreamProps> = ({
  usecaseId,
  isProcessing,
  turnId,
  onComplete,
}) => {
  const { getAccessTokenSilently, isAuthenticated } = useAuth();
  const [traces, setTraces] = useState<TraceStep[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [polling, setPolling] = useState(false);
  const pollingRef = useRef(false);
  const mountedRef = useRef(true);
  const startTimeRef = useRef(new Date());

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Start polling when processing begins
  useEffect(() => {
    if (!isProcessing || !usecaseId) {
      pollingRef.current = false;
      setPolling(false);
      return;
    }

    // Clear previous traces when new processing starts
    setTraces([]);

    // Reset state
    setTraces([]);
    pollingRef.current = true;
    setPolling(true);

    let lastStepNumber = 0;
    const pollInterval = 10000; // Poll every 10s as requested to avoid RPM limits

    const poll = async () => {
      // Get auth token
      let authHeader = "";
      if (isAuthenticated) {
        try {
          const token = await getAccessTokenSilently();
          if (token) {
            authHeader = `Bearer ${token}`;
          }
        } catch (e) {
          // Auth error, continue without token
        }
      }

      while (pollingRef.current && mountedRef.current) {
        try {
          // Build URL with optional turn_id filter
          let url = `${API_BASE_URL}/usecases/${usecaseId}/agent-thinking/history?limit=200`;
          if (turnId) {
            url += `&turn_id=${turnId}`;
          }

          const response = await fetch(url, {
            headers: authHeader ? { Authorization: authHeader } : {},
          });

          if (!response.ok) {
            await new Promise(r => setTimeout(r, 1000));
            continue;
          }

          const data = await response.json();

          const allTraces: TraceStep[] = data.traces || [];

          if (allTraces.length > 0 && mountedRef.current) {
            // Filter traces that are newer than the start time
            const newTraces = allTraces.filter(t => {
              if (!t.created_at) return true; // Include if no timestamp
              return new Date(t.created_at) > startTimeRef.current;
            });

            // Only update if we have new traces or if we need to clear previous state
            const maxStep = newTraces.length > 0 ? Math.max(...newTraces.map(t => t.step_number)) : 0;

            // Update if we have content (or if we need to ensure it's empty initially)
            // We use a JSON string comparison to avoid unnecessary re-renders if content is identical
            if (JSON.stringify(newTraces) !== JSON.stringify(traces)) {
              lastStepNumber = maxStep;
              setTraces(newTraces);
            }
          }

          // Note: Status check removed - polling stops when isLoading becomes false

        } catch (e) {
          // Poll error, continue polling
        }

        await new Promise(r => setTimeout(r, pollInterval));
      }
    };

    poll();

    return () => {
      pollingRef.current = false;
    };
  }, [isProcessing, usecaseId, turnId, isAuthenticated, getAccessTokenSilently, onComplete]);

  if (!isProcessing && traces.length === 0) {
    return null;
  }

  return (
    <div className="my-2 border border-border rounded-lg bg-background/60 overflow-hidden">
      {/* Header */}
      <button
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-card-hover transition-colors"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-3">
          {isProcessing && polling && (
            <span className="flex items-center gap-2">
              <span className="text-sm font-medium">Thinking... </span>
            </span>
          )}
          {!isProcessing && (
            <span className="text-sm font-medium text-muted-foreground">
              Completed ({traces.length} steps)
            </span>
          )}
          {isProcessing && !polling && (
            <span className="text-sm text-muted-foreground">Starting...</span>
          )}
        </div>
        <span className="text-xs text-foreground/70 flex items-center gap-1">
          {expanded ? "▲ Collapse" : "▼ Expand Thinking"}
        </span>
      </button>

      {/* Expandable content */}
      {expanded && (
        <div className="px-4 pb-4 pt-1 max-h-80 overflow-y-auto space-y-2">
          {traces.length === 0 ? (
            <div className="text-xs text-muted-foreground">
              Waiting for agent to start...
            </div>
          ) : (
            traces.map((trace, idx) => {
              const { label, color } = formatStepType(trace.step_type);
              return (
                <div
                  key={`${trace.step_number}-${idx}`}
                  className="border border-border/50 rounded p-2 bg-background/40 text-xs"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`font-semibold ${color}`}>{label}</span>
                    <span className="text-muted-foreground">
                      Step {trace.step_number}
                    </span>
                  </div>
                  <div className="text-foreground/80 break-words font-mono">
                    {truncateContent(trace.content, 300)}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};

export default ThinkingStream;
