import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChatTrace } from "./ChatTrace";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { FileText, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import "highlight.js/styles/github-dark.css";

interface Traces {
  engine?: string | null;
  tool_calls?: Array<{
    name: string;
    started_at?: string;
    finished_at?: string;
    duration_ms?: number;
    ok?: boolean;
    args_preview?: string;
    result_preview?: string;
    chars_read?: number | null;
    error?: string | null;
  }>;
  planning?: {
    todos?: any[];
    subagents?: any[];
    filesystem_ops?: any[];
  };
}

interface Message {
  id: string;
  type: "user" | "assistant";
  content: string;
  file?: {
    name: string;
    type: string;
  };
  timestamp: Date;
  hasPreview?: boolean;
  traces?: Traces;
}

interface ChatContentProps {
  usecaseId: string | null;
  messages: Message[];
  isLoading?: boolean;
  onOpenPreview?: (messageId: string) => void;
}

export const ChatContent: React.FC<ChatContentProps> = ({
  usecaseId,
  messages,
  isLoading = false,
  onOpenPreview,
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [expandedTraces, setExpandedTraces] = useState<Record<string, boolean>>({});

  const toggleTraces = (id: string) =>
    setExpandedTraces(prev => ({ ...prev, [id]: !prev[id] }));

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Auto-scroll when messages change
  useEffect(() => {
    if (messages.length > 0) {
      // Use a small delay to ensure DOM is updated
      setTimeout(scrollToBottom, 100);
    }
  }, [messages]);

  // Auto-scroll when loading state changes
  useEffect(() => {
    if (isLoading) {
      setTimeout(scrollToBottom, 100);
    }
  }, [isLoading]);

  // Auto-scroll when usecase changes and has messages
  useEffect(() => {
    if (usecaseId && messages.length > 0) {
      setTimeout(scrollToBottom, 200);
    }
  }, [usecaseId]);
  if (!usecaseId) {
    return (
      // Welcome State
      <div className="flex-1 flex items-center justify-center py-8">
        <div className="text-center max-w-xs sm:max-w-md md:max-w-2xl fade-in">
          <div className="mb-6 md:mb-8">
            <div className="inline-flex items-center justify-center w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 rounded-full bg-gradient-to-br from-primary to-primary-glow mb-4 sm:mb-6 glow-primary">
              <FileText className="w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8 text-primary-foreground" />
            </div>
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold text-foreground mb-2 sm:mb-4">
              Hello
            </h1>
            <p className="text-base sm:text-lg text-muted-foreground">
              Start a chat to begin.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4 mt-6 sm:mt-8">
            <Card className="p-4 sm:p-5 md:p-6 hover:bg-card-hover transition-colors cursor-pointer border-border">
              <FileText className="w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8 text-primary mb-2 sm:mb-3" />
              <h3 className="font-semibold text-card-foreground mb-1 sm:mb-2">Upload FSD</h3>
              <p className="text-xs sm:text-sm text-muted-foreground">
                Upload your Functional Specification Document for comprehensive test case generation
              </p>
            </Card>

            <Card className="p-4 sm:p-5 md:p-6 hover:bg-card-hover transition-colors cursor-pointer border-border">
              <FileText className="w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8 text-secondary mb-2 sm:mb-3" />
              <h3 className="font-semibold text-card-foreground mb-1 sm:mb-2">Analyze CR</h3>
              <p className="text-xs sm:text-sm text-muted-foreground">
                Upload Change Requests to generate targeted test scenarios
              </p>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  return (
    // Chat Messages
    <div className="space-y-4 sm:space-y-6 overflow-hidden">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex ${message.type === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden ${message.type === "user"
                ? "bg-chat-user border border-border ml-auto"
                : "bg-chat-assistant border border-primary/30 mr-auto shadow-sm"
              }`}
          >
            {message.file && (
              <div className="flex items-center gap-2 mb-3 p-2 rounded-lg bg-accent/50 border border-border">
                <FileText className="w-4 h-4 text-accent-foreground" />
                <span className="text-sm font-medium text-accent-foreground">
                  {message.file.name}
                </span>
              </div>
            )}
            <div className="text-sm leading-relaxed break-words overflow-x-auto overflow-y-visible markdown-content">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
                components={{
                  // Customize headings
                  h1: ({ children }) => (
                    <h1 className="text-lg font-bold mb-2 text-foreground">{children}</h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="text-base font-bold mb-2 text-foreground">{children}</h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="text-sm font-bold mb-1 text-foreground">{children}</h3>
                  ),
                  // Customize paragraphs
                  p: ({ children }) => (
                    <p className="mb-2 last:mb-0">{children}</p>
                  ),
                  // Customize code blocks
                  pre: ({ children }) => (
                    <pre className="bg-muted p-3 rounded-lg overflow-x-auto my-2 text-xs border border-border">
                      {children}
                    </pre>
                  ),
                  // Customize inline code
                  code: ({ children, className }) => {
                    const isBlock = className?.includes('language-');
                    if (isBlock) {
                      return <code className={className}>{children}</code>;
                    }
                    return (
                      <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono border border-border">
                        {children}
                      </code>
                    );
                  },
                  // Customize lists
                  ul: ({ children }) => (
                    <ul className="list-disc ml-4 mb-2 space-y-1">{children}</ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="list-decimal ml-4 mb-2 space-y-1">{children}</ol>
                  ),
                  li: ({ children }) => (
                    <li className="text-sm">{children}</li>
                  ),
                  // Customize links
                  a: ({ href, children }) => (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:text-primary/80 underline transition-colors"
                    >
                      {children}
                    </a>
                  ),
                  // Customize blockquotes
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-4 border-primary pl-4 py-2 my-2 bg-muted/50 rounded-r">
                      {children}
                    </blockquote>
                  ),
                  // Customize tables
                  table: ({ children }) => (
                    <div className="overflow-x-auto my-2">
                      <table className="min-w-full border border-border rounded">
                        {children}
                      </table>
                    </div>
                  ),
                  thead: ({ children }) => (
                    <thead className="bg-muted">{children}</thead>
                  ),
                  th: ({ children }) => (
                    <th className="border border-border px-3 py-2 text-left text-xs font-semibold">
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="border border-border px-3 py-2 text-xs">
                      {children}
                    </td>
                  ),
                  // Customize horizontal rules
                  hr: () => (
                    <hr className="border-border my-4" />
                  ),
                  // Customize strong/bold
                  strong: ({ children }) => (
                    <strong className="font-semibold text-foreground">{children}</strong>
                  ),
                  // Customize emphasis/italic
                  em: ({ children }) => (
                    <em className="italic text-muted-foreground">{children}</em>
                  ),
                }}
              >
                {normalizeMarkdownText(message.content)}
              </ReactMarkdown>
            </div>
            {/* Traces disclosure */}
            {message.type === "assistant" && message.traces && (
              <ChatTrace traces={message.traces} />
            )}
            {message.hasPreview && onOpenPreview && (
              <Button
                onClick={() => onOpenPreview(message.id)}
                variant="outline"
                size="sm"
                className="mt-3 h-8 text-xs gap-2 hover:bg-gray-700 hover:text-gray-100"
              >
                <ExternalLink className="w-3 h-3" />
                Open in Preview
              </Button>
            )}
            <div className="text-xs text-muted-foreground mt-2">
              {message.timestamp.toLocaleTimeString()}
            </div>
          </div>
        </div>
      ))}

      {isLoading && (
        <div className="flex justify-start">
          <div className="bg-chat-assistant border border-primary/30 rounded-xl p-4 mr-auto shadow-sm">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" />
              <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
              <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
            </div>
          </div>
        </div>
      )}

      {/* Invisible element to scroll to */}
      <div ref={messagesEndRef} className="h-4" />
    </div>
  );
};
