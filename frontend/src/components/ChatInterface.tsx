import { useEffect, useRef, useState } from "react";
import { FileText, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { FileChip } from "@/components/FileChip";
import { PreviewPanel } from "@/components/PreviewPanel";
import { useApi } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { ChatInput, FloatingInputContainer, ChatTrace } from "@/components/chat";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { RequirementsGenerationConfirmModal } from "@/components/chat/RequirementsGenerationConfirmModal";
import { ScenariosGenerationConfirmModal } from "@/components/chat/ScenariosGenerationConfirmModal";
import { TestCasesGenerationConfirmModal } from "@/components/chat/TestCasesGenerationConfirmModal";
import { PdfContentMessage } from "@/components/chat/PdfContentMessage";
import { RequirementsMessage } from "@/components/chat/RequirementsMessage";
import { ScenariosMessage } from "@/components/chat/ScenariosMessage";
import { TestCasesMessage } from "@/components/chat/TestCasesMessage";
import { requestNotificationPermission, sendNotification } from "@/lib/notifications";

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
  currentModel?: string;
  onModelChange?: (modelId: string) => void;
}

export function ChatInterface({ userId, usecaseId, currentModel: propCurrentModel, onModelChange }: Props) {
  const { apiGet, apiPost } = useApi();
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
  const handledModalUsecasesRef = useRef<Record<string, boolean>>({});
  const [scenarioGenConfirmOpen, setScenarioGenConfirmOpen] = useState(false);
  const [testCaseGenConfirmOpen, setTestCaseGenConfirmOpen] = useState(false);
  const [isScenarioGenBlocking, setIsScenarioGenBlocking] = useState(false);
  const scenarioGenPollTimerRef = useRef<number | null>(null);
  const [scenarioGenStatus, setScenarioGenStatus] = useState<"Not Started" | "In Progress" | "Completed" | "Failed" | "">("");
  const [lastScenarioGenCheckedUsecaseId, setLastScenarioGenCheckedUsecaseId] = useState<string | null>(null);
  const [scenarioGenConfirmed, setScenarioGenConfirmed] = useState<boolean>(false);
  const handledScenarioModalUsecasesRef = useRef<Record<string, boolean>>({});
  const [isTestCaseGenBlocking, setIsTestCaseGenBlocking] = useState(false);
  const testCaseGenPollTimerRef = useRef<number | null>(null);
  const [testCaseGenStatus, setTestCaseGenStatus] = useState<"Not Started" | "In Progress" | "Completed" | "Failed" | "">("");
  const [lastTestCaseGenCheckedUsecaseId, setLastTestCaseGenCheckedUsecaseId] = useState<string | null>(null);
  const [testCaseGenConfirmed, setTestCaseGenConfirmed] = useState<boolean>(false);
  const handledTestCasesModalUsecasesRef = useRef<Record<string, boolean>>({});
  const ocrBannerTimerRef = useRef<number | null>(null);
  const [pendingFiles, setPendingFiles] = useState<SelectedFile[]>([]);
  const [currentModel, setCurrentModel] = useState<string>(propCurrentModel || "gemini-2.5-flash-lite");

  // Sync with prop if provided
  useEffect(() => {
    if (propCurrentModel !== undefined) {
      setCurrentModel(propCurrentModel);
    }
  }, [propCurrentModel]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pdfContentMessages, setPdfContentMessages] = useState<Array<{
    fileId: string;
    fileName: string;
    pages: Array<{ page_number: number; markdown: string; is_completed: boolean }>;
    timestamp: Date;
  }>>([]);
  const [requirementsMessages, setRequirementsMessages] = useState<Array<{
    requirements: Array<{
      id: string;
      name: string;
      description: string;
      requirement_entities?: any;
      created_at?: string;
    }>;
    timestamp: Date;
  }>>([]);
  const [scenariosMessages, setScenariosMessages] = useState<Array<{
    scenarios: Array<{
      id: string;
      display_id: number;
      scenario_name: string;
      scenario_description: string;
      scenario_id?: string;
      requirement_id: string;
      requirement_display_id: number;
      flows?: any[];
      created_at?: string;
    }>;
    timestamp: Date;
  }>>([]);
  const [testCasesMessages, setTestCasesMessages] = useState<Array<{
    testCases: Array<{
      id: string;
      display_id: number;
      test_case: string;
      description?: string;
      flow?: string;
      requirementId?: string;
      scenarioId?: string;
      preConditions?: string[];
      testData?: string[];
      testSteps?: string[];
      expectedResults?: string[];
      postConditions?: string[];
      risk_analysis?: string;
      requirement_category?: string;
      lens?: string;
      scenario_display_id?: number;
      scenario_name?: string;
      requirement_display_id?: number;
      created_at?: string;
    }>;
    timestamp: Date;
  }>>([]);
  const [expandedMessageId, setExpandedMessageId] = useState<string | null>(null);
  // Removed files tray and processing modal state
  const [status, setStatus] = useState<string>("Completed");
  const [waitingForResponse, setWaitingForResponse] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Removed OCR UI state

  // Scroll to bottom when messages change
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    } else if (scrollAreaRef.current) {
      // Fallback: scroll the ScrollArea container to bottom
      const scrollContainer = scrollAreaRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
    }
  };

  const notificationsEnabledRef = useRef(false);

  // Fetch notification settings
  useEffect(() => {
    if (userId) {
      apiGet<any>(`/users/${userId}`).then(user => {
        if (user) {
          notificationsEnabledRef.current = user.push_notification !== undefined ? user.push_notification : true;
          if (notificationsEnabledRef.current) {
            requestNotificationPermission();
          }
        }
      }).catch(() => { });
    }
  }, [userId]);

  // Handle push notifications for new messages
  useEffect(() => {
    if (messages.length === 0) return;

    const lastMessage = messages[messages.length - 1];
    if (lastMessage.type === "assistant" && !document.hasFocus() && notificationsEnabledRef.current) {
      // Find the corresponding user query if possible (message before last)
      const userQuery = messages[messages.length - 2]?.content || "Your Query";

      let title = "Cortexa Answered";
      // Try to make title more relevant
      if (messages.length >= 2) title = "Cortexa Answered: " + (userQuery.length > 20 ? userQuery.substring(0, 20) + "..." : userQuery);

      const body = extractMainTextFromStored(lastMessage.content);
      const preview = body.length > 50 ? body.substring(0, 50) + "..." : body;

      sendNotification(title, preview);
    }
  }, [messages]);

  // Load chat for selected usecase and reset per-chat state
  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!usecaseId) {
        setMessages([]);
        setPdfContentMessages([]);
        setRequirementsMessages([]);
        setScenariosMessages([]);
        setTestCasesMessages([]);
        setReqGenStatus("");
        setLastReqGenCheckedUsecaseId(null);
        setScenarioGenStatus("");
        setLastScenarioGenCheckedUsecaseId(null);
        setExpandedMessageId(null); // Reset expanded view when usecase changes
        // Cleanup polling timers
        if (reqGenPollTimerRef.current) {
          window.clearInterval(reqGenPollTimerRef.current);
          reqGenPollTimerRef.current = null;
        }
        if (scenarioGenPollTimerRef.current) {
          window.clearInterval(scenarioGenPollTimerRef.current);
          scenarioGenPollTimerRef.current = null;
        }
        if (testCaseGenPollTimerRef.current) {
          window.clearInterval(testCaseGenPollTimerRef.current);
          testCaseGenPollTimerRef.current = null;
        }
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
          // If already confirmed on backend, prevent modal from reopening for this usecase
          if (rg?.requirement_generation_confirmed) {
            handledModalUsecasesRef.current[usecaseId] = true;
          }
          setLastReqGenCheckedUsecaseId(usecaseId);
          if (rg?.requirement_generation === "In Progress") {
            setIsReqGenBlocking(true);
          } else if (rg?.requirement_generation === "Completed" || rg?.requirement_generation === "Failed") {
            setIsReqGenBlocking(false);
          }
        } catch { }
        // Initialize scenario generation status banner on usecase change
        try {
          const sg = await apiGet<any>(`/scenarios/${usecaseId}/status`);
          const sgState = String(sg?.scenario_generation || "").trim().toLowerCase();
          setScenarioGenStatus((sgState === "completed") ? "Completed" : (sgState === "in progress") ? "In Progress" : (sgState === "failed") ? "Failed" : "Not Started");
          setLastScenarioGenCheckedUsecaseId(usecaseId);
          if (sg?.scenario_generation === "In Progress") {
            setIsScenarioGenBlocking(true);
            // Start polling if in progress
            if (scenarioGenPollTimerRef.current) {
              window.clearInterval(scenarioGenPollTimerRef.current);
            }
            scenarioGenPollTimerRef.current = window.setInterval(async () => {
              try {
                const statusData = await apiGet<any>(`/scenarios/${usecaseId}/status`);
                if (statusData) {
                  const newStatus = statusData.scenario_generation || "Not Started";
                  setScenarioGenStatus(newStatus);
                  if (newStatus === "Completed" || newStatus === "Failed") {
                    if (scenarioGenPollTimerRef.current) {
                      window.clearInterval(scenarioGenPollTimerRef.current);
                      scenarioGenPollTimerRef.current = null;
                    }
                    setIsScenarioGenBlocking(false);
                  }
                }
              } catch (error) {
                if (scenarioGenPollTimerRef.current) {
                  window.clearInterval(scenarioGenPollTimerRef.current);
                  scenarioGenPollTimerRef.current = null;
                }
                setIsScenarioGenBlocking(false);
              }
            }, 6000);
          } else if (sg?.scenario_generation === "Completed" || sg?.scenario_generation === "Failed") {
            setIsScenarioGenBlocking(false);
          }
        } catch { }

        // Load model from usecase (only if not controlled by parent)
        if (propCurrentModel === undefined) {
          try {
            const usecaseData = await apiGet<any>(`/usecases/${usecaseId}`);
            if (usecaseData?.selected_model) {
              setCurrentModel(usecaseData.selected_model);
              // Notify parent if callback provided
              if (onModelChange) {
                onModelChange(usecaseData.selected_model);
              }
            }
          } catch { }
        }

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

          // Skip [modal] marker entries - they will be processed separately
          if (entry.modal) {
            return null;
          }

          const content = entry.system;
          // agent output contains JSON; show only user_answer if present
          let shown = extractMainTextFromStored(content);
          try {
            const m = content.match(/```json\s*([\s\S]*?)\s*```/i);
            const jsonText = m ? m[1] : content;
            const obj = JSON.parse(jsonText);
            if (obj && obj.system_event === "requirement_generation_confirmation_required") {
              // Always replace JSON with user-friendly message for display
              shown = "I've requested requirement generation. A confirmation modal will appear. Click 'Yes' to start the background process. You'll be notified when complete.";
              // Only trigger modal for fresh latest assistant message for this usecase, and if not already handled/confirmed
              const isLatest = idx === sortedHistory.length - 1;
              const alreadyHandled = !!handledModalUsecasesRef.current[usecaseId];
              if (isLatest && !alreadyHandled && !reqGenConfirmed) {
                setReqGenConfirmOpen(true);
                setIsReqGenBlocking(true);
                setWaitingForResponse(false);
                setIsLoading(false);
              }
            } else if (obj && obj.system_event === "requirement_generation_in_progress") {
              // Always replace JSON with user-friendly message for display
              shown = "Requirement generation is in progress. You'll be notified when complete.";
              setIsReqGenBlocking(true);
              setWaitingForResponse(false);
              setIsLoading(false);
              setReqGenStatus("In Progress");
            } else if (obj && obj.system_event === "scenario_generation_confirmation_required") {
              // Always replace JSON with user-friendly message for display
              shown = "I've requested scenario generation. A confirmation modal will appear. Click 'Yes' to start the background process. You'll be notified when complete.";
              // Only trigger modal for fresh latest assistant message for this usecase, and if not already handled/confirmed
              const isLatest = idx === sortedHistory.length - 1;
              const alreadyHandled = !!handledScenarioModalUsecasesRef.current[usecaseId];
              if (isLatest && !alreadyHandled && !scenarioGenConfirmed) {
                setScenarioGenConfirmOpen(true);
                setIsScenarioGenBlocking(true);
                setWaitingForResponse(false);
                setIsLoading(false);
              }
            } else if (obj && obj.system_event === "testcase_generation_confirmation_required") {
              // Always replace JSON with user-friendly message for display
              shown = "I've requested test case generation. A confirmation modal will appear. Click 'Yes' to start the background process. You'll be notified when complete.";
              // Only trigger modal for fresh latest assistant message for this usecase, and if not already handled/confirmed
              const isLatest = idx === sortedHistory.length - 1;
              const alreadyHandled = !!handledTestCasesModalUsecasesRef.current[usecaseId];
              if (isLatest && !alreadyHandled && !testCaseGenConfirmed) {
                setTestCaseGenConfirmOpen(true);
                setIsTestCaseGenBlocking(true);
                setWaitingForResponse(false);
                setIsLoading(false);
              }
            } else if (obj && obj.system_event === "testcase_generation_in_progress") {
              // Always replace JSON with user-friendly message for display
              shown = "Test case generation is in progress. You'll be notified when complete.";
              setIsTestCaseGenBlocking(true);
              setWaitingForResponse(false);
              setIsLoading(false);
              setTestCaseGenStatus("In Progress");
            } else if (obj && obj.system_event === "scenario_generation_in_progress") {
              // Always replace JSON with user-friendly message for display
              shown = "Scenario generation is in progress. You'll be notified when complete.";
              setIsScenarioGenBlocking(true);
              setWaitingForResponse(false);
              setIsLoading(false);
              setScenarioGenStatus("In Progress");
            } else if (obj && obj.user_answer) {
              shown = obj.user_answer;
            }
          } catch { }
          const msg: Message = { id: `a-${idx}`, type: "assistant", content: shown, timestamp: ts } as Message;
          if (entry.traces) {
            msg.traces = entry.traces as Traces;
          }
          return msg;
        }).filter((msg): msg is Message => msg !== null);

        setMessages(mappedMessages);

        // Check for [modal] markers in chat history and fetch content
        const modalMarkers = sortedHistory.filter((entry: any) => entry && entry.modal);

        // Track which types we found markers for BEFORE processing
        const foundPdfMarkers = modalMarkers.some((m: any) => m.modal?.file_id);
        const foundRequirementsMarkers = modalMarkers.some((m: any) => m.modal?.type === "requirements");
        const foundScenariosMarkers = modalMarkers.some((m: any) => m.modal?.type === "scenarios");
        const foundTestCasesMarkers = modalMarkers.some((m: any) => m.modal?.type === "testcases");


        if (modalMarkers.length > 0) {
          // Fetch PDF content and requirements for all markers - load asynchronously without blocking
          // Don't await - let messages render immediately while PDF content loads in background
          (async () => {
            const pdfContents: Array<{
              fileId: string;
              fileName: string;
              pages: Array<{ page_number: number; markdown: string; is_completed: boolean }>;
              timestamp: Date;
            }> = [];

            const requirementsContents: Array<{
              requirements: Array<{
                id: string;
                name: string;
                description: string;
                requirement_entities?: any;
                created_at?: string;
              }>;
              timestamp: Date;
            }> = [];

            const scenariosContents: Array<{
              scenarios: Array<{
                id: string;
                display_id: number;
                scenario_name: string;
                scenario_description: string;
                scenario_id?: string;
                requirement_id: string;
                requirement_display_id: number;
                flows?: any[];
                created_at?: string;
              }>;
              timestamp: Date;
            }> = [];

            const testCasesContents: Array<{
              testCases: Array<{
                id: string;
                display_id: number;
                test_case: string;
                description?: string;
                flow?: string;
                requirementId?: string;
                scenarioId?: string;
                preConditions?: string[];
                testData?: string[];
                testSteps?: string[];
                expectedResults?: string[];
                postConditions?: string[];
                risk_analysis?: string;
                requirement_category?: string;
                lens?: string;
                scenario_display_id?: number;
                scenario_name?: string;
                requirement_display_id?: number;
                created_at?: string;
              }>;
              timestamp: Date;
            }> = [];

            // Load modal content in parallel for better performance - use Promise.allSettled to handle errors gracefully
            const loadPromises = modalMarkers.map(async (markerEntry) => {
              const modal = markerEntry.modal;
              if (modal && modal.file_id) {
                // PDF modal
                try {
                  const fileContent = await apiGet<any>(`/files/file_contents/retrieval/${modal.file_id}`);
                  if (fileContent && fileContent.pages && fileContent.pages.length > 0) {
                    pdfContents.push({
                      fileId: fileContent.file_id,
                      fileName: fileContent.file_name,
                      pages: fileContent.pages,
                      timestamp: new Date(markerEntry.timestamp || modal.timestamp || Date.now())
                    });
                  } else {
                  }
                } catch (error) {
                  // Don't throw - continue loading other content
                }
              } else if (modal && modal.type === "requirements" && modal.usecase_id) {
                // Requirements modal
                try {
                  const requirementsData = await apiGet<any>(`/requirements/${modal.usecase_id}/list`);
                  if (requirementsData && requirementsData.requirements && requirementsData.requirements.length > 0) {
                    requirementsContents.push({
                      requirements: requirementsData.requirements,
                      timestamp: new Date(markerEntry.timestamp || modal.timestamp || Date.now())
                    });
                  } else {
                  }
                } catch (error) {
                }
              } else if (modal && modal.type === "scenarios" && modal.usecase_id) {
                // Scenarios modal
                try {
                  const scenariosData = await apiGet<any>(`/scenarios/${modal.usecase_id}/list-flat`);
                  if (scenariosData && scenariosData.scenarios && scenariosData.scenarios.length > 0) {
                    scenariosContents.push({
                      scenarios: scenariosData.scenarios,
                      timestamp: new Date(markerEntry.timestamp || modal.timestamp || Date.now())
                    });
                  } else {
                  }
                } catch (error) {
                }
              } else if (modal && modal.type === "testcases" && modal.usecase_id) {
                // Test cases modal
                try {
                  const testCasesData = await apiGet<any>(`/testcases/${modal.usecase_id}/list`);
                  if (testCasesData && testCasesData.test_cases && testCasesData.test_cases.length > 0) {
                    testCasesContents.push({
                      testCases: testCasesData.test_cases,
                      timestamp: new Date(markerEntry.timestamp || modal.timestamp || Date.now())
                    });
                  } else {
                  }
                } catch (error) {
                }
              }
            });

            // Wait for all loads to complete (but don't block message rendering - this runs in background)
            // Use allSettled so errors in one load don't prevent others from completing
            await Promise.allSettled(loadPromises);

            // Always update state for types we found markers for
            // When loading from chat history, we should load ALL markers found, not preserve existing state
            // (existing state was already cleared when usecase changed)
            // IMPORTANT: Set state for ALL found types, even if arrays are empty (API might return empty)
            // This ensures we don't accidentally preserve stale state
            if (foundPdfMarkers) {
              setPdfContentMessages(pdfContents);
            } else {
              // No PDF markers found - ensure state is cleared
              setPdfContentMessages([]);
            }
            if (foundRequirementsMarkers) {
              setRequirementsMessages(requirementsContents);
            } else {
              // No requirements markers found - ensure state is cleared
              setRequirementsMessages([]);
            }
            if (foundScenariosMarkers) {
              setScenariosMessages(scenariosContents);
            } else {
              // No scenarios markers found - ensure state is cleared
              setScenariosMessages([]);
            }
            if (foundTestCasesMarkers) {
              setTestCasesMessages(testCasesContents);
            } else {
              // No test cases markers found - ensure state is cleared
              setTestCasesMessages([]);
            }

          })();
        } else {
          // No modal markers found - clear all (this is correct when switching to a usecase with no modals)
          setPdfContentMessages([]);
          setRequirementsMessages([]);
          setScenariosMessages([]);
          setTestCasesMessages([]);
        }

        // Wait for DOM to update after all state changes, then scroll to bottom
        // Use requestAnimationFrame to ensure DOM is fully rendered
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setTimeout(() => {
              scrollToBottom();
              // Also try scrolling again after a short delay to catch any late-rendering content
              setTimeout(scrollToBottom, 200);
            }, 100);
          });
        });
      } catch (e) {
        setMessages([]);
        setPdfContentMessages([]);
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

            // Check for [modal] markers in chat history and fetch content
            const modalMarkers = sortedHistory.filter((entry: any) => entry && entry.modal);
            if (modalMarkers.length > 0) {
              // Fetch PDF content and requirements for all markers
              const pdfContents: Array<{
                fileId: string;
                fileName: string;
                pages: Array<{ page_number: number; markdown: string; is_completed: boolean }>;
                timestamp: Date;
              }> = [];

              const requirementsContents: Array<{
                requirements: Array<{
                  id: string;
                  name: string;
                  description: string;
                  requirement_entities?: any;
                  created_at?: string;
                }>;
                timestamp: Date;
              }> = [];

              const scenariosContents: Array<{
                scenarios: Array<{
                  id: string;
                  display_id: number;
                  scenario_name: string;
                  scenario_description: string;
                  scenario_id?: string;
                  requirement_id: string;
                  requirement_display_id: number;
                  flows?: any[];
                  created_at?: string;
                }>;
                timestamp: Date;
              }> = [];

              const testCasesContents: Array<{
                testCases: Array<{
                  id: string;
                  display_id: number;
                  test_case: string;
                  description?: string;
                  flow?: string;
                  requirementId?: string;
                  scenarioId?: string;
                  preConditions?: string[];
                  testData?: string[];
                  testSteps?: string[];
                  expectedResults?: string[];
                  postConditions?: string[];
                  risk_analysis?: string;
                  requirement_category?: string;
                  lens?: string;
                  scenario_display_id?: number;
                  scenario_name?: string;
                  requirement_display_id?: number;
                  created_at?: string;
                }>;
                timestamp: Date;
              }> = [];

              // Track which types we found markers for BEFORE processing
              const foundPdfMarkers = modalMarkers.some((m: any) => m.modal?.file_id);
              const foundRequirementsMarkers = modalMarkers.some((m: any) => m.modal?.type === "requirements");
              const foundScenariosMarkers = modalMarkers.some((m: any) => m.modal?.type === "scenarios");
              const foundTestCasesMarkers = modalMarkers.some((m: any) => m.modal?.type === "testcases");


              for (const markerEntry of modalMarkers) {
                const modal = markerEntry.modal;
                if (modal && modal.file_id) {
                  // PDF modal
                  try {
                    const fileContent = await apiGet<any>(`/files/file_contents/retrieval/${modal.file_id}`);
                    if (fileContent && fileContent.pages && fileContent.pages.length > 0) {
                      pdfContents.push({
                        fileId: fileContent.file_id,
                        fileName: fileContent.file_name,
                        pages: fileContent.pages,
                        timestamp: new Date(markerEntry.timestamp || modal.timestamp || Date.now())
                      });
                    }
                  } catch (error) {
                  }
                } else if (modal && modal.type === "requirements" && modal.usecase_id) {
                  // Requirements modal
                  try {
                    const requirementsData = await apiGet<any>(`/requirements/${modal.usecase_id}/list`);
                    if (requirementsData && requirementsData.requirements && requirementsData.requirements.length > 0) {
                      requirementsContents.push({
                        requirements: requirementsData.requirements,
                        timestamp: new Date(markerEntry.timestamp || modal.timestamp || Date.now())
                      });
                    }
                  } catch (error) {
                  }
                } else if (modal && modal.type === "scenarios" && modal.usecase_id) {
                  // Scenarios modal
                  try {
                    const scenariosData = await apiGet<any>(`/scenarios/${modal.usecase_id}/list-flat`);
                    if (scenariosData && scenariosData.scenarios && scenariosData.scenarios.length > 0) {
                      scenariosContents.push({
                        scenarios: scenariosData.scenarios,
                        timestamp: new Date(markerEntry.timestamp || modal.timestamp || Date.now())
                      });
                    } else {
                    }
                  } catch (error) {
                  }
                } else if (modal && modal.type === "testcases" && modal.usecase_id) {
                  // Test cases modal
                  try {
                    const testCasesData = await apiGet<any>(`/testcases/${modal.usecase_id}/list`);
                    if (testCasesData && testCasesData.test_cases && testCasesData.test_cases.length > 0) {
                      testCasesContents.push({
                        testCases: testCasesData.test_cases,
                        timestamp: new Date(markerEntry.timestamp || modal.timestamp || Date.now())
                      });
                    } else {
                    }
                  } catch (error) {
                  }
                }
              }

              // During polling, only update state for types we found markers for
              // This preserves existing state for types we didn't find markers for during polling
              // (polling is incremental, not a full reload)
              if (foundPdfMarkers) {
                setPdfContentMessages(pdfContents);
              }
              if (foundRequirementsMarkers) {
                setRequirementsMessages(requirementsContents);
              }
              if (foundScenariosMarkers) {
                setScenariosMessages(scenariosContents);
              }
              if (foundTestCasesMarkers) {
                setTestCasesMessages(testCasesContents);
              }

            }

            const mappedMessages = sortedHistory.map((entry, idx) => {
              const ts = new Date(entry.timestamp || Date.now());
              // Skip [modal] marker entries - they will be processed separately
              if (entry.modal) {
                return null;
              }
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
                  // Always replace JSON with user-friendly message for display
                  shown = "I've requested requirement generation. A confirmation modal will appear. Click 'Yes' to start the background process. You'll be notified when complete.";
                  // Only trigger modal for fresh latest assistant message
                  const isLatest = idx === sortedHistory.length - 1;
                  const alreadyHandled = !!handledModalUsecasesRef.current[usecaseId!];
                  if (isLatest && !alreadyHandled && !reqGenConfirmed) {
                    setReqGenConfirmOpen(true);
                    setIsReqGenBlocking(true);
                    setWaitingForResponse(false);
                    setIsLoading(false);
                    setReqGenStatus("Not Started");
                  }
                } else if (obj && obj.system_event === "requirement_generation_in_progress") {
                  // Always replace JSON with user-friendly message for display
                  shown = "Requirement generation is in progress. You'll be notified when complete.";
                  setIsReqGenBlocking(true);
                  setWaitingForResponse(false);
                  setIsLoading(false);
                  setReqGenStatus("In Progress");
                } else if (obj && obj.system_event === "scenario_generation_confirmation_required") {
                  // Always replace JSON with user-friendly message for display
                  shown = "I've requested scenario generation. A confirmation modal will appear. Click 'Yes' to start the background process. You'll be notified when complete.";
                  // Only trigger modal for fresh latest assistant message
                  const isLatest = idx === sortedHistory.length - 1;
                  const alreadyHandled = !!handledScenarioModalUsecasesRef.current[usecaseId!];
                  if (isLatest && !alreadyHandled && !scenarioGenConfirmed) {
                    setScenarioGenConfirmOpen(true);
                    setIsScenarioGenBlocking(true);
                    setWaitingForResponse(false);
                    setIsLoading(false);
                    setScenarioGenStatus("Not Started");
                  }
                } else if (obj && obj.system_event === "scenario_generation_in_progress") {
                  // Always replace JSON with user-friendly message for display
                  shown = "Scenario generation is in progress. You'll be notified when complete.";
                  setIsScenarioGenBlocking(true);
                  setWaitingForResponse(false);
                  setIsLoading(false);
                  setScenarioGenStatus("In Progress");
                } else if (obj && obj.system_event === "testcase_generation_confirmation_required") {
                  // Always replace JSON with user-friendly message for display
                  shown = "I've requested test case generation. A confirmation modal will appear. Click 'Yes' to start the background process. You'll be notified when complete.";
                  // Only trigger modal for fresh latest assistant message
                  const isLatest = idx === sortedHistory.length - 1;
                  const alreadyHandled = !!handledTestCasesModalUsecasesRef.current[usecaseId!];
                  if (isLatest && !alreadyHandled && !testCaseGenConfirmed) {
                    setTestCaseGenConfirmOpen(true);
                    setIsTestCaseGenBlocking(true);
                    setWaitingForResponse(false);
                    setIsLoading(false);
                    setTestCaseGenStatus("Not Started");
                  } else {
                  }
                } else if (obj && obj.system_event === "testcase_generation_in_progress") {
                  // Always replace JSON with user-friendly message for display
                  shown = "Test case generation is in progress. You'll be notified when complete.";
                  setIsTestCaseGenBlocking(true);
                  setWaitingForResponse(false);
                  setIsLoading(false);
                  setTestCaseGenStatus("In Progress");
                } else if (obj && obj.user_answer) {
                  shown = obj.user_answer;
                }
              } catch { }
              const msg: Message = { id: `a-${idx}`, type: "assistant", content: shown, timestamp: ts } as Message;
              if (entry.traces) {
                msg.traces = entry.traces as Traces;
              }
              return msg;
            }).filter((msg): msg is Message => msg !== null);

            setMessages(mappedMessages);

            // Scroll to bottom after messages are rendered
            setTimeout(scrollToBottom, 100);
          }
        }
      } catch (e) {
        setIsLoading(false);
        setWaitingForResponse(false); // Stop waiting on error
      }
    }

    // Start polling immediately when waiting for response
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

        const uploadResponse = await apiPost<any[]>('/files/file_contents/upload', formData);

        // Don't add PDF content immediately - wait for modal marker from backend
        // The modal marker will be created by the agent tool and will appear in polled history
        // This ensures correct timestamp ordering and consistency between streaming and reload

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
              }
              return;
            }
          } catch { }
          attempts += 1;
          setTimeout(checkOcr, 1500);
        };
        setTimeout(checkOcr, 1500);
      }

      // Send chat message with file information if available
      // Use prop model if provided, otherwise use local state
      const modelToUse = propCurrentModel !== undefined ? propCurrentModel : currentModel;
      const chatPayload: any = { role: "user", content: messageContent, model: modelToUse };
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
        window.dispatchEvent(new CustomEvent('chat-updated', { detail: { usecaseId: targetUsecaseId } }));
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
        ) : expandedMessageId ? (
          // Expanded view - render the expanded component
          (() => {
            // Rebuild the same data structures as in the normal view
            const groupedPdfs: Array<Array<{
              fileId: string;
              fileName: string;
              pages: Array<{ page_number: number; markdown: string; is_completed: boolean }>;
              timestamp: Date;
            }>> = [];

            const sortedPdfs = [...pdfContentMessages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
            const sortedRequirements = [...requirementsMessages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
            const sortedScenarios = [...scenariosMessages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
            const sortedTestCases = [...testCasesMessages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());

            sortedPdfs.forEach((pdf) => {
              let addedToGroup = false;
              for (const group of groupedPdfs) {
                const groupTimestamps = group.map(p => p.timestamp.getTime());
                const minTime = Math.min(...groupTimestamps);
                const maxTime = Math.max(...groupTimestamps);
                const pdfTime = pdf.timestamp.getTime();

                if (Math.abs(pdfTime - minTime) <= 5000 || Math.abs(pdfTime - maxTime) <= 5000) {
                  group.push(pdf);
                  addedToGroup = true;
                  break;
                }
              }

              if (!addedToGroup) {
                groupedPdfs.push([pdf]);
              }
            });

            // Find which message is expanded
            const allItems: Array<{
              type: 'message' | 'pdf-group' | 'requirements' | 'scenarios' | 'testcases';
              timestamp: Date;
              data: any;
            }> = [
              ...messages.map(m => ({ type: 'message' as const, timestamp: m.timestamp, data: m })),
              ...groupedPdfs.map(group => ({
                type: 'pdf-group' as const,
                timestamp: group[0].timestamp,
                data: group.map(p => ({
                  fileId: p.fileId,
                  fileName: p.fileName,
                  pages: p.pages
                }))
              })),
              ...sortedRequirements.map(req => ({
                type: 'requirements' as const,
                timestamp: req.timestamp,
                data: req.requirements
              })),
              ...sortedScenarios.map(scen => ({
                type: 'scenarios' as const,
                timestamp: scen.timestamp,
                data: scen.scenarios
              })),
              ...sortedTestCases.map(tc => ({
                type: 'testcases' as const,
                timestamp: tc.timestamp,
                data: tc.testCases
              }))
            ].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());

            // Find the expanded item
            let expandedItem: typeof allItems[0] | null = null;
            let expandedIdx = -1;
            allItems.forEach((item, idx) => {
              let messageId = '';
              if (item.type === 'pdf-group') {
                const pdfFiles = item.data as Array<{ fileId: string }>;
                messageId = `pdf-group-${idx}-${pdfFiles.map(f => f.fileId).join('-')}`;
              } else if (item.type === 'requirements') {
                const requirements = item.data as Array<{ id: string }>;
                messageId = `requirements-${idx}-${requirements.map(r => r.id).join('-')}`;
              } else if (item.type === 'scenarios') {
                const scenarios = item.data as Array<{ id: string }>;
                messageId = `scenarios-${idx}-${scenarios.map(s => s.id).join('-')}`;
              } else if (item.type === 'testcases') {
                const testCases = item.data as Array<{ id: string }>;
                messageId = `testcases-${idx}-${testCases.map(tc => tc.id).join('-')}`;
              }
              if (messageId === expandedMessageId) {
                expandedItem = item;
                expandedIdx = idx;
              }
            });

            if (expandedItem) {
              if (expandedItem.type === 'pdf-group') {
                const pdfFiles = expandedItem.data as Array<{ fileId: string; fileName: string; pages: Array<{ page_number: number; markdown: string; is_completed: boolean }> }>;
                return (
                  <PdfContentMessage
                    key={expandedMessageId}
                    files={pdfFiles}
                    messageId={expandedMessageId}
                    onExpand={setExpandedMessageId}
                    isExpanded={true}
                    onMinimize={() => setExpandedMessageId(null)}
                  />
                );
              } else if (expandedItem.type === 'requirements') {
                const requirements = expandedItem.data as Array<{ id: string; name: string; description: string; requirement_entities?: any; created_at?: string }>;
                return (
                  <RequirementsMessage
                    key={expandedMessageId}
                    requirements={requirements}
                    usecaseId={usecaseId || ""}
                    messageId={expandedMessageId}
                    onExpand={setExpandedMessageId}
                    isExpanded={true}
                    onMinimize={() => setExpandedMessageId(null)}
                  />
                );
              } else if (expandedItem.type === 'scenarios') {
                const scenarios = expandedItem.data as Array<{ id: string; display_id: number; scenario_name: string; scenario_description: string; scenario_id?: string; requirement_id: string; requirement_display_id: number; flows?: any[]; created_at?: string }>;
                return (
                  <ScenariosMessage
                    key={expandedMessageId}
                    scenarios={scenarios}
                    usecaseId={usecaseId || ""}
                    messageId={expandedMessageId}
                    onExpand={setExpandedMessageId}
                    isExpanded={true}
                    onMinimize={() => setExpandedMessageId(null)}
                  />
                );
              } else if (expandedItem.type === 'testcases') {
                const testCases = expandedItem.data as Array<{
                  id: string;
                  display_id: number;
                  test_case: string;
                  description?: string;
                  flow?: string;
                  requirementId?: string;
                  scenarioId?: string;
                  preConditions?: string[];
                  testData?: string[];
                  testSteps?: string[];
                  expectedResults?: string[];
                  postConditions?: string[];
                  risk_analysis?: string;
                  requirement_category?: string;
                  lens?: string;
                  scenario_display_id?: number;
                  scenario_name?: string;
                  requirement_display_id?: number;
                  created_at?: string;
                }>;
                return (
                  <TestCasesMessage
                    key={expandedMessageId}
                    testCases={testCases}
                    usecaseId={usecaseId || ""}
                    messageId={expandedMessageId}
                    onExpand={setExpandedMessageId}
                    isExpanded={true}
                    onMinimize={() => setExpandedMessageId(null)}
                  />
                );
              }
            }
            return null;
          })()
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
              {(() => {
                // Combine messages and PDF content messages, sorted by timestamp
                // Group PDFs by timestamp proximity (within 5 seconds)
                const groupedPdfs: Array<Array<{
                  fileId: string;
                  fileName: string;
                  pages: Array<{ page_number: number; markdown: string; is_completed: boolean }>;
                  timestamp: Date;
                }>> = [];

                const sortedPdfs = [...pdfContentMessages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
                const sortedRequirements = [...requirementsMessages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
                const sortedScenarios = [...scenariosMessages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
                const sortedTestCases = [...testCasesMessages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());

                sortedPdfs.forEach((pdf) => {
                  // Find a group where this PDF's timestamp is within 5 seconds of any PDF in the group
                  let addedToGroup = false;
                  for (const group of groupedPdfs) {
                    const groupTimestamps = group.map(p => p.timestamp.getTime());
                    const minTime = Math.min(...groupTimestamps);
                    const maxTime = Math.max(...groupTimestamps);
                    const pdfTime = pdf.timestamp.getTime();

                    // Check if PDF is within 5 seconds (5000ms) of the group
                    if (Math.abs(pdfTime - minTime) <= 5000 || Math.abs(pdfTime - maxTime) <= 5000) {
                      group.push(pdf);
                      addedToGroup = true;
                      break;
                    }
                  }

                  // If not added to any group, create a new group
                  if (!addedToGroup) {
                    groupedPdfs.push([pdf]);
                  }
                });

                // Create items for rendering: messages, grouped PDFs, requirements, scenarios, and test cases
                const allItems: Array<{
                  type: 'message' | 'pdf-group' | 'requirements' | 'scenarios' | 'testcases';
                  timestamp: Date;
                  data: Message | Array<{ fileId: string; fileName: string; pages: Array<{ page_number: number; markdown: string; is_completed: boolean }> }> | Array<{ id: string; name: string; description: string; requirement_entities?: any; created_at?: string }> | Array<{ id: string; display_id: number; scenario_name: string; scenario_description: string; scenario_id?: string; requirement_id: string; requirement_display_id: number; flows?: any[]; created_at?: string }> | Array<{ id: string; display_id: number; test_case: string; description?: string; flow?: string; requirementId?: string; scenarioId?: string; preConditions?: string[]; testData?: string[]; testSteps?: string[]; expectedResults?: string[]; postConditions?: string[]; risk_analysis?: string; requirement_category?: string; lens?: string; scenario_display_id?: number; scenario_name?: string; requirement_display_id?: number; created_at?: string }>;
                }> = [
                  ...messages.map(m => ({ type: 'message' as const, timestamp: m.timestamp, data: m })),
                  ...groupedPdfs.map(group => ({
                    type: 'pdf-group' as const,
                    timestamp: group[0].timestamp, // Use first PDF's timestamp for sorting
                    data: group.map(p => ({
                      fileId: p.fileId,
                      fileName: p.fileName,
                      pages: p.pages
                    }))
                  })),
                  ...sortedRequirements.map(req => ({
                    type: 'requirements' as const,
                    timestamp: req.timestamp,
                    data: req.requirements
                  })),
                  ...sortedScenarios.map(scen => ({
                    type: 'scenarios' as const,
                    timestamp: scen.timestamp,
                    data: scen.scenarios
                  })),
                  ...sortedTestCases.map(tc => ({
                    type: 'testcases' as const,
                    timestamp: tc.timestamp,
                    data: tc.testCases
                  }))
                ].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());

                // If allItems is empty but we have messages, ensure messages are shown
                if (allItems.length === 0 && messages.length > 0) {
                  return messages.map((message) => (
                    <div
                      key={message.id}
                      className={`flex ${message.type === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden ${message.type === "user"
                          ? "bg-chat-user border border-border ml-auto"
                          : "bg-chat-assistant border border-border mr-auto"
                          }`}
                      >
                        <div className="text-sm leading-relaxed break-words overflow-x-auto overflow-y-visible markdown-content">
                          {message.type === "assistant" ? (
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
                        <div className="text-xs text-muted-foreground mt-2">
                          {message.timestamp.toLocaleTimeString()}
                        </div>
                      </div>
                    </div>
                  ));
                }

                try {
                  return allItems.map((item, idx) => {
                    if (item.type === 'pdf-group') {
                      const pdfFiles = item.data as Array<{ fileId: string; fileName: string; pages: Array<{ page_number: number; markdown: string; is_completed: boolean }> }>;
                      const messageId = `pdf-group-${idx}-${pdfFiles.map(f => f.fileId).join('-')}`;
                      return (
                        <PdfContentMessage
                          key={messageId}
                          files={pdfFiles}
                          messageId={messageId}
                          onExpand={setExpandedMessageId}
                          isExpanded={expandedMessageId === messageId}
                          onMinimize={() => setExpandedMessageId(null)}
                        />
                      );
                    } else if (item.type === 'requirements') {
                      const requirements = item.data as Array<{ id: string; name: string; description: string; requirement_entities?: any; created_at?: string }>;
                      const messageId = `requirements-${idx}-${requirements.map(r => r.id).join('-')}`;
                      return (
                        <RequirementsMessage
                          key={messageId}
                          requirements={requirements}
                          usecaseId={usecaseId || ""}
                          messageId={messageId}
                          onExpand={setExpandedMessageId}
                          isExpanded={expandedMessageId === messageId}
                          onMinimize={() => setExpandedMessageId(null)}
                        />
                      );
                    } else if (item.type === 'scenarios') {
                      const scenarios = item.data as Array<{ id: string; display_id: number; scenario_name: string; scenario_description: string; scenario_id?: string; requirement_id: string; requirement_display_id: number; flows?: any[]; created_at?: string }>;
                      const messageId = `scenarios-${idx}-${scenarios.map(s => s.id).join('-')}`;
                      const isExpanded = expandedMessageId === messageId;
                      return (
                        <ScenariosMessage
                          key={messageId}
                          scenarios={scenarios}
                          usecaseId={usecaseId || ""}
                          messageId={messageId}
                          onExpand={setExpandedMessageId}
                          isExpanded={isExpanded}
                          onMinimize={() => setExpandedMessageId(null)}
                        />
                      );
                    } else if (item.type === 'testcases') {
                      const testCases = item.data as Array<{
                        id: string;
                        display_id: number;
                        test_case: string;
                        description?: string;
                        flow?: string;
                        requirementId?: string;
                        scenarioId?: string;
                        preConditions?: string[];
                        testData?: string[];
                        testSteps?: string[];
                        expectedResults?: string[];
                        postConditions?: string[];
                        risk_analysis?: string;
                        requirement_category?: string;
                        lens?: string;
                        scenario_display_id?: number;
                        scenario_name?: string;
                        requirement_display_id?: number;
                        created_at?: string;
                      }>;
                      const messageId = `testcases-${idx}-${testCases.map(tc => tc.id).join('-')}`;
                      const isExpanded = expandedMessageId === messageId;
                      return (
                        <TestCasesMessage
                          key={messageId}
                          testCases={testCases}
                          usecaseId={usecaseId || ""}
                          messageId={messageId}
                          onExpand={setExpandedMessageId}
                          isExpanded={isExpanded}
                          onMinimize={() => setExpandedMessageId(null)}
                        />
                      );
                    } else {
                      const message = item.data as Message;
                      return (
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
                              {message.type === "assistant" ? (
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
                      );
                    }
                  });
                } catch (error) {
                  // Fallback: render just messages if there's an error
                  return messages.map((message) => (
                    <div
                      key={message.id}
                      className={`flex ${message.type === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden ${message.type === "user"
                          ? "bg-chat-user border border-border ml-auto"
                          : "bg-chat-assistant border border-border mr-auto"
                          }`}
                      >
                        <div className="text-sm leading-relaxed break-words overflow-x-auto overflow-y-visible markdown-content">
                          {message.type === "assistant" ? (
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
                        <div className="text-xs text-muted-foreground mt-2">
                          {message.timestamp.toLocaleTimeString()}
                        </div>
                      </div>
                    </div>
                  ));
                }
              })()}

              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-chat-assistant border border-border rounded-xl p-4 mr-auto">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                      <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
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
              isDisabled={status === "In Progress" || isLoading || reqGenConfirmOpen || scenarioGenConfirmOpen || testCaseGenConfirmOpen}
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

      <ScenariosGenerationConfirmModal
        open={scenarioGenConfirmOpen}
        onConfirm={async () => {
          if (!usecaseId) { setScenarioGenConfirmOpen(false); return; }
          // Optimistically prevent re-opening for this usecase in current session
          handledScenarioModalUsecasesRef.current[usecaseId] = true;
          setScenarioGenConfirmOpen(false);
          setIsScenarioGenBlocking(true);
          setIsLoading(false);
          setWaitingForResponse(false);
          try {
            await apiPost(`/scenarios/${usecaseId}/generate`, {});
            // Start polling scenario generation status every 6s
            if (scenarioGenPollTimerRef.current) {
              window.clearInterval(scenarioGenPollTimerRef.current);
            }
            const startedAt = Date.now();
            scenarioGenPollTimerRef.current = window.setInterval(async () => {
              try {
                const statusData = await apiGet<any>(`/scenarios/${usecaseId}/status`);
                if (statusData) {
                  const newStatus = statusData.scenario_generation || "Not Started";
                  setScenarioGenStatus(newStatus);
                  setLastScenarioGenCheckedUsecaseId(usecaseId);
                  if (newStatus === "Completed" || newStatus === "Failed") {
                    if (scenarioGenPollTimerRef.current) {
                      window.clearInterval(scenarioGenPollTimerRef.current);
                      scenarioGenPollTimerRef.current = null;
                    }
                    setIsScenarioGenBlocking(false);
                    if (newStatus === "Completed") {
                      toast({
                        title: "Scenario generation completed",
                        description: `Generated ${statusData.total_inserted || 0} scenarios successfully.`,
                      });
                    } else {
                      toast({
                        title: "Scenario generation failed",
                        description: "Scenario generation encountered an error. Please try again.",
                        variant: "destructive",
                      });
                    }
                  }
                }
              } catch (error) {
                // Stop polling on error
                if (scenarioGenPollTimerRef.current) {
                  window.clearInterval(scenarioGenPollTimerRef.current);
                  scenarioGenPollTimerRef.current = null;
                }
                setIsScenarioGenBlocking(false);
              }
            }, 6000);
            setScenarioGenStatus("In Progress");
            toast({
              title: "Scenario generation started",
              description: "Scenarios are being generated in the background. You'll be notified when complete.",
            });
          } catch (error) {
            setIsScenarioGenBlocking(false);
            toast({
              title: "Error",
              description: "Failed to start scenario generation. Please try again.",
              variant: "destructive",
            });
          }
        }}
        onCancel={() => {
          setScenarioGenConfirmOpen(false);
          setIsScenarioGenBlocking(false);
          setIsLoading(false);
          setWaitingForResponse(false);
        }}
      />

      <RequirementsGenerationConfirmModal
        open={reqGenConfirmOpen}
        onConfirm={async () => {
          if (!usecaseId) { setReqGenConfirmOpen(false); return; }
          // Optimistically prevent re-opening for this usecase in current session
          handledModalUsecasesRef.current[usecaseId] = true;
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
                  if (reqGenPollTimerRef.current) {
                    window.clearInterval(reqGenPollTimerRef.current);
                    reqGenPollTimerRef.current = null;
                  }
                  setIsReqGenBlocking(false);
                  setWaitingForResponse(false);
                  setIsLoading(false);
                }
              } catch (e) {
              }
            }, 6000);
          } catch (e) {
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

      <TestCasesGenerationConfirmModal
        open={testCaseGenConfirmOpen}
        onConfirm={async () => {
          if (!usecaseId) { setTestCaseGenConfirmOpen(false); return; }
          // Optimistically prevent re-opening for this usecase in current session
          handledTestCasesModalUsecasesRef.current[usecaseId] = true;
          setTestCaseGenConfirmOpen(false);
          setIsTestCaseGenBlocking(true);
          setIsLoading(false);
          setWaitingForResponse(false);
          try {
            await apiPost(`/testcases/${usecaseId}/generate`, {});
            // Start polling test case generation status every 6s
            if (testCaseGenPollTimerRef.current) {
              window.clearInterval(testCaseGenPollTimerRef.current);
            }
            const startedAt = Date.now();
            testCaseGenPollTimerRef.current = window.setInterval(async () => {
              try {
                const statusData = await apiGet<any>(`/testcases/${usecaseId}/status`);
                if (statusData) {
                  const newStatus = statusData.test_case_generation || "Not Started";
                  setTestCaseGenStatus(newStatus);
                  setLastTestCaseGenCheckedUsecaseId(usecaseId);
                  if (newStatus === "Completed" || newStatus === "Failed") {
                    if (testCaseGenPollTimerRef.current) {
                      window.clearInterval(testCaseGenPollTimerRef.current);
                      testCaseGenPollTimerRef.current = null;
                    }
                    setIsTestCaseGenBlocking(false);
                    if (newStatus === "Completed") {
                      toast({
                        title: "Test case generation completed",
                        description: `Generated ${statusData.total_inserted || 0} test cases successfully.`,
                      });
                    } else {
                      toast({
                        title: "Test case generation failed",
                        description: "Test case generation encountered an error. Please try again.",
                        variant: "destructive",
                      });
                    }
                  }
                }
              } catch (error) {
                // Stop polling on error
                if (testCaseGenPollTimerRef.current) {
                  window.clearInterval(testCaseGenPollTimerRef.current);
                  testCaseGenPollTimerRef.current = null;
                }
                setIsTestCaseGenBlocking(false);
              }
            }, 6000);
            setTestCaseGenStatus("In Progress");
            toast({
              title: "Test case generation started",
              description: "Test cases are being generated in the background. You'll be notified when complete.",
            });
          } catch (error) {
            setIsTestCaseGenBlocking(false);
            toast({
              title: "Error",
              description: "Failed to start test case generation. Please try again.",
              variant: "destructive",
            });
          }
        }}
        onCancel={() => {
          setTestCaseGenConfirmOpen(false);
          setIsTestCaseGenBlocking(false);
          setIsLoading(false);
          setWaitingForResponse(false);
        }}
      />

    </div>
  );
}