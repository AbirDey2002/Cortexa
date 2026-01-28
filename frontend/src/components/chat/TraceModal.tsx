import React, { useState, useCallback } from "react";
import { X, Brain, Loader2, AlertCircle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { API_BASE_URL } from "@/lib/utils";

type TraceRow = {
    step_number: number;
    step_type: "thought" | "tool_start" | "tool_end" | "error";
    content: Record<string, any> | null;
    turn_id: string | null;
    created_at: string | null;
};

type TraceModalProps = {
    isOpen: boolean;
    onClose: () => void;
    usecaseId: string;
    turnId: string;
};

function formatStepType(type: string): { label: string; color: string } {
    switch (type) {
        case "thought":
            return { label: "Thinking", color: "text-blue-400" };
        case "tool_start":
            return { label: "Tool Started", color: "text-yellow-400" };
        case "tool_end":
            return { label: "Tool Completed", color: "text-green-400" };
        case "error":
            return { label: "Error", color: "text-red-400" };
        default:
            return { label: type, color: "text-gray-400" };
    }
}

function formatTime(ts: string | null): string {
    if (!ts) return "";
    try {
        const d = new Date(ts);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
        return "";
    }
}

function formatContent(content: Record<string, any> | null): string {
    if (!content) return "";
    try {
        if (content.text) return String(content.text);
        if (content.tool) return `Tool: ${content.tool}\nInput: ${JSON.stringify(content.input, null, 2)}`;
        if (content.output) {
            const out = typeof content.output === "string" ? content.output : JSON.stringify(content.output, null, 2);
            return out;
        }
        if (content.error) return `Error: ${content.error}`;
        return JSON.stringify(content, null, 2);
    } catch {
        return "[content]";
    }
}

export const TraceModal: React.FC<TraceModalProps> = ({
    isOpen,
    onClose,
    usecaseId,
    turnId,
}) => {
    const { getAccessTokenSilently, isAuthenticated } = useAuth();
    const [traces, setTraces] = useState<TraceRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch traces when modal opens
    const fetchTraces = useCallback(async () => {
        if (!usecaseId || !turnId) return;

        setLoading(true);
        setError(null);

        try {
            let authHeader = "";
            if (isAuthenticated) {
                const token = await getAccessTokenSilently();
                if (token) authHeader = `Bearer ${token}`;
            }

            const response = await fetch(
                `${API_BASE_URL}/usecases/${usecaseId}/agent-thinking/history?turn_id=${turnId}&limit=200`,
                { headers: authHeader ? { Authorization: authHeader } : {} }
            );

            if (!response.ok) {
                throw new Error(`Failed to fetch traces: ${response.status}`);
            }

            const data = await response.json();
            // Sort by step_number ascending (chronological order)
            const sortedTraces = (data.traces || []).sort(
                (a: TraceRow, b: TraceRow) => a.step_number - b.step_number
            );
            setTraces(sortedTraces);
        } catch (e: any) {
            setError(e.message || "Failed to load traces");
        } finally {
            setLoading(false);
        }
    }, [usecaseId, turnId, isAuthenticated, getAccessTokenSilently]);

    // Fetch when modal opens
    React.useEffect(() => {
        if (isOpen) {
            fetchTraces();
        }
    }, [isOpen, fetchTraces]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-3xl max-h-[80vh] flex flex-col m-4">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                    <div className="flex items-center gap-3">
                        <Brain className="w-5 h-5 text-primary" />
                        <h2 className="text-lg font-semibold">Agent Thinking Trace</h2>
                        <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded">
                            {traces.length} steps
                        </span>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-muted rounded-lg transition-colors"
                        aria-label="Close"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-4">
                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                            <span className="ml-2 text-muted-foreground">Loading traces...</span>
                        </div>
                    ) : error ? (
                        <div className="flex items-center justify-center py-12 text-red-400">
                            <AlertCircle className="w-5 h-5 mr-2" />
                            {error}
                        </div>
                    ) : traces.length === 0 ? (
                        <div className="flex items-center justify-center py-12 text-muted-foreground">
                            No traces found for this message
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {traces.map((trace, idx) => {
                                const { label, color } = formatStepType(trace.step_type);
                                return (
                                    <div
                                        key={`${trace.step_number}-${idx}`}
                                        className="border border-border rounded-lg p-4 bg-card hover:bg-card-hover transition-colors"
                                    >
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="flex items-center gap-2">
                                                <span className={`font-medium ${color}`}>{label}</span>
                                                <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                                                    Step {trace.step_number}
                                                </span>
                                            </div>
                                            {trace.created_at && (
                                                <span className="text-xs text-muted-foreground">
                                                    {formatTime(trace.created_at)}
                                                </span>
                                            )}
                                        </div>
                                        <pre className="text-sm text-foreground/80 whitespace-pre-wrap break-words font-mono bg-background/50 rounded p-2 max-h-48 overflow-y-auto">
                                            {formatContent(trace.content)}
                                        </pre>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default TraceModal;
