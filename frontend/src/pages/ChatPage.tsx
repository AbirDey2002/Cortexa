import React, { useEffect, useRef, useState } from "react";
import { MainLayout } from "@/components/layout";
import { ChatContent, ChatPreview } from "@/components/chat";
import { apiGet, apiPost } from "@/lib/utils";

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

interface ChatPageProps {
  initialUsecaseId?: string;
}

export const ChatPage: React.FC<ChatPageProps> = ({ initialUsecaseId }) => {
  const [userId, setUserId] = useState<string>("");
  const [activeUsecaseId, setActiveUsecaseId] = useState<string | null>(initialUsecaseId || null);
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

  // Load user ID
  useEffect(() => {
    (async () => {
      try {
        const usecases = await apiGet<any[]>("/frontend/usecases/list");

        if (usecases && usecases.length > 0) {
          setUserId(usecases[0].user_id);

          if (initialUsecaseId) {
            const usecaseExists = usecases.some(u => u.usecase_id === initialUsecaseId);
            if (usecaseExists) {
              setActiveUsecaseId(initialUsecaseId);
            }
          }
          return;
        }

        setUserId("52588196-f538-42bf-adb8-df885ab0120c");
      } catch (e) {
        setUserId("52588196-f538-42bf-adb8-df885ab0120c");
      }
    })();
  }, [initialUsecaseId]);

  // Load chat for selected usecase
  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!activeUsecaseId) {
        setMessages([]);
        return;
      }
      try {
        const statuses = await apiGet<any>(`/frontend/usecases/${activeUsecaseId}/statuses`);
        if (cancelled) return;
        setStatus(statuses.status || "Completed");
        const history = await apiGet<any[]>(`/frontend/usecases/${activeUsecaseId}/chat`);
        if (cancelled) return;

        // Sort messages by timestamp in ascending order (oldest first)
        const sortedHistory = [...history].sort((a, b) => {
          const tsA = new Date(a.timestamp || 0).getTime();
          const tsB = new Date(b.timestamp || 0).getTime();
          return tsA - tsB;
        });

        setMessages(
          sortedHistory.map((entry, idx) => {
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
            } catch { }
            return { id: `a-${idx}`, type: "assistant", content: shown, timestamp: ts } as Message;
          })
        );
      } catch (e) {
        setMessages([]);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [activeUsecaseId]);

  // Unified polling for status and message retrieval
  useEffect(() => {
    if (!activeUsecaseId || !waitingForResponse) return;

    let timer: any;

    async function poll() {
      try {
        const response = await apiGet<any>(`/frontend/usecases/${activeUsecaseId}/statuses`);
        const currentStatus = response.status || "Completed";
        setStatus(currentStatus);

        if (currentStatus === "In Progress") {
          setIsLoading(true);
          timer = setTimeout(poll, 2000);
        } else if (currentStatus === "Completed") {
          setIsLoading(false);
          setWaitingForResponse(false);

          if (response.latest_message && !messages.some(m =>
            m.type === "assistant" && m.content === response.latest_message)) {

            const systemMessage: Message = {
              id: `a-${Date.now()}`,
              type: "assistant",
              content: response.latest_message,
              timestamp: new Date(),
            };

            setMessages(prev => [...prev, systemMessage]);
          } else {
            const history = await apiGet<any[]>(`/frontend/usecases/${activeUsecaseId}/chat`);

            const sortedHistory = [...history].sort((a, b) => {
              const tsA = new Date(a.timestamp || 0).getTime();
              const tsB = new Date(b.timestamp || 0).getTime();
              return tsA - tsB;
            });

            setMessages(
              sortedHistory.map((entry, idx) => {
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
                } catch { }
                return { id: `a-${idx}`, type: "assistant", content: shown, timestamp: ts } as Message;
              })
            );
          }
        }
      } catch (e) {
        setIsLoading(false);
        setWaitingForResponse(false);
      }
    }

    poll();

    return () => {
      clearTimeout(timer);
    };
  }, [activeUsecaseId, waitingForResponse, messages]);

  const handleSend = async () => {
    if (!inputValue.trim() || !activeUsecaseId) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: "user",
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue("");
    setUploadedFiles([]);
    setIsLoading(true);

    try {
      await apiPost(`/usecases/${activeUsecaseId}/gemini-chat`, { role: "user", content: userMessage.content });
      setStatus("In Progress");
      setWaitingForResponse(true);

      if (window.dispatchEvent) {
        window.dispatchEvent(new CustomEvent('chat-updated', { detail: { usecaseId: activeUsecaseId } }));
      }
    } catch (e) {
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
- **Priority**: Medium`);
    setPreviewTitle("Login Module Test Cases");
    setPreviewOpen(true);
  };

  return (
    <MainLayout
      userId={userId}
      activeUsecaseId={activeUsecaseId}
      onSelectUsecase={setActiveUsecaseId}
      onNewUsecase={setActiveUsecaseId}
      onSendMessage={handleSend}
      inputValue={inputValue}
      onInputChange={(e) => setInputValue(e.target.value)}
      isInputDisabled={status === "In Progress" || isLoading}
      uploadedFiles={uploadedFiles}
      onRemoveFile={handleRemoveFile}
      onFileUpload={handleFileUpload}
    >
      <div className="flex h-full">
        {/* Main Content */}
        <div className={`flex-1 ${previewOpen ? 'hidden md:block md:w-3/5' : 'w-full'}`}>
          <ChatContent
            usecaseId={activeUsecaseId}
            messages={messages}
            isLoading={isLoading}
            onOpenPreview={handleOpenPreview}
          />
        </div>

        {/* Preview Panel */}
        {previewOpen && (
          <div className="w-full md:w-2/5 h-full">
            <ChatPreview
              content={previewContent}
              title={previewTitle}
              onClose={() => setPreviewOpen(false)}
            />
          </div>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.doc,.docx,.txt"
        onChange={handleFileSelect}
        multiple
        className="hidden"
      />
    </MainLayout>
  );
};
