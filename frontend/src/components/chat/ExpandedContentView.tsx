import React from "react";
import { X, Minimize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

interface ExpandedContentViewProps {
  isExpanded: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  searchComponent?: React.ReactNode;
  filterComponent?: React.ReactNode;
}

export function ExpandedContentView({
  isExpanded,
  onClose,
  title,
  children,
  searchComponent,
  filterComponent,
}: ExpandedContentViewProps) {
  if (!isExpanded) return null;

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col">
      {/* Header Bar */}
      <div className="h-auto min-h-16 border-b border-border flex flex-col sm:flex-row items-stretch sm:items-center justify-between px-4 py-2 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 gap-2">
        {/* Left: Title */}
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold text-foreground truncate">{title}</h2>
        </div>

        {/* Center: Search */}
        {searchComponent && (
          <div className="flex-1 flex justify-center px-2 sm:px-4">
            {searchComponent}
          </div>
        )}

        {/* Right: Filters and Close Button */}
        <div className="flex items-center justify-end gap-2 flex-shrink-0">
          {filterComponent && (
            <div className="flex items-center gap-2 flex-wrap">
              {filterComponent}
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-8 w-8 p-0"
            title="Minimize"
          >
            <Minimize2 className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-8 w-8 p-0"
            title="Close"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full w-full">
          <div className="p-4">
            {children}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

