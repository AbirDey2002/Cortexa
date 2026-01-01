import { useState, useMemo } from "react";
import { RequirementCard } from "./RequirementCard";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Maximize2 } from "lucide-react";
import { ExpandedContentView } from "./ExpandedContentView";

interface Requirement {
  id: string;
  display_id?: number;
  name: string;
  description: string;
  requirement_entities?: any;
  created_at?: string;
}

interface RequirementsMessageProps {
  requirements: Requirement[];
  usecaseId: string;
  messageId?: string;
  onExpand?: (messageId: string) => void;
  isExpanded?: boolean;
  onMinimize?: () => void;
}

export function RequirementsMessage({
  requirements,
  usecaseId,
  messageId,
  onExpand,
  isExpanded = false,
  onMinimize,
}: RequirementsMessageProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState<"name" | "content">("name");

  // Filter requirements based on search
  const filteredRequirements = useMemo(() => {
    if (!searchQuery.trim()) return requirements;

    return requirements.filter((req) => {
      if (searchMode === "name") {
        return req.name.toLowerCase().includes(searchQuery.toLowerCase());
      } else {
        // Search in name, description, and requirement_entities
        const searchableText = [
          req.name,
          req.description,
          JSON.stringify(req.requirement_entities || {}),
        ]
          .join(" ")
          .toLowerCase();
        return searchableText.includes(searchQuery.toLowerCase());
      }
    });
  }, [requirements, searchQuery, searchMode]);

  const handleExpand = () => {
    if (messageId && onExpand) {
      onExpand(messageId);
    }
  };

  if (!requirements || requirements.length === 0) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden bg-chat-assistant border border-primary/30 mr-auto shadow-sm">
          <div className="text-sm text-muted-foreground">
            No requirements found for this usecase.
          </div>
        </div>
      </div>
    );
  }

  // Collapsed view
  const collapsedView = (
    <div className="flex justify-start w-full" style={{ width: '100%', maxWidth: '100%' }}>
      <div className="w-full max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-x-hidden bg-chat-assistant border border-primary/30 mr-auto flex flex-col shadow-sm" style={{ width: '100%', maxWidth: '95%', boxSizing: 'border-box', overflow: 'hidden' }}>
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs font-semibold text-muted-foreground">
            Requirements ({requirements.length})
          </div>
          {messageId && onExpand && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleExpand}
              className="h-6 px-2 text-xs"
              title="Expand to full screen"
            >
              <Maximize2 className="h-3 w-3 mr-1" />
              Expand
            </Button>
          )}
        </div>
        
        {/* Requirements List - Scrollable */}
        <ScrollArea className="w-full max-w-full flex-1 max-h-[600px] pr-4 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', overflow: 'hidden' }}>
          <div className="w-full max-w-full space-y-2 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
            {requirements.map((requirement, index) => (
              <RequirementCard
                key={requirement.id}
                requirement={requirement}
                index={index}
                isInExpandedView={false}
                searchQuery={searchQuery}
              />
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  );

  // Expanded view
  if (isExpanded && onMinimize) {
    return (
      <ExpandedContentView
        isExpanded={isExpanded}
        onClose={onMinimize}
        title={`Requirements (${filteredRequirements.length}${searchQuery ? ` filtered from ${requirements.length}` : ''})`}
        searchComponent={
          <div className="flex items-center gap-2 w-full max-w-md">
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search requirements..."
              className="flex-1"
            />
            <ToggleGroup
              type="single"
              value={searchMode}
              onValueChange={(v) => {
                if (v === "name" || v === "content") {
                  setSearchMode(v);
                }
              }}
            >
              <ToggleGroupItem value="name" aria-label="Search by name">
                By Name
              </ToggleGroupItem>
              <ToggleGroupItem value="content" aria-label="Search full content">
                Full Content
              </ToggleGroupItem>
            </ToggleGroup>
          </div>
        }
      >
        <div className="space-y-2">
          {filteredRequirements.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-8">
              No requirements match your search.
            </div>
          ) : (
            filteredRequirements.map((requirement, index) => (
              <RequirementCard
                key={requirement.id}
                requirement={requirement}
                index={index}
                isInExpandedView={isExpanded}
                searchQuery={searchQuery}
              />
            ))
          )}
        </div>
      </ExpandedContentView>
    );
  }

  return collapsedView;
}

