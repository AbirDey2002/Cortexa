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
  userId: string;
}

export function Layout({ children, initialUsecaseId, onUsecaseChange, userId }: LayoutProps) {
  const [currentModel, setCurrentModel] = useState("gemini-2.5-flash-lite");
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

  // Load usecases and set active usecase if provided
  useEffect(() => {
    if (!userId) return;
    
    (async () => {
      try {
        // Try to get existing usecases
        const usecases = await apiGet<any[]>("/frontend/usecases/list");
        
        // If there's an initial usecase ID from the URL, use it
        if (initialUsecaseId && usecases) {
          // Verify the usecase exists
          const usecaseExists = usecases.some(u => u.usecase_id === initialUsecaseId);
          if (usecaseExists) {
            setActiveUsecaseId(initialUsecaseId);
            return;
          }
        }
        
        // Don't automatically set an active usecase - let the user choose
      } catch (e) {
        console.error("Failed to get usecases:", e);
      }
    })();
  }, [initialUsecaseId, onUsecaseChange, userId]);
  
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