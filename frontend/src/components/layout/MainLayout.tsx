import React, { useState, useRef } from "react";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { ChatPanel } from "./ChatPanel";
import { apiPost } from "@/lib/utils";

interface MainLayoutProps {
  children?: React.ReactNode;
  userId: string;
  activeUsecaseId: string | null;
  onSelectUsecase: (id: string) => void;
  onNewUsecase: (id: string) => void;
  onSendMessage: () => void;
  inputValue: string;
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  isInputDisabled?: boolean;
  uploadedFiles?: Array<{name: string; type: string}>;
  onRemoveFile?: (index: number) => void;
  onFileUpload: () => void;
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  children,
  userId,
  activeUsecaseId,
  onSelectUsecase,
  onNewUsecase,
  onSendMessage,
  inputValue,
  onInputChange,
  isInputDisabled = false,
  uploadedFiles = [],
  onRemoveFile,
  onFileUpload
}) => {
  const [currentModel, setCurrentModel] = useState("gemini-2.5-flash-lite");
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const handleModelChange = async (modelId: string) => {
    setCurrentModel(modelId);
    // Update usecase model if usecase is selected
    if (activeUsecaseId) {
      try {
        await apiPost(`/frontend/usecases/${activeUsecaseId}/model`, { model: modelId });
      } catch (error) {
      }
    }
  };
  
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSendMessage();
    }
  };
  
  return (
    <SidebarProvider defaultOpen={true}>
      <div className="flex h-screen w-full bg-[#0D0E10] text-gray-100">
        {/* Sidebar - absolute positioning to avoid affecting layout */}
        <div className="absolute z-[100]">
          <AppSidebar
            userId={userId}
            activeUsecaseId={activeUsecaseId}
            onSelectUsecase={onSelectUsecase}
            onNewUsecase={onNewUsecase}
          />
        </div>
        
        {/* Chat Panel - full width with proper margin */}
        <div className="w-full">
          <ChatPanel
          currentModel={currentModel}
          onModelChange={handleModelChange}
          inputValue={inputValue}
          onInputChange={onInputChange}
          onSend={onSendMessage}
          onFileUpload={onFileUpload}
          onKeyPress={handleKeyPress}
          isInputDisabled={isInputDisabled}
          uploadedFiles={uploadedFiles}
          onRemoveFile={onRemoveFile}
        >
          {children}
        </ChatPanel>
        </div>
      </div>
    </SidebarProvider>
  );
};
