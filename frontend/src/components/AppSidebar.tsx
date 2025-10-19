import { useEffect, useState, useRef } from "react";
import { Plus, MessageSquare, Settings, HelpCircle, Menu } from "lucide-react";
import {
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { apiGet, apiPost } from "@/lib/utils";

type UsecaseListItem = {
  usecase_id: string;
  user_id: string;
  usecase_name: string;
  status: string;
  updated_at?: string | null;
  created_at?: string | null;
};

interface Props {
  userId: string;
  activeUsecaseId: string | null;
  onSelectUsecase: (id: string) => void;
  onNewUsecase: (id: string) => void;
}

export function AppSidebar({ userId, activeUsecaseId, onSelectUsecase, onNewUsecase }: Props) {
  const { state } = useSidebar();
  const [selectedChat, setSelectedChat] = useState<string | null>(activeUsecaseId);
  const [usecases, setUsecases] = useState<UsecaseListItem[]>([]);
  const isCollapsed = state === "collapsed";
  
  // Reference to track if we need to apply animation
  const animatingItemRef = useRef<string | null>(null);

  // Function to fetch and update usecases
  const fetchUsecases = async () => {
    if (!userId) return;
    try {
      const usecases = await apiGet<UsecaseListItem[]>(`/frontend/usecases/list`);
      
      // Sort usecases by updated_at timestamp (most recent first)
      const sortedUsecases = [...usecases].sort((a, b) => {
        const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
        const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
        return dateB - dateA; // Descending order (newest first)
      });
      
      // Check if the active usecase has moved position (for animation)
      if (activeUsecaseId) {
        const oldIndex = usecases.findIndex(u => u.usecase_id === activeUsecaseId);
        const newIndex = sortedUsecases.findIndex(u => u.usecase_id === activeUsecaseId);
        if (oldIndex !== newIndex && oldIndex !== -1) {
          animatingItemRef.current = activeUsecaseId;
        }
      }
      
      setUsecases(sortedUsecases);
      
      // Update selected chat if activeUsecaseId changes
      if (activeUsecaseId && sortedUsecases.some(u => u.usecase_id === activeUsecaseId)) {
        setSelectedChat(activeUsecaseId);
      }
    } catch (e) {
      console.error("Error fetching usecases:", e);
    }
  };
  
  // Initial fetch on mount and when userId/activeUsecaseId changes
  useEffect(() => {
    fetchUsecases();
  }, [userId, activeUsecaseId]);
  
  // Listen for chat updates to refresh the sidebar
  useEffect(() => {
    const handleChatUpdate = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail && customEvent.detail.usecaseId) {
        // Update the specific usecase to the top of the list immediately
        // This happens on user input, not waiting for system response
        setUsecases(prevUsecases => {
          const usecaseId = customEvent.detail.usecaseId;
          const usecase = prevUsecases.find(u => u.usecase_id === usecaseId);
          
          if (usecase) {
            // Create a copy of the usecase with updated timestamp
            const updatedUsecase = {
              ...usecase,
              updated_at: new Date().toISOString()
            };
            
            // Remove the usecase from the list and add it to the top
            const filteredUsecases = prevUsecases.filter(u => u.usecase_id !== usecaseId);
            animatingItemRef.current = usecaseId; // Set for animation
            
            // Return the updated list with the usecase at the top
            return [updatedUsecase, ...filteredUsecases];
          }
          
          return prevUsecases;
        });
      }
    };
    
    window.addEventListener('chat-updated', handleChatUpdate);
    return () => {
      window.removeEventListener('chat-updated', handleChatUpdate);
    };
  }, [userId]);

  const handleNewChat = async () => {
    setSelectedChat(null);
    try {
      // Get the current count of chats to name this one appropriately
      const chatCount = usecases.length + 1;
      const chatName = `Chat ${chatCount}`;
      
      const payload = { user_id: userId, usecase_name: chatName, email: "abir.dey@intellectdesign.com" };
      const record = await apiPost<UsecaseListItem>("/usecases", payload);
      
      // Refresh the list of usecases after creating a new one
      const updatedUsecases = await apiGet<UsecaseListItem[]>(`/frontend/usecases/list`);
      setUsecases(updatedUsecases);
      
      // Select the new usecase
      setSelectedChat(record.usecase_id);
      onNewUsecase(record.usecase_id);
    } catch (e) {
      console.error("Error creating new chat:", e);
    }
  };

  const handleChatSelect = (chatId: string) => {
    setSelectedChat(chatId);
    onSelectUsecase(chatId);
  };

  return (
    <TooltipProvider>
      <SidebarContent className="p-2 xs:p-3 sm:p-4 flex flex-col h-full">
          {/* Header with toggle and new chat */}
          <div className="flex items-center justify-between mb-3 sm:mb-6">
            {!isCollapsed && (
              <h2 className="text-base sm:text-lg font-bold text-sidebar-foreground truncate">Cortexa</h2>
            )}
            <SidebarTrigger className="p-1 sm:p-2 hover:bg-sidebar-accent rounded-md sm:rounded-lg transition-colors">
              <Menu className="h-4 w-4" />
            </SidebarTrigger>
          </div>

          {/* New Chat Button */}
          <div className="mb-2">
            {isCollapsed ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    onClick={handleNewChat}
                    variant="ghost"
                    size="sm"
                    className="w-full text-white hover:text-glow border-0 px-2 transition-all duration-200"
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">
                  <p>New Chat</p>
                </TooltipContent>
              </Tooltip>
            ) : (
              <Button
                onClick={handleNewChat}
                variant="ghost"
                size="default"
                className="w-full text-white hover:text-glow border-0 px-4 transition-all duration-200"
              >
                <Plus className="h-4 w-4" />
                <span className="ml-2">New Chat</span>
              </Button>
            )}
          </div>
          
          {/* Separator with line and text */}
          {!isCollapsed && (
            <div className="flex items-center mb-4 mt-2">
              <div className="flex-grow h-px bg-sidebar-border"></div>
            </div>
          )}

          {/* Recent Chats - Now with flex-grow to take available space */}
          <SidebarGroup className="flex-grow overflow-hidden flex flex-col min-h-0">
            {!isCollapsed && (
              <SidebarGroupLabel className="text-sidebar-foreground/70 text-sm font-medium mb-3">
                Recent
              </SidebarGroupLabel>
            )}
            <SidebarGroupContent className="flex-grow overflow-hidden">
              <ScrollArea className="h-full">
                <SidebarMenu className="space-y-1">
                  {usecases.map((chat) => (
                    <SidebarMenuItem key={chat.usecase_id}>
                      {isCollapsed ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <SidebarMenuButton
                              asChild
                              className={`w-full p-2 rounded-lg transition-all cursor-pointer justify-center ${
                                selectedChat === chat.usecase_id
                                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                                  : "hover:bg-sidebar-accent/50 text-sidebar-foreground"
                              }`}
                            >
                              <div onClick={() => handleChatSelect(chat.usecase_id)}>
                                <MessageSquare className="h-4 w-4" />
                              </div>
                            </SidebarMenuButton>
                          </TooltipTrigger>
                          <TooltipContent side="right">
                            <p className="max-w-xs">{chat.usecase_name}</p>
                          </TooltipContent>
                        </Tooltip>
                      ) : (
                        <SidebarMenuButton
                          asChild
                          className={`w-full p-4 rounded-lg transition-all cursor-pointer ${
                            selectedChat === chat.usecase_id
                              ? "bg-sidebar-accent text-sidebar-accent-foreground"
                              : "hover:bg-sidebar-accent/50 text-sidebar-foreground"
                          } ${
                            animatingItemRef.current === chat.usecase_id ? "animate-slide-up" : ""
                          }`}
                        >
                          <div 
                            onClick={() => handleChatSelect(chat.usecase_id)} 
                            className="flex items-center"
                            onAnimationEnd={() => {
                              if (animatingItemRef.current === chat.usecase_id) {
                                animatingItemRef.current = null;
                              }
                            }}
                          >
                            <MessageSquare className="h-4 w-4 flex-shrink-0" />
                            <div className="flex-1 min-w-0 ml-3">
                              <p className="text-sm font-medium truncate">
                                {chat.usecase_name}
                              </p>
                            </div>
                          </div>
                        </SidebarMenuButton>
                      )}
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </ScrollArea>
            </SidebarGroupContent>
          </SidebarGroup>

          {/* Settings & Help - Bottom Section - Now fixed at bottom */}
          <div className="pt-4 mt-2">
            <SidebarMenu className="space-y-1">
              <SidebarMenuItem>
                {isCollapsed ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <SidebarMenuButton className="hover:bg-sidebar-accent text-sidebar-foreground p-2 rounded-lg transition-colors justify-center">
                        <Settings className="h-4 w-4" />
                      </SidebarMenuButton>
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      <p>Settings</p>
                    </TooltipContent>
                  </Tooltip>
                ) : (
                  <SidebarMenuButton className="hover:bg-sidebar-accent text-sidebar-foreground p-3 rounded-lg transition-colors">
                    <Settings className="h-4 w-4" />
                    <span className="ml-3">Settings</span>
                  </SidebarMenuButton>
                )}
              </SidebarMenuItem>
              <SidebarMenuItem>
                {isCollapsed ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <SidebarMenuButton className="hover:bg-sidebar-accent text-sidebar-foreground p-2 rounded-lg transition-colors justify-center">
                        <HelpCircle className="h-4 w-4" />
                      </SidebarMenuButton>
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      <p>Help</p>
                    </TooltipContent>
                  </Tooltip>
                ) : (
                  <SidebarMenuButton className="hover:bg-sidebar-accent text-sidebar-foreground p-3 rounded-lg transition-colors">
                    <HelpCircle className="h-4 w-4" />
                    <span className="ml-3">Help</span>
                  </SidebarMenuButton>
                )}
              </SidebarMenuItem>
            </SidebarMenu>
          </div>
        </SidebarContent>
    </TooltipProvider>
  );
}