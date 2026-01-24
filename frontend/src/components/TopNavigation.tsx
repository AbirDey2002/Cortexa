import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, User, Settings, BarChart3, LogOut, Key, Sparkles } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuGroup,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { useSidebar } from "@/components/ui/sidebar";
import { useAuth } from "@/contexts/AuthContext";
import { useApi } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

interface TopNavigationProps {
  currentModel: string;
  onModelChange: (model: string) => void;
}

interface AvailableModel {
  provider_id: string;
  provider_name: string;
  model_id: string;
  model_name: string;
  description: string;
  context_window: number;
  is_default: boolean;
  key_source: string; // 'user' or 'system'
}

export function TopNavigation({ currentModel, onModelChange }: TopNavigationProps) {
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(true);
  const { state: sidebarState } = useSidebar();
  const isSidebarCollapsed = sidebarState === "collapsed";
  const { logout, user, userId } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { apiGet } = useApi();

  const handleLogout = () => {
    logout();
    toast({
      title: "Logged out",
      description: "You have been successfully logged out.",
    });
    navigate("/");
  };

  // Fetch available models from BYOK endpoint (only when authenticated)
  useEffect(() => {
    // Only fetch if user is authenticated
    if (!userId) {
      setIsLoadingModels(false);
      return;
    }

    async function fetchModels() {
      setIsLoadingModels(true);
      try {
        const response = await apiGet<{ models: AvailableModel[] }>("/api-keys/available-models");
        setAvailableModels(response?.models || []);
      } catch (error) {
        console.error("Failed to fetch models:", error);
        setAvailableModels([]);
      } finally {
        setIsLoadingModels(false);
      }
    }
    fetchModels();
  }, [userId, apiGet]);

  // Group models by provider
  const modelsByProvider = availableModels.reduce((acc, model) => {
    if (!acc[model.provider_id]) {
      acc[model.provider_id] = {
        provider_name: model.provider_name,
        models: []
      };
    }
    acc[model.provider_id].models.push(model);
    return acc;
  }, {} as Record<string, { provider_name: string; models: AvailableModel[] }>);

  // Find current model info
  const currentModelInfo = availableModels.find(m => m.model_id === currentModel);
  const hasNoModels = availableModels.length === 0 && !isLoadingModels;
  const displayName = hasNoModels ? "Configure API Key" : (currentModelInfo?.model_name || currentModel.split('/').pop() || currentModel);

  return (
    <div className="flex-1 transition-all duration-300">
      <div className={`flex items-center justify-between h-full`}>
        {/* Left Side - Model Selector */}
        <div className="inline-flex md:peer-data-[state=expanded]:hidden">
          <DropdownMenu open={isModelDropdownOpen} onOpenChange={setIsModelDropdownOpen}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="text-foreground hover:bg-accent hover:text-accent-foreground px-2 sm:px-3 py-2 h-8 sm:h-9 text-xs sm:text-sm md:text-base font-normal"
              >
                <span className="mr-1">{displayName}</span>
                <ChevronDown className="h-4 w-4 opacity-50" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-80 bg-popover border-border max-h-96 overflow-y-auto">
              <DropdownMenuLabel className="text-popover-foreground flex items-center justify-between">
                <span>Select Model</span>
                {isLoadingModels && <span className="text-xs text-muted-foreground">Loading...</span>}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />

              {hasNoModels ? (
                <div className="py-6 px-4 text-center">
                  <Key className="w-8 h-8 mx-auto mb-3 text-muted-foreground/50" />
                  <p className="text-sm font-medium text-foreground mb-1">No API Keys Configured</p>
                  <p className="text-xs text-muted-foreground mb-3">
                    Add your API keys to use LLM models
                  </p>
                  <DropdownMenuItem
                    className="cursor-pointer justify-center bg-primary text-primary-foreground hover:bg-primary/90"
                    onClick={() => userId && navigate(`/user/${userId}/settings`)}
                  >
                    <Key className="w-3 h-3 mr-2" />
                    Configure API Keys
                  </DropdownMenuItem>
                </div>
              ) : (
                <>
                  {Object.entries(modelsByProvider).map(([providerId, { provider_name, models }]) => (
                    <DropdownMenuGroup key={providerId}>
                      <div className="flex flex-row items-center justify-start px-2 py-2 bg-muted/30">
                        {/* Provider Logo */}
                        {providerId === 'openai' && (
                          <img src="/openai.png" alt="OpenAI" className="w-5 h-5 mr-2 object-contain" />
                        )}
                        {providerId === 'gemini' && (
                          <img src="/gemini.png" alt="Gemini" className="w-5 h-5 mr-2 object-contain" />
                        )}
                        {providerId === 'claude' && (
                          <img src="/claude.png" alt="Claude" className="w-5 h-5 mr-2 object-contain" />
                        )}
                        {providerId === 'grok' && (
                          <img src="/grok.png" alt="Grok" className="w-5 h-5 mr-2 object-contain" />
                        )}
                        {providerId === 'deepseek' && (
                          <img src="/deepseek.png" alt="DeepSeek" className="w-5 h-5 mr-2 object-contain" />
                        )}
                        {providerId === 'huggingface' && (
                          <img src="/huggingface.png" alt="HuggingFace" className="w-5 h-5 mr-2 object-contain" />
                        )}
                        <DropdownMenuLabel className="text-xs font-semibold text-muted-foreground uppercase tracking-wide py-0 px-0">
                          {provider_name}
                        </DropdownMenuLabel>
                      </div>

                      {
                        models.map((model) => (
                          <DropdownMenuItem
                            key={model.model_id}
                            onClick={() => {
                              onModelChange(model.model_id);
                              setIsModelDropdownOpen(false);
                            }}
                            className={`cursor-pointer justify-start pl-4 py-2 ${currentModel === model.model_id
                              ? "bg-accent/50 text-accent-foreground font-medium"
                              : "hover:bg-accent/30 text-muted-foreground"
                              }`}
                          >
                            {model.model_name}
                          </DropdownMenuItem>
                        ))
                      }
                    </DropdownMenuGroup>
                  ))}

                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="cursor-pointer text-xs text-muted-foreground"
                    onClick={() => userId && navigate(`/user/${userId}/settings`)}
                  >
                    <Key className="w-3 h-3 mr-2" />
                    Manage API Keys...
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Right Side - User Account */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="relative h-7 w-7 sm:h-8 sm:w-8 md:h-9 md:w-9 rounded-full">
              <Avatar className="h-7 w-7 sm:h-8 sm:w-8 md:h-9 md:w-9">
                <AvatarImage src={user?.picture} alt={user?.name || "User"} />
                <AvatarFallback className="bg-primary text-primary-foreground text-xs sm:text-sm md:text-base">
                  {user?.name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || "U"}
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 bg-popover border-border">
            <DropdownMenuLabel
              className="text-popover-foreground cursor-pointer hover:bg-accent/50 rounded-sm p-2 -mx-2 -my-1 transition-colors"
              onClick={() => userId && navigate(`/user/${userId}/profile`)}
            >
              <div className="flex flex-col space-y-1">
                <p className="text-sm font-medium">{user?.name || "User"}</p>
                <p className="text-xs text-muted-foreground">{user?.email || ""}</p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer hover:bg-accent hover:text-accent-foreground"
              onClick={() => userId && navigate(`/user/${userId}/profile`)}
            >
              <User className="mr-2 h-4 w-4" />
              <span>Profile</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="cursor-pointer hover:bg-accent hover:text-accent-foreground"
              onClick={() => userId && navigate(`/user/${userId}/usage`)}
            >
              <BarChart3 className="mr-2 h-4 w-4" />
              <span>Usage</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="cursor-pointer hover:bg-accent hover:text-accent-foreground"
              onClick={() => userId && navigate(`/user/${userId}/settings`)}
            >
              <Settings className="mr-2 h-4 w-4" />
              <span>Settings</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer hover:bg-accent hover:text-accent-foreground text-destructive"
              onClick={handleLogout}
            >
              <LogOut className="mr-2 h-4 w-4" />
              <span>Logout</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div >
  );
}