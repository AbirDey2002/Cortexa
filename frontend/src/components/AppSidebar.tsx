import { useEffect, useState, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
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
import { useApi } from "@/lib/utils";
import { SlidingName } from "@/components/chat/SlidingName";

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
  const { apiGet, apiPost } = useApi();
  
  // Reference to track if we need to apply animation
  const animatingItemRef = useRef<string | null>(null);
  
  // Track naming state for both Stage 1 (conversation-based) and Stage 2 (document-based)
  const namingStateRef = useRef<Map<string, {
    // Stage 1 (conversation-based)
    stage1: {
      initialName: string;
      isPolling: boolean;
      startTime: number;
    } | null;
    // Stage 2 (document-based)
    stage2: {
      initialName: string;
      textExtractionCompleted: boolean;
      isPolling: boolean;
      startTime: number;
    } | null;
  }>>(new Map());
  
  // Separate interval refs for Stage 1 and Stage 2 polling
  const stage1PollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const stage2PollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Function to fetch and update usecases
  const fetchUsecases = useCallback(async () => {
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
    }
  }, [userId, activeUsecaseId, apiGet]);
  
  // Initial fetch on mount and when userId/activeUsecaseId changes
  useEffect(() => {
    fetchUsecases();
  }, [fetchUsecases]);
  
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

  // Stage 1: Poll for conversation-based naming (when name is still "Chat X")
  useEffect(() => {
    if (!activeUsecaseId || !userId) {
      // Clean up Stage 1 polling if no active use case
      if (stage1PollIntervalRef.current) {
        clearInterval(stage1PollIntervalRef.current);
        stage1PollIntervalRef.current = null;
      }
      return;
    }

    // Clean up any existing Stage 1 polling
    if (stage1PollIntervalRef.current) {
      clearInterval(stage1PollIntervalRef.current);
      stage1PollIntervalRef.current = null;
    }

    const usecase = usecases.find(u => u.usecase_id === activeUsecaseId);
    if (!usecase) return;

    // Check if name is still default "Chat X"
    const isDefaultName = usecase.usecase_name.startsWith("Chat ");

    if (isDefaultName) {
      // Initialize Stage 1 state if not exists
      const currentState = namingStateRef.current.get(activeUsecaseId);
      if (!currentState || !currentState.stage1) {
        if (!currentState) {
          namingStateRef.current.set(activeUsecaseId, {
            stage1: {
              initialName: usecase.usecase_name,
              isPolling: false,
              startTime: Date.now(),
            },
            stage2: null,
          });
        } else {
          namingStateRef.current.set(activeUsecaseId, {
            ...currentState,
            stage1: {
              initialName: usecase.usecase_name,
              isPolling: false,
              startTime: Date.now(),
            },
          });
        }
      }

      // Start Stage 1 polling if not already polling
      if (!stage1PollIntervalRef.current) {
        let pollCount = 0;
        const MAX_POLL_ATTEMPTS = 15; // 30 seconds max (15 * 2s) - conversation naming is faster

        stage1PollIntervalRef.current = setInterval(async () => {
          pollCount++;

          // Stop polling after max attempts
          if (pollCount > MAX_POLL_ATTEMPTS) {
            if (stage1PollIntervalRef.current) {
              clearInterval(stage1PollIntervalRef.current);
              stage1PollIntervalRef.current = null;
            }
            // Clean up Stage 1 state after timeout
            const state = namingStateRef.current.get(activeUsecaseId);
            if (state) {
              namingStateRef.current.set(activeUsecaseId, {
                ...state,
                stage1: null,
              });
            }
            return;
          }

          try {
            // Fetch updated use cases
            const updatedUsecases = await apiGet<UsecaseListItem[]>(`/frontend/usecases/list`);
            const updatedUsecase = updatedUsecases.find(u => u.usecase_id === activeUsecaseId);

            if (updatedUsecase) {
              const currentState = namingStateRef.current.get(activeUsecaseId);
              const stage1State = currentState?.stage1;

              // Check if name changed from "Chat X" (Stage 1 naming completed)
              if (stage1State && !updatedUsecase.usecase_name.startsWith("Chat ")) {
                // Name changed - Stage 1 naming completed
                setUsecases(prev => prev.map(u =>
                  u.usecase_id === activeUsecaseId
                    ? { ...u, usecase_name: updatedUsecase.usecase_name }
                    : u
                ));

                // Stop polling
                if (stage1PollIntervalRef.current) {
                  clearInterval(stage1PollIntervalRef.current);
                  stage1PollIntervalRef.current = null;
                }

                // Clean up Stage 1 state
                if (currentState) {
                  namingStateRef.current.set(activeUsecaseId, {
                    ...currentState,
                    stage1: null,
                  });
                }
                return;
              }

              // Update use cases list (in case other use cases changed)
              setUsecases(prev => {
                const nameChanged = prev.some((p) => {
                  const updated = updatedUsecases.find(u => u.usecase_id === p.usecase_id);
                  return updated && updated.usecase_name !== p.usecase_name;
                });

                if (nameChanged) {
                  return prev.map(p => {
                    const updated = updatedUsecases.find(u => u.usecase_id === p.usecase_id);
                    if (updated && updated.usecase_name !== p.usecase_name) {
                      return { ...p, usecase_name: updated.usecase_name };
                    }
                    return p;
                  });
                }
                return prev;
              });
            }
          } catch (e) {
            // Continue polling on error
          }
        }, 2000); // Poll every 2 seconds
      }
    } else {
      // Name already changed, stop Stage 1 polling if running
      if (stage1PollIntervalRef.current) {
        clearInterval(stage1PollIntervalRef.current);
        stage1PollIntervalRef.current = null;
      }
      // Clean up Stage 1 state
      const state = namingStateRef.current.get(activeUsecaseId);
      if (state && state.stage1) {
        namingStateRef.current.set(activeUsecaseId, {
          ...state,
          stage1: null,
        });
      }
    }

    // Cleanup function
    return () => {
      if (stage1PollIntervalRef.current) {
        clearInterval(stage1PollIntervalRef.current);
        stage1PollIntervalRef.current = null;
      }
    };
  }, [activeUsecaseId, userId, usecases, apiGet]);

  // Stage 2: Poll for document-based naming (when text extraction is completed)
  useEffect(() => {
    if (!activeUsecaseId || !userId) {
      // Clean up Stage 2 polling if no active use case
      if (stage2PollIntervalRef.current) {
        clearInterval(stage2PollIntervalRef.current);
        stage2PollIntervalRef.current = null;
      }
      return;
    }

    // Clean up any existing Stage 2 polling
    if (stage2PollIntervalRef.current) {
      clearInterval(stage2PollIntervalRef.current);
      stage2PollIntervalRef.current = null;
    }

    // Top-level check: If name has already changed from initialName, stop polling
    // This is similar to Stage 1's top-level check
    const usecase = usecases.find(u => u.usecase_id === activeUsecaseId);
    if (usecase) {
      const currentState = namingStateRef.current.get(activeUsecaseId);
      const stage2State = currentState?.stage2;
      
      // If we have Stage 2 state and the name has changed from initialName, stop polling
      if (stage2State && usecase.usecase_name !== stage2State.initialName) {
        // Name already changed - stop polling and clean up
        if (stage2PollIntervalRef.current) {
          clearInterval(stage2PollIntervalRef.current);
          stage2PollIntervalRef.current = null;
        }
        // Clean up Stage 2 state
        if (currentState) {
          namingStateRef.current.set(activeUsecaseId, {
            ...currentState,
            stage2: null,
          });
        }
        return;
      }
    }

    let pollCount = 0;
    const MAX_POLL_ATTEMPTS = 30; // 60 seconds max (30 * 2s)

    const checkAndStartPolling = async () => {
      try {
        // Check if this use case exists in our list
        const usecase = usecases.find(u => u.usecase_id === activeUsecaseId);
        if (!usecase) return;

        // Check text extraction status
        const status = await apiGet<{
          text_extraction: string;
          status: string;
        }>(`/frontend/usecases/${activeUsecaseId}/statuses`);

        // Only poll if text_extraction is "Completed" (documents were uploaded)
        if (status.text_extraction === "Completed") {
          // Get or initialize state
          const currentState = namingStateRef.current.get(activeUsecaseId);
          const stage2State = currentState?.stage2;

          // Initialize Stage 2 state if not exists or text extraction just completed
          if (!stage2State || !stage2State.textExtractionCompleted) {
            const newState = {
              initialName: usecase.usecase_name, // Store current name when Stage 2 polling starts
              textExtractionCompleted: true,
              isPolling: false,
              startTime: Date.now(),
            };

            if (!currentState) {
              namingStateRef.current.set(activeUsecaseId, {
                stage1: null,
                stage2: newState,
              });
            } else {
              namingStateRef.current.set(activeUsecaseId, {
                ...currentState,
                stage2: newState,
              });
            }
          }

          const updatedState = namingStateRef.current.get(activeUsecaseId);
          const finalStage2State = updatedState?.stage2;
          if (!finalStage2State) return;

          // Double-check: If name has already changed, don't start polling
          if (finalStage2State && usecase.usecase_name !== finalStage2State.initialName) {
            // Name already changed - clean up and return
            if (currentState) {
              namingStateRef.current.set(activeUsecaseId, {
                ...currentState,
                stage2: null,
              });
            }
            return;
          }

          // Start polling if not already polling
          if (!stage2PollIntervalRef.current) {
            pollCount = 0; // Reset poll count for new polling session
            // Store the initial name in a closure to ensure we always have the correct reference
            const storedInitialName = finalStage2State.initialName;
            
            stage2PollIntervalRef.current = setInterval(async () => {
              // First check: Verify we still have state and should be polling
              // Also check if interval ref still exists (might have been cleared)
              if (!stage2PollIntervalRef.current) {
                return;
              }
              
              const currentState = namingStateRef.current.get(activeUsecaseId);
              const stage2State = currentState?.stage2;
              
              // If state was cleaned up, stop immediately
              if (!stage2State) {
                if (stage2PollIntervalRef.current) {
                  clearInterval(stage2PollIntervalRef.current);
                  stage2PollIntervalRef.current = null;
                }
                return;
              }

              pollCount++;

              // Stop polling after max attempts
              if (pollCount > MAX_POLL_ATTEMPTS) {
                if (stage2PollIntervalRef.current) {
                  clearInterval(stage2PollIntervalRef.current);
                  stage2PollIntervalRef.current = null;
                }
                // Clean up Stage 2 state after timeout
                const state = namingStateRef.current.get(activeUsecaseId);
                if (state) {
                  namingStateRef.current.set(activeUsecaseId, {
                    ...state,
                    stage2: null,
                  });
                }
                return;
              }

              try {
                // Fetch updated use cases
                const updatedUsecases = await apiGet<UsecaseListItem[]>(`/frontend/usecases/list`);
                const updatedUsecase = updatedUsecases.find(u => u.usecase_id === activeUsecaseId);

                if (updatedUsecase) {
                  // Check if name changed from the name stored when Stage 2 polling started
                  // Use both the stored initialName and current state for comparison
                  const nameChanged = updatedUsecase.usecase_name !== storedInitialName;
                  
                  if (nameChanged) {
                    // Name changed - Stage 2 naming completed
                    // CRITICAL: Stop polling and clean up state BEFORE updating usecases
                    // This prevents useEffect from re-running and restarting polling
                    
                    // Stop polling immediately - clear interval first
                    const intervalId = stage2PollIntervalRef.current;
                    if (intervalId) {
                      clearInterval(intervalId);
                      stage2PollIntervalRef.current = null;
                    }

                    // Clean up Stage 2 state BEFORE setUsecases triggers useEffect re-run
                    const finalState = namingStateRef.current.get(activeUsecaseId);
                    if (finalState) {
                      namingStateRef.current.set(activeUsecaseId, {
                        ...finalState,
                        stage2: null,
                      });
                    }
                    
                    // Now update usecases - this will trigger useEffect re-run, but state is already cleaned up
                    setUsecases(prev => prev.map(u =>
                      u.usecase_id === activeUsecaseId
                        ? { ...u, usecase_name: updatedUsecase.usecase_name }
                        : u
                    ));
                    
                    return;
                  }

                  // Update use cases list (in case other use cases changed)
                  setUsecases(prev => {
                    const nameChanged = prev.some((p) => {
                      const updated = updatedUsecases.find(u => u.usecase_id === p.usecase_id);
                      return updated && updated.usecase_name !== p.usecase_name;
                    });

                    if (nameChanged) {
                      return prev.map(p => {
                        const updated = updatedUsecases.find(u => u.usecase_id === p.usecase_id);
                        if (updated && updated.usecase_name !== p.usecase_name) {
                          return { ...p, usecase_name: updated.usecase_name };
                        }
                        return p;
                      });
                    }
                    return prev;
                  });
                }
              } catch (e) {
                // Continue polling on error
              }
            }, 2000); // Poll every 2 seconds
          }
        } else {
          // Text extraction not completed, no need to poll
          // Clean up Stage 2 state if exists
          const state = namingStateRef.current.get(activeUsecaseId);
          if (state && state.stage2) {
            namingStateRef.current.set(activeUsecaseId, {
              ...state,
              stage2: null,
            });
          }
          // Stop polling if it was running
          if (stage2PollIntervalRef.current) {
            clearInterval(stage2PollIntervalRef.current);
            stage2PollIntervalRef.current = null;
          }
        }
      } catch (e) {
        // Silently fail - will retry when use case changes
      }
    };

    // Initial check
    checkAndStartPolling();

    // Cleanup function
    return () => {
      if (stage2PollIntervalRef.current) {
        clearInterval(stage2PollIntervalRef.current);
        stage2PollIntervalRef.current = null;
      }
    };
  }, [activeUsecaseId, userId, usecases, apiGet]);

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
                            <p className="max-w-xs break-words">{chat.usecase_name}</p>
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
                            <div className="flex-1 min-w-0 ml-3 overflow-hidden">
                              <SlidingName
                                name={chat.usecase_name}
                                maxChars={30}
                                className="text-sm font-medium"
                              />
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
                      <SidebarMenuButton 
                        asChild
                        className="hover:bg-sidebar-accent text-sidebar-foreground p-2 rounded-lg transition-colors justify-center"
                      >
                        <Link to={`/user/${userId}/settings`}>
                          <Settings className="h-4 w-4" />
                        </Link>
                      </SidebarMenuButton>
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      <p>Settings</p>
                    </TooltipContent>
                  </Tooltip>
                ) : (
                  <SidebarMenuButton 
                    asChild
                    className="hover:bg-sidebar-accent text-sidebar-foreground p-3 rounded-lg transition-colors"
                  >
                    <Link to={`/user/${userId}/settings`}>
                      <Settings className="h-4 w-4" />
                      <span className="ml-3">Settings</span>
                    </Link>
                  </SidebarMenuButton>
                )}
              </SidebarMenuItem>
              <SidebarMenuItem>
                {isCollapsed ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <SidebarMenuButton 
                        asChild
                        className="hover:bg-sidebar-accent text-sidebar-foreground p-2 rounded-lg transition-colors justify-center"
                      >
                        <Link to={`/user/${userId}/help`}>
                          <HelpCircle className="h-4 w-4" />
                        </Link>
                      </SidebarMenuButton>
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      <p>Help</p>
                    </TooltipContent>
                  </Tooltip>
                ) : (
                  <SidebarMenuButton 
                    asChild
                    className="hover:bg-sidebar-accent text-sidebar-foreground p-3 rounded-lg transition-colors"
                  >
                    <Link to={`/user/${userId}/help`}>
                      <HelpCircle className="h-4 w-4" />
                      <span className="ml-3">Help</span>
                    </Link>
                  </SidebarMenuButton>
                )}
              </SidebarMenuItem>
            </SidebarMenu>
          </div>
        </SidebarContent>
    </TooltipProvider>
  );
}