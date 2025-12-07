import { useEffect, useState } from "react";
import { SidebarProvider, SidebarTrigger, SidebarInset, Sidebar } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { TopNavigation } from "@/components/TopNavigation";
import { ChatInterface } from "@/components/ChatInterface";
import { apiGet, apiPost } from "@/lib/utils";

interface LayoutProps {
  children?: React.ReactNode;
  initialUsecaseId?: string;
  onUsecaseChange?: (usecaseId: string) => void;
}

export function Layout({ children, initialUsecaseId, onUsecaseChange }: LayoutProps) {
  const [currentModel, setCurrentModel] = useState("gemini-2.5-flash-lite");
  const [userId, setUserId] = useState<string>("");
  const [activeUsecaseId, setActiveUsecaseId] = useState<string | null>(null);
  
  // Load model from usecase when usecase changes
  useEffect(() => {
    if (activeUsecaseId) {
      (async () => {
        try {
          const usecaseData = await apiGet<any>(`/usecases/${activeUsecaseId}`);
          if (usecaseData?.selected_model) {
            setCurrentModel(usecaseData.selected_model);
          }
        } catch (error) {
          console.error("Failed to load usecase model:", error);
        }
      })();
    }
  }, [activeUsecaseId]);

  // Use hardcoded user ID from backend
  useEffect(() => {
    (async () => {
      try {
        // Try to get existing usecases first
        const usecases = await apiGet<any[]>("/frontend/usecases/list");
        
        // Set the user ID if we have usecases
        if (usecases && usecases.length > 0) {
          setUserId(usecases[0].user_id);
          
          // If there's an initial usecase ID from the URL, use it
          if (initialUsecaseId) {
            // Verify the usecase exists
            const usecaseExists = usecases.some(u => u.usecase_id === initialUsecaseId);
            if (usecaseExists) {
              setActiveUsecaseId(initialUsecaseId);
              return;
            }
          }
          
          // Don't automatically set an active usecase - let the user choose
          return;
        }
        
        // Just set the user ID if we don't have usecases
        setUserId("52588196-f538-42bf-adb8-df885ab0120c");
      } catch (e) {
        console.error("Failed to get usecases:", e);
        // Fallback to hardcoded ID if fetching fails
        setUserId("52588196-f538-42bf-adb8-df885ab0120c");
      }
    })();
  }, [initialUsecaseId, onUsecaseChange]);
  
  // Listen for usecase creation events from ChatInterface
  useEffect(() => {
    const handleUsecaseCreated = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail && customEvent.detail.usecaseId) {
        setActiveUsecaseId(customEvent.detail.usecaseId);
        if (onUsecaseChange) onUsecaseChange(customEvent.detail.usecaseId);
      }
    };
    
    window.addEventListener('usecase-created', handleUsecaseCreated);
    return () => {
      window.removeEventListener('usecase-created', handleUsecaseCreated);
    };
  }, [onUsecaseChange]);

  // Removed auto-creation of new chat on entry

  return (
    <SidebarProvider defaultOpen={true}>
      <div className="min-h-screen flex w-full bg-background">
        {/* App Sidebar as inset column (no overlay); content provided by AppSidebar */}
        <Sidebar variant="inset" collapsible="offcanvas" className="border-r border-sidebar-border">
          <AppSidebar
            userId={userId}
            activeUsecaseId={activeUsecaseId}
            onSelectUsecase={(id) => {
              setActiveUsecaseId(id);
              if (onUsecaseChange) onUsecaseChange(id);
            }}
            onNewUsecase={(id) => {
              setActiveUsecaseId(id);
              if (onUsecaseChange) onUsecaseChange(id);
            }}
          />
        </Sidebar>
        
        <SidebarInset>
          <div className="flex items-center h-12 sm:h-14 border-b border-border glassmorphism-navbar sticky top-0 z-40 bg-background">
            <div className="flex items-center h-full pl-2 sm:pl-4">
              <SidebarTrigger className="mr-1 sm:mr-2 inline-flex md:peer-data-[state=expanded]:hidden" />
            </div>
            <div className="flex-1">
              <TopNavigation 
                currentModel={currentModel}
                onModelChange={async (modelId: string) => {
                  setCurrentModel(modelId);
                  // Update usecase model if usecase is selected
                  if (activeUsecaseId) {
                    try {
                      await apiPost(`/frontend/usecases/${activeUsecaseId}/model`, { model: modelId });
                    } catch (error) {
                      console.error("Failed to update usecase model:", error);
                    }
                  }
                }}
              />
            </div>
          </div>

          <main className="flex-1 overflow-hidden">
            {children || <ChatInterface userId={userId} usecaseId={activeUsecaseId} currentModel={currentModel} onModelChange={async (modelId: string) => {
              setCurrentModel(modelId);
              // Update usecase model if usecase is selected
              if (activeUsecaseId) {
                try {
                  await apiPost(`/frontend/usecases/${activeUsecaseId}/model`, { model: modelId });
                } catch (error) {
                  console.error("Failed to update usecase model:", error);
                }
              }
            }} />}
          </main>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}