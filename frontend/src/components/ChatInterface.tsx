import { useEffect, useRef, useState } from "react";
import { FileText, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { FileChip } from "@/components/FileChip";
import { PreviewPanel } from "@/components/PreviewPanel";
import { apiGet, apiPost } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { ChatInput, FloatingInputContainer, ChatTrace } from "@/components/chat";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { RequirementsGenerationConfirmModal } from "@/components/chat/RequirementsGenerationConfirmModal";

function extractMainTextFromStored(raw: any): string {
  try {
    if (typeof raw !== "string") return String(raw ?? "");
    const s = raw.trim();
    if (s.startsWith("[") && (s.includes("'text'") || s.includes('"text"'))) {
      const re = /(?:'text'|\"text\")\s*:\s*(?:'([^']*)'|\"([^\"]*)\")/g;
      const parts: string[] = [];
      let m: RegExpExecArray | null;
      while ((m = re.exec(s)) !== null) {
        const val = m[1] || m[2] || "";
        if (val) parts.push(val);
      }
      return parts.join("\n\n") || s;
    }
    return s;
  } catch {
    return String(raw ?? "");
  }
}

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
  toolCall?: string;
  traces?: Traces;
}

// Files selected to be sent with the next message
interface SelectedFile {
  name: string;
  type: string;
  file: File;
}

// Removed UploadedFilesTab and processing modal

interface Props {
  userId: string;
  usecaseId: string | null;
}

export function ChatInterface({ userId, usecaseId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [expandedTraces, setExpandedTraces] = useState<Record<string, boolean>>({});
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [reqGenConfirmOpen, setReqGenConfirmOpen] = useState(false);
  const [isReqGenBlocking, setIsReqGenBlocking] = useState(false);
  const reqGenPollTimerRef = useRef<number | null>(null);
  const { toast } = useToast();
  const [isOcrProcessing, setIsOcrProcessing] = useState(false);
  const [reqGenStatus, setReqGenStatus] = useState<"Not Started" | "In Progress" | "Completed" | "Failed" | "">("");
  const [lastReqGenCheckedUsecaseId, setLastReqGenCheckedUsecaseId] = useState<string | null>(null);
  const [reqGenConfirmed, setReqGenConfirmed] = useState<boolean>(false);
  const ocrBannerTimerRef = useRef<number | null>(null);
  const [pendingFiles, setPendingFiles] = useState<SelectedFile[]>([]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Removed files tray and processing modal state
  const [status, setStatus] = useState<string>("Completed");
  const [waitingForResponse, setWaitingForResponse] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Removed OCR UI state

  // Scroll to bottom when messages change
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  };

  // Load chat for selected usecase and reset per-chat state
  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!usecaseId) {
        setMessages([]);
        setReqGenStatus("");
        setLastReqGenCheckedUsecaseId(null);
        return;
      }
      try {
        const statuses = await apiGet<any>(`/frontend/usecases/${usecaseId}/statuses`);
        if (cancelled) return;
        setStatus(statuses.status || "Completed");
        // Initialize requirement generation status banner on usecase change
        try {
          const rg = await apiGet<any>(`/requirements/${usecaseId}/status`);
          const state = String(rg?.requirement_generation || "").trim().toLowerCase();
          setReqGenStatus((state === "completed") ? "Completed" : (state === "in progress") ? "In Progress" : (state === "failed") ? "Failed" : "Not Started");
          setReqGenConfirmed(!!rg?.requirement_generation_confirmed);
          setLastReqGenCheckedUsecaseId(usecaseId);
          if (rg?.requirement_generation === "In Progress") {
            setIsReqGenBlocking(true);
          } else if (rg?.requirement_generation === "Completed" || rg?.requirement_generation === "Failed") {
            setIsReqGenBlocking(false);
          }
        } catch {}
        // Fetch unified chat history (Gemini-backed backend writes to same store)
        const history = await apiGet<any[]>(`/frontend/usecases/${usecaseId}/chat`);
        if (cancelled) return;
        
        // Sort messages by timestamp in ascending order (oldest first)
        const sortedHistory = [...history].sort((a, b) => {
          const tsA = new Date(a.timestamp || 0).getTime();
          const tsB = new Date(b.timestamp || 0).getTime();
          return tsA - tsB;
        });
        
        const mappedMessages = sortedHistory.map((entry, idx) => {
          const ts = new Date(entry.timestamp || Date.now());
          if (entry.user !== undefined) {
            const message: Message = { 
              id: `u-${idx}`, 
              type: "user", 
              content: entry.user, 
              timestamp: ts 
            };
            
            // Add file information if available
            if (entry.files && entry.files.length > 0) {
              message.file = {
                name: entry.files[0].name,
                type: entry.files[0].type
              };
            }
            
            return message;
          }
          
          const content = entry.system;
          // agent output contains JSON; show only user_answer if present
          let shown = extractMainTextFromStored(content);
          try {
            const m = content.match(/```json\s*([\s\S]*?)\s*```/i);
            const jsonText = m ? m[1] : content;
            const obj = JSON.parse(jsonText);
            if (obj && obj.system_event === "requirement_generation_confirmation_required") {
              // Optional guard: do not re-open if consent already recorded
              if (lastReqGenCheckedUsecaseId === usecaseId && reqGenConfirmed) {
                // consent already recorded; ignore
              } else {
              console.debug("system_event detected: requirement_generation_confirmation_required");
              setReqGenConfirmOpen(true);
              setIsReqGenBlocking(true);
              setWaitingForResponse(false);
              setIsLoading(false);
              shown = "I've identified documents ready for requirement generation. A confirmation dialog will appear. Click 'Yes' to start the background process. You'll be notified when complete.";
              }
            } else if (obj && obj.system_event === "requirement_generation_in_progress") {
              console.debug("system_event detected: requirement_generation_in_progress");
              setIsReqGenBlocking(true);
              setWaitingForResponse(false);
              setIsLoading(false);
              setReqGenStatus("In Progress");
            } else if (obj && obj.user_answer) {
              shown = obj.user_answer;
            }
          } catch {}
          const msg: Message = { id: `a-${idx}`, type: "assistant", content: shown, timestamp: ts } as Message;
          if (entry.traces) {
            msg.traces = entry.traces as Traces;
          }
          return msg;
        });
        
        setMessages(mappedMessages);
        
        // Schedule scroll to bottom after messages are rendered
        setTimeout(scrollToBottom, 100);
      } catch (e) {
        console.error("Error loading chat history:", e);
        setMessages([]);
      }
    }
    load();
    // No files tray/modal state to reset
    return () => {
      cancelled = true;
    };
  }, [usecaseId]);

  // Unified polling for status and message retrieval - only when waiting for a response
  useEffect(() => {
    // Only poll if we're in a usecase AND waiting for a response
    if (!usecaseId || !waitingForResponse) return;
    
    let timer: any;
    
    async function poll() {
      try {
        // Poll for status using the specific usecase endpoint
        const response = await apiGet<any>(`/frontend/usecases/${usecaseId}/statuses`);
        const currentStatus = response.status || "Completed";
        setStatus(currentStatus);
        
        if (currentStatus === "In Progress") {
          // Show loading indicator while in progress
          setIsLoading(true);
          
          // Continue polling while in progress
          timer = setTimeout(poll, 2000);
        } else if (currentStatus === "Completed") {
          // When status changes to Completed
          setIsLoading(false);
          setWaitingForResponse(false); // Stop waiting for response
          
          // If the response includes the latest message, add it to messages
          if (response.latest_message && !messages.some(m => 
            m.type === "assistant" && m.content === response.latest_message)) {
            
            // Add the system message
            const systemMessage: Message = {
              id: `a-${Date.now()}`,
              type: "assistant",
              content: response.latest_message,
              timestamp: new Date(),
            };
            
            setMessages(prev => [...prev, systemMessage]);
            // Scroll to bottom after system message is added
            setTimeout(scrollToBottom, 100);
          } else {
            // Get the full chat history
            const history = await apiGet<any[]>(`/frontend/usecases/${usecaseId}/chat`);
            
            // Sort messages by timestamp in ascending order (oldest first)
            const sortedHistory = [...history].sort((a, b) => {
              const tsA = new Date(a.timestamp || 0).getTime();
              const tsB = new Date(b.timestamp || 0).getTime();
              return tsA - tsB;
            });
            
            const mappedMessages = sortedHistory.map((entry, idx) => {
              const ts = new Date(entry.timestamp || Date.now());
              if (entry.user !== undefined) {
                const message: Message = { 
                  id: `u-${idx}`, 
                  type: "user", 
                  content: entry.user, 
                  timestamp: ts 
                };
                
                // Add file information if available
                if (entry.files && entry.files.length > 0) {
                  message.file = {
                    name: entry.files[0].name,
                    type: entry.files[0].type
                  };
                }
                
                return message;
              }
              const content = entry.system;
              let shown = extractMainTextFromStored(content);
              try {
                const m = content.match(/```json\s*([\s\S]*?)\s*```/i);
                const jsonText = m ? m[1] : content;
                const obj = JSON.parse(jsonText);
                if (obj && obj.system_event === "requirement_generation_confirmation_required") {
                  console.debug("system_event detected (poll loop): requirement_generation_confirmation_required");
                  setReqGenConfirmOpen(true);
                  setIsReqGenBlocking(true);
                  setWaitingForResponse(false);
                  setIsLoading(false);
                  setReqGenStatus("Not Started");
                  shown = "I've identified documents ready for requirement generation. A confirmation dialog will appear. Click 'Yes' to start the background process. You'll be notified when complete.";
                } else if (obj && obj.system_event === "requirement_generation_in_progress") {
                  console.debug("system_event detected (poll loop): requirement_generation_in_progress");
                  setIsReqGenBlocking(true);
                  setWaitingForResponse(false);
                  setIsLoading(false);
                  setReqGenStatus("In Progress");
                } else if (obj && obj.user_answer) {
                  shown = obj.user_answer;
                }
              } catch {}
              const msg: Message = { id: `a-${idx}`, type: "assistant", content: shown, timestamp: ts } as Message;
              if (entry.traces) {
                msg.traces = entry.traces as Traces;
              }
              return msg;
            });
            
            setMessages(mappedMessages);
            
            // Scroll to bottom after messages are rendered
            setTimeout(scrollToBottom, 100);
          }
        }
      } catch (e) {
        console.error("Error polling status:", e);
        setIsLoading(false);
        setWaitingForResponse(false); // Stop waiting on error
      }
    }
    
    // Start polling immediately when waiting for response
    console.log(`Starting polling for usecase ${usecaseId} - waiting for response`);
    poll();
    
    return () => {
      clearTimeout(timer);
    };
  }, [usecaseId, waitingForResponse, messages]);

  const createNewUsecase = async () => {
    try {
      // Get the current count of chats to name this one appropriately
      const usecases = await apiGet<any[]>(`/frontend/usecases/list`);
      const chatCount = usecases.length + 1;
      const chatName = `Chat ${chatCount}`;
      
      // Create new usecase
      const payload = { user_id: userId, usecase_name: chatName, email: "abir.dey@intellectdesign.com" };
      const record = await apiPost<any>("/usecases", payload);
      
      // Notify the parent component about the new usecase
      if (window.dispatchEvent) {
        window.dispatchEvent(new CustomEvent('usecase-created', { detail: { usecaseId: record.usecase_id } }));
      }
      
      return record.usecase_id;
    } catch (e) {
      console.error("Error creating new chat:", e);
      return null;
    }
  };

  const handleSend = async () => {
    if (!inputValue.trim()) return;
    
    // If no usecase is selected, create a new one first
    let targetUsecaseId = usecaseId;
    if (!targetUsecaseId) {
      targetUsecaseId = await createNewUsecase();
      if (!targetUsecaseId) return; // Failed to create usecase
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      type: "user",
      content: inputValue,
      timestamp: new Date(),
      file: pendingFiles.length > 0 ? {
        name: pendingFiles[0].name,
        type: pendingFiles[0].type
      } : undefined,
    };

    setMessages(prev => [...prev, userMessage]);
    // Scroll to bottom after user message is added
    setTimeout(scrollToBottom, 100);
    
    const messageContent = inputValue;
    const filesToUpload = [...pendingFiles];
    
    setInputValue("");
    setPendingFiles([]);
    setIsLoading(true);

    try {
      // Upload files if any
      if (filesToUpload.length > 0) {
        const formData = new FormData();
        filesToUpload.forEach(file => {
          formData.append('files', file.file);
        });
        formData.append('email', 'abir.dey@intellectdesign.com');
        formData.append('usecase_id', targetUsecaseId);

        await apiPost('/files/upload_file', formData);
        // Short-lived poll to confirm OCR read
        let attempts = 0;
        const checkOcr = async () => {
          try {
            const res = await apiGet<any>(`/files/ocr/${targetUsecaseId}/document-markdown`);
            const hasData = !!res?.combined_markdown;
            if (hasData || attempts >= 4) {
              setIsOcrProcessing(false);
              // Optionally show transient notice
              if (hasData) {
                console.debug("OCR completed: documents are readable");
              }
              return;
            }
          } catch {}
          attempts += 1;
          setTimeout(checkOcr, 1500);
        };
        setTimeout(checkOcr, 1500);
      }

      // Send chat message with file information if available
      const chatPayload: any = { role: "user", content: messageContent };
      if (filesToUpload.length > 0) {
        chatPayload.files = filesToUpload.map(file => ({
          name: file.name,
          type: file.type,
          size: file.file.size
        }));
      }
      
      // Route chat to Gemini conversation endpoint (not PF)
      await apiPost(`/usecases/${targetUsecaseId}/gemini-chat`, chatPayload);
      setStatus("In Progress");
      setWaitingForResponse(true); // Start waiting for response
      
      // Notify the parent component that a message was sent to refresh the sidebar
      if (window.dispatchEvent) {
        window.dispatchEvent(new CustomEvent('chat-updated', { detail: { usecaseId } }));
      }
    } catch (e) {
      console.error("Error sending message:", e);
      setIsLoading(false);
    }
  };

  const handleFileUpload = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files) {
      const selected: SelectedFile[] = Array.from(files).map(file => ({
        name: file.name,
        type: file.type,
        file: file,
      }));
      setPendingFiles(prev => [...prev, ...selected]);
      // Start OCR status banner
      setIsOcrProcessing(true);
    }
    // Reset the input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleRemoveFile = (index: number) => {
    setPendingFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleOpenPreview = (messageId: string) => {
    setPreviewContent(`**Test Case Suite: Login Module Analysis**

**Test Case 1: Valid Login Functionality**
- **Objective**: Verify successful login with valid credentials
- **Prerequisites**: User account exists in system
- **Steps**:
  1. Navigate to login page
  2. Enter valid username
  3. Enter valid password
  4. Click login button
- **Expected Result**: User is redirected to dashboard
- **Priority**: High

**Test Case 2: Invalid Credentials**
- **Objective**: Verify error handling for invalid credentials
- **Prerequisites**: Login page is accessible
- **Steps**:
  1. Navigate to login page
  2. Enter invalid username or password
  3. Click login button
- **Expected Result**: Error message displayed
- **Priority**: High

**Test Case 3: Empty Field Validation**
- **Objective**: Verify required field validation
- **Prerequisites**: Login page is accessible
- **Steps**:
  1. Navigate to login page
  2. Leave username field empty
  3. Click login button
- **Expected Result**: Validation error displayed
- **Priority**: Medium

**Test Case 4: Password Security**
- **Objective**: Verify password field is masked
- **Prerequisites**: Login page is accessible
- **Steps**:
  1. Navigate to login page
  2. Enter password in password field
- **Expected Result**: Password characters are masked
- **Priority**: Medium

**Test Case 5: Session Management**
- **Objective**: Verify session timeout handling
- **Prerequisites**: User is logged in
- **Steps**:
  1. Login successfully
  2. Wait for session timeout
  3. Attempt to access protected resource
- **Expected Result**: User is redirected to login
- **Priority**: High`);
    setPreviewTitle("Login Module Test Cases");
    setPreviewOpen(true);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Removed OCR handlers and UI

  // Sidebar state not needed for removed files tray

  function normalizeMarkdownText(text: string): string {
    try {
      let s = text ?? "";
      // Convert common escaped sequences to real characters for proper MD rendering
      s = s.replace(/\\n/g, "\n");
      s = s.replace(/\\t/g, "\t");
      return s;
    } catch {
      return text;
    }
  }

  return (
    <div className={`
      flex h-full w-full transition-all duration-300
    `}>
      {/* Main Chat Area */}
      <div className={`flex flex-col h-full w-full ${previewOpen ? 'md:w-3/5' : 'w-full'}`}>
        {(!usecaseId) ? (
          // Welcome State
          <div className="flex-1 flex items-center justify-center p-4 sm:p-6 md:p-8">
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
        ) : (
          // Chat Messages
          <ScrollArea ref={scrollAreaRef} className="flex-1 pb-24 overflow-y-auto">
            <div className="space-y-4 sm:space-y-6 max-w-full md:max-w-4xl mx-auto px-4 overflow-hidden">
              {/* Status bar */}
              {(waitingForResponse || isOcrProcessing || isReqGenBlocking || reqGenStatus === "In Progress") && (
                <div className="text-xs text-muted-foreground px-2 py-1">
                  {waitingForResponse && <span>Sending…</span>}
                  {!waitingForResponse && isOcrProcessing && <span>Reading document(s)…</span>}
                  {!waitingForResponse && !isOcrProcessing && reqGenStatus === "In Progress" && <span>Requirement generation in progress…</span>}
                </div>
              )}
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.type === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden ${
                      message.type === "user"
                        ? "bg-chat-user border border-border ml-auto"
                        : "bg-chat-assistant border border-border mr-auto"
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
                      {message.type === "assistant" ? (
                        // IMPORTANT: Do NOT remove markdown rendering for assistant messages. It ensures
                        // headings, code blocks, tables, line breaks, and raw <br> are rendered correctly.
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          rehypePlugins={[rehypeHighlight]}
                        >
                          {normalizeMarkdownText(message.content)}
                        </ReactMarkdown>
                      ) : (
                        <>{message.content}</>
                      )}
                    </div>
                    {message.type === "assistant" && message.traces && (
                      <ChatTrace traces={message.traces as any} />
                    )}
                    {message.hasPreview && (
                      <Button
                        onClick={() => handleOpenPreview(message.id)}
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
                  <div className="bg-chat-assistant border border-border rounded-xl p-4 mr-auto">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{animationDelay: '0.1s'}} />
                      <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{animationDelay: '0.2s'}} />
                    </div>
                  </div>
                </div>
              )}
              
              {/* Empty div for scrolling to bottom */}
              <div ref={messagesEndRef} className="h-5 mb-20" />
            </div>
          </ScrollArea>
        )}

        {/* Chat Input */}
        <FloatingInputContainer>
          <div className="max-w-full md:max-w-4xl mx-auto px-4 space-y-2">
            {/* File Chips */}
            {pendingFiles.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {pendingFiles.map((file, index) => (
                  <FileChip
                    key={index}
                    file={file}
                    onRemove={() => handleRemoveFile(index)}
                  />
                ))}
              </div>
            )}
            
            <ChatInput 
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onSend={handleSend}
              onFileUpload={handleFileUpload}
              onKeyPress={handleKeyPress}
              isDisabled={status === "In Progress" || isLoading || reqGenConfirmOpen}
            />
            
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.doc,.docx,.txt"
              onChange={handleFileSelect}
              multiple
              className="hidden"
            />
          </div>
        </FloatingInputContainer>
      </div>

      {/* Preview Panel */}
      {previewOpen && (
        <div className="w-full md:w-2/5 h-full fixed md:relative right-0 top-0 z-40 md:z-auto">
          <PreviewPanel
            content={previewContent}
            title={previewTitle}
            onClose={() => setPreviewOpen(false)}
          />
        </div>
      )}

      <RequirementsGenerationConfirmModal
        open={reqGenConfirmOpen}
        onConfirm={async () => {
          if (!usecaseId) { setReqGenConfirmOpen(false); return; }
          setReqGenConfirmOpen(false);
          setIsReqGenBlocking(true);
          setIsLoading(false);
          setWaitingForResponse(false);
          try {
            await apiPost(`/requirements/${usecaseId}/generate`, {});
            // Start polling requirements status every 6s
            if (reqGenPollTimerRef.current) {
              window.clearInterval(reqGenPollTimerRef.current);
            }
            const startedAt = Date.now();
            reqGenPollTimerRef.current = window.setInterval(async () => {
              try {
                const status = await apiGet<any>(`/requirements/${usecaseId}/status`);
                const state = String(status?.requirement_generation || "").trim().toLowerCase();
                console.debug("[req-gen poll] state=", state, "inserted=", status?.total_inserted);
                if (state === "completed" || state === "failed") {
                  if (reqGenPollTimerRef.current) {
                    window.clearInterval(reqGenPollTimerRef.current);
                    reqGenPollTimerRef.current = null;
                  }
                  setIsReqGenBlocking(false);
                  setWaitingForResponse(false);
                  setIsLoading(false);
                  if (state === "completed") toast({ title: "Requirements generated", description: "You can now ask questions about requirements." });
                  if (state === "failed") toast({ title: "Requirement generation failed", description: "Please try again.", variant: "destructive" as any });
                }
                // Max timeout: 10 minutes
                if (Date.now() - startedAt > 10 * 60 * 1000) {
                  console.debug("[req-gen poll] stop due to max timeout");
                  if (reqGenPollTimerRef.current) {
                    window.clearInterval(reqGenPollTimerRef.current);
                    reqGenPollTimerRef.current = null;
                  }
                  setIsReqGenBlocking(false);
                  setWaitingForResponse(false);
                  setIsLoading(false);
                }
              } catch (e) {
                console.error("Error polling requirements status", e);
              }
            }, 6000);
          } catch (e) {
            console.error("Failed to start requirement generation", e);
            setIsReqGenBlocking(false);
          }
        }}
        onCancel={() => {
          setReqGenConfirmOpen(false);
          setIsReqGenBlocking(false);
          setWaitingForResponse(false);
          setIsLoading(false);
        }}
      />

    </div>
  );
}