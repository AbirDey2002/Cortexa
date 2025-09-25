import { useState } from "react";
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

interface TopNavigationProps {
  currentModel: string;
  onModelChange: (model: string) => void;
}

const availableModels = [
  { id: "cortexa-4-pro", name: "Cortexa-4 Pro", description: "Most capable model" },
  { id: "cortexa-3.5-turbo", name: "Cortexa-3.5 Turbo", description: "Balanced performance" },
  { id: "legacy-model", name: "Legacy Model", description: "Previous generation" },
];

export function TopNavigation({ currentModel, onModelChange }: TopNavigationProps) {
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const { state: sidebarState } = useSidebar();
  const isSidebarCollapsed = sidebarState === "collapsed";

  return (
    <div className="flex-1 transition-all duration-300">
      <div className={`flex items-center justify-between h-full ${!isSidebarCollapsed ? 'pl-4' : ''}`}>
        {/* Left Side - Model Selector */}
        <DropdownMenu open={isModelDropdownOpen} onOpenChange={setIsModelDropdownOpen}>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              className="text-foreground hover:bg-accent hover:text-accent-foreground px-2 sm:px-3 py-2 h-8 sm:h-9 text-xs sm:text-sm md:text-base"
            >
              <span className="font-medium">{currentModel}</span>
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
                  onModelChange(model.name);
                  setIsModelDropdownOpen(false);
                }}
                className={`cursor-pointer ${
                  currentModel === model.name
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

        {/* Right Side - User Account */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="relative h-7 w-7 sm:h-8 sm:w-8 md:h-9 md:w-9 rounded-full">
              <Avatar className="h-7 w-7 sm:h-8 sm:w-8 md:h-9 md:w-9">
                <AvatarImage src="/placeholder-avatar.jpg" alt="Abir" />
                <AvatarFallback className="bg-primary text-primary-foreground text-xs sm:text-sm md:text-base">
                  A
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 bg-popover border-border">
            <DropdownMenuLabel className="text-popover-foreground">
              <div className="flex flex-col space-y-1">
                <p className="text-sm font-medium">Abir</p>
                <p className="text-xs text-muted-foreground">abir@example.com</p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="cursor-pointer hover:bg-accent hover:text-accent-foreground">
              <User className="mr-2 h-4 w-4" />
              <span>Profile</span>
            </DropdownMenuItem>
            <DropdownMenuItem className="cursor-pointer hover:bg-accent hover:text-accent-foreground">
              <BarChart3 className="mr-2 h-4 w-4" />
              <span>Usage</span>
            </DropdownMenuItem>
            <DropdownMenuItem className="cursor-pointer hover:bg-accent hover:text-accent-foreground">
              <Settings className="mr-2 h-4 w-4" />
              <span>Settings</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="cursor-pointer hover:bg-accent hover:text-accent-foreground text-destructive">
              <LogOut className="mr-2 h-4 w-4" />
              <span>Logout</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}