import { useState } from "react";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { TopNavigation } from "@/components/TopNavigation";
import { ChatInterface } from "@/components/ChatInterface";

interface LayoutProps {
  children?: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [currentModel, setCurrentModel] = useState("Cortexa-4 Pro");

  return (
    <SidebarProvider defaultOpen={true}>
      <div className="min-h-screen flex w-full bg-background">
        <AppSidebar />
        
        <div className="flex-1 flex flex-col">
          <TopNavigation 
            currentModel={currentModel}
            onModelChange={setCurrentModel}
          />
          
          <main className="flex-1 overflow-hidden">
            {children || <ChatInterface />}
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}