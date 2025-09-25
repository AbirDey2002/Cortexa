import React from "react";
import { useSidebar, SidebarTrigger } from "@/components/ui/sidebar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { TopNavigation } from "@/components/TopNavigation";
import { ChatInput } from "@/components/chat/ChatInput";
import { FileChip } from "@/components/FileChip";
import { Menu } from "lucide-react";

interface ChatPanelProps {
  children?: React.ReactNode;
  currentModel: string;
  onModelChange: (model: string) => void;
  inputValue: string;
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
  onFileUpload: () => void;
  onKeyPress: (e: React.KeyboardEvent) => void;
  isInputDisabled?: boolean;
  uploadedFiles?: Array<{name: string; type: string}>;
  onRemoveFile?: (index: number) => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  children,
  currentModel,
  onModelChange,
  inputValue,
  onInputChange,
  onSend,
  onFileUpload,
  onKeyPress,
  isInputDisabled = false,
  uploadedFiles = [],
  onRemoveFile
}) => {
  const { state: sidebarState } = useSidebar();
  const isSidebarCollapsed = sidebarState === "collapsed";

  return (
    <div className={`flex-1 flex flex-col h-screen overflow-hidden transition-all duration-300 ${isSidebarCollapsed ? 'pl-0' : 'pl-0 md:pl-80'}`}>
      {/* Fixed Navbar */}
      <div className={`flex items-center h-12 sm:h-14 border-b border-gray-800 glassmorphism-navbar fixed top-0 right-0 z-40 transition-all duration-300 ${isSidebarCollapsed ? 'left-0' : 'left-0 md:left-80'}`}>
        {/* Show sidebar trigger only when sidebar is collapsed */}
        {isSidebarCollapsed && (
          <div className="flex items-center pl-4 pr-2">
            <SidebarTrigger className="p-2 rounded-md hover:bg-gray-800 text-gray-400 hover:text-gray-100 transition-colors">
              <Menu className="h-4 w-4" />
            </SidebarTrigger>
          </div>
        )}
        <div className="flex-1 px-2 sm:px-4">
          <TopNavigation 
            currentModel={currentModel}
            onModelChange={onModelChange}
          />
        </div>
      </div>

      {/* Content Area - Full height with padding for fixed elements */}
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-screen">
          <div className={`px-2 sm:px-4 pt-16 pb-32 max-w-5xl mx-auto`}>
            {children}
          </div>
        </ScrollArea>
      </div>

      {/* Fixed Chat Input Area */}
      <div className={`border-t border-gray-800 glassmorphism-input fixed bottom-0 right-0 z-40 p-3 sm:p-4 transition-all duration-300 ${isSidebarCollapsed ? 'left-0' : 'left-0 md:left-80'}`}>
        <div className="max-w-5xl mx-auto space-y-2">
          {/* File Chips */}
          {uploadedFiles.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {uploadedFiles.map((file, index) => (
                <FileChip
                  key={index}
                  file={file}
                  onRemove={() => onRemoveFile && onRemoveFile(index)}
                />
              ))}
            </div>
          )}
          
          <ChatInput
            value={inputValue}
            onChange={onInputChange}
            onSend={onSend}
            onFileUpload={onFileUpload}
            onKeyPress={onKeyPress}
            isDisabled={isInputDisabled}
          />
        </div>
      </div>
    </div>
  );
};
