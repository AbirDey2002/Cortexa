import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, User, Settings, BarChart3, LogOut } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useSidebar } from "@/components/ui/sidebar";
import { useAuth } from "@/contexts/AuthContext";
import { apiGet } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

interface TopNavigationProps {
  currentModel: string;
  onModelChange: (model: string) => void;
}

interface Model {
  id: string;
  name: string;
  description: string;
}

export function TopNavigation({ currentModel, onModelChange }: TopNavigationProps) {
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [availableModels, setAvailableModels] = useState<Model[]>([]);
  const { state: sidebarState } = useSidebar();
  const isSidebarCollapsed = sidebarState === "collapsed";
  const { logout, user, userId } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleLogout = () => {
    logout();
    toast({
      title: "Logged out",
      description: "You have been successfully logged out.",
    });
    navigate("/");
  };

  // Fetch models from backend
  useEffect(() => {
    async function fetchModels() {
      try {
        const response = await apiGet<{ models: Model[] }>("/api/v1/models");
        if (response?.models) {
          setAvailableModels(response.models);
        }
      } catch (error) {
        // Fallback to default models if API fails
        setAvailableModels([
          { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash", description: "Fast and efficient model" },
        ]);
      }
    }
    fetchModels();
  }, []);

  return (
    <div className="flex-1 transition-all duration-300">
      <div className={`flex items-center justify-between h-full`}>
        {/* Left Side - Model Selector (hidden on desktop when sidebar expanded) */}
        <div className="inline-flex md:peer-data-[state=expanded]:hidden">
          <DropdownMenu open={isModelDropdownOpen} onOpenChange={setIsModelDropdownOpen}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="text-foreground hover:bg-accent hover:text-accent-foreground px-2 sm:px-3 py-2 h-8 sm:h-9 text-xs sm:text-sm md:text-base"
              >
                <span className="font-medium">
                  {availableModels.find(m => m.id === currentModel)?.name || currentModel}
                </span>
                <ChevronDown className="ml-2 h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-64 bg-popover border-border">
              <DropdownMenuLabel className="text-popover-foreground">
                Select Model
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {availableModels.map((model) => (
                <DropdownMenuItem
                  key={model.id}
                  onClick={() => {
                    onModelChange(model.id);
                    setIsModelDropdownOpen(false);
                  }}
                  className={`cursor-pointer ${
                    currentModel === model.id
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-accent hover:text-accent-foreground"
                  }`}
                >
                  <div>
                    <div className="font-medium">{model.name}</div>
                    <div className="text-sm text-muted-foreground">{model.description}</div>
                  </div>
                </DropdownMenuItem>
              ))}
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
    </div>
  );
}