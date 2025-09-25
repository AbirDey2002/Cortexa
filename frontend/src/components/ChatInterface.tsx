import { useEffect, useRef, useState } from "react";
import { FileText, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { FileChip } from "@/components/FileChip";
import { PreviewPanel } from "@/components/PreviewPanel";
import { apiGet, apiPost, API_BASE_URL } from "@/lib/utils";
import { useSidebar } from "@/components/ui/sidebar";
import { ChatInput, FloatingInputContainer } from "@/components/chat";

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
}

interface UploadedFile {
  name: string;
  type: string;
  file: File;
}

interface Props {
  userId: string;
  usecaseId: string | null;
}

export function ChatInterface({ userId, usecaseId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<string>("Completed");
  const [waitingForResponse, setWaitingForResponse] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages change
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  };

  // Load chat for selected usecase
  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!usecaseId) {
        setMessages([]);
        return;
      }
      try {
        const statuses = await apiGet<any>(`/test/statuses/${usecaseId}`);
        if (cancelled) return;
        setStatus(statuses.status || "Completed");
        const history = await apiGet<any[]>(`/test/chat/${usecaseId}`);
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
            return { id: `u-${idx}`, type: "user", content: entry.user, timestamp: ts } as Message;
          }
          const content = entry.system;
          // agent output contains JSON; show only user_answer if present
          let shown = content;
          try {
            const m = content.match(/```json\s*([\s\S]*?)\s*```/i);
            const jsonText = m ? m[1] : content;
            const obj = JSON.parse(jsonText);
            if (obj && obj.user_answer) shown = obj.user_answer;
          } catch {}
          return { id: `a-${idx}`, type: "assistant", content: shown, timestamp: ts } as Message;
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
        const response = await apiGet<any>(`/test/statuses/${usecaseId}`);
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
            const history = await apiGet<any[]>(`/test/chat/${usecaseId}`);
            
            // Sort messages by timestamp in ascending order (oldest first)
            const sortedHistory = [...history].sort((a, b) => {
              const tsA = new Date(a.timestamp || 0).getTime();
              const tsB = new Date(b.timestamp || 0).getTime();
              return tsA - tsB;
            });
            
            const mappedMessages = sortedHistory.map((entry, idx) => {
              const ts = new Date(entry.timestamp || Date.now());
              if (entry.user !== undefined) {
                return { id: `u-${idx}`, type: "user", content: entry.user, timestamp: ts } as Message;
              }
              const content = entry.system;
              let shown = content;
              try {
                const m = content.match(/```json\s*([\s\S]*?)\s*```/i);
                const jsonText = m ? m[1] : content;
                const obj = JSON.parse(jsonText);
                if (obj && obj.user_answer) shown = obj.user_answer;
              } catch {}
              return { id: `a-${idx}`, type: "assistant", content: shown, timestamp: ts } as Message;
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
      const usecases = await apiGet<any[]>(`/test/usecases`);
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
    };

    setMessages(prev => [...prev, userMessage]);
    // Scroll to bottom after user message is added
    setTimeout(scrollToBottom, 100);
    setInputValue("");
    setUploadedFiles([]);
    setIsLoading(true);

    try {
      await apiPost(`/test/chat/${targetUsecaseId}`, { role: "user", content: userMessage.content });
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
      const newFiles: UploadedFile[] = Array.from(files).map(file => ({
        name: file.name,
        type: file.type,
        file: file,
      }));
      setUploadedFiles(prev => [...prev, ...newFiles]);
    }
    // Reset the input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleRemoveFile = (index: number) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index));
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

  // Get sidebar state to adjust layout
  const { state: sidebarState } = useSidebar();
  const isSidebarCollapsed = sidebarState === "collapsed";
  
  return (
    <div className={`flex h-full w-full transition-all duration-300 ${isSidebarCollapsed ? 'pl-14' : 'pl-16 sm:pl-72 md:pl-80'}`}>
      {/* Main Chat Area */}
      <div className={`flex flex-col transition-all duration-300 h-full ${previewOpen ? 'w-full md:w-3/5' : 'w-full'} ${isSidebarCollapsed ? 'max-w-full sm:max-w-3xl md:max-w-4xl lg:max-w-5xl mx-auto px-4' : 'px-4'}`}>
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
          <ScrollArea ref={scrollAreaRef} className="flex-1 p-3 sm:p-4 md:p-6 pb-24 overflow-y-auto">
            <div className="space-y-4 sm:space-y-6 max-w-full md:max-w-4xl mx-auto overflow-hidden">
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
                    <div className="text-sm whitespace-pre-wrap leading-relaxed break-words overflow-hidden">
                      {message.content}
                    </div>
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
          <div className="space-y-2">
            {/* File Chips */}
            {uploadedFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 max-w-5xl mx-auto px-3">
                {uploadedFiles.map((file, index) => (
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
              isDisabled={status === "In Progress" || isLoading}
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
    </div>
  );
}