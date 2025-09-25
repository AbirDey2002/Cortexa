import { useEffect, useState } from "react";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
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
  const [currentModel, setCurrentModel] = useState("Cortexa-4 Pro");
  const [userId, setUserId] = useState<string>("");
  const [activeUsecaseId, setActiveUsecaseId] = useState<string | null>(null);

  // Use hardcoded user ID from backend
  useEffect(() => {
    (async () => {
      try {
        // Try to get existing usecases first
        const usecases = await apiGet<any[]>("/test/usecases");
        
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
        {/* App Sidebar with higher z-index to be on top of other elements */}
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
        
        <div className="flex-1 flex flex-col w-full">
          <div className="flex items-center h-12 sm:h-14 border-b border-border glassmorphism-navbar fixed top-0 left-0 right-0 z-40">
            <div className="flex items-center h-full pl-2 sm:pl-4">
              <SidebarTrigger className="mr-1 sm:mr-2" />
            </div>
            <div className="flex-1">
              <div className="max-w-full sm:max-w-3xl md:max-w-4xl lg:max-w-6xl mx-auto px-2 sm:px-4 transition-all duration-300">
                <TopNavigation 
                  currentModel={currentModel}
                  onModelChange={setCurrentModel}
                />
              </div>
            </div>
          </div>
          
          <main className="flex-1 overflow-hidden pt-12 sm:pt-14 pb-20 sm:pb-24">
            {children || <ChatInterface userId={userId} usecaseId={activeUsecaseId} />}
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}