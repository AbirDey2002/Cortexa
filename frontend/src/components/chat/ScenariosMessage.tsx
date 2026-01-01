import { useState, useMemo } from "react";
import { ScenarioCard } from "./ScenarioCard";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Maximize2 } from "lucide-react";
import { ExpandedContentView } from "./ExpandedContentView";
import { Label } from "@/components/ui/label";

interface Scenario {
  id: string;
  display_id: number;
  scenario_name: string;
  scenario_description: string;
  scenario_id?: string;
  requirement_id: string;
  requirement_display_id: number;
  flows?: Array<{
    Type?: string;
    Description?: string;
    Coverage?: string;
    ExpectedResults?: string;
  }>;
  created_at?: string;
}

interface ScenariosMessageProps {
  scenarios: Scenario[];
  usecaseId: string;
  messageId?: string;
  onExpand?: (messageId: string) => void;
  isExpanded?: boolean;
  onMinimize?: () => void;
}

export function ScenariosMessage({
  scenarios,
  usecaseId,
  messageId,
  onExpand,
  isExpanded = false,
  onMinimize,
}: ScenariosMessageProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState<"name" | "content">("name");
  const [selectedFlowTypes, setSelectedFlowTypes] = useState<Set<string>>(new Set());
  const [selectedRequirementId, setSelectedRequirementId] = useState<string>("");

  // Extract unique flow types from scenarios
  const flowTypes = useMemo(() => {
    const types = new Set<string>();
    scenarios.forEach((s) => {
      s.flows?.forEach((f) => {
        if (f.Type) types.add(f.Type);
      });
    });
    return Array.from(types).sort();
  }, [scenarios]);

  // Extract unique requirements from scenarios
  const requirements = useMemo(() => {
    const reqs = new Map<string, { id: string; displayId: number }>();
    scenarios.forEach((s) => {
      if (s.requirement_id && s.requirement_display_id) {
        reqs.set(s.requirement_id, {
          id: s.requirement_id,
          displayId: s.requirement_display_id,
        });
      }
    });
    return Array.from(reqs.values()).sort((a, b) => a.displayId - b.displayId);
  }, [scenarios]);

  // Filter scenarios
  const filteredScenarios = useMemo(() => {
    let filtered = scenarios;

    // Search filter
    if (searchQuery.trim()) {
      filtered = filtered.filter((s) => {
        if (searchMode === "name") {
          return s.scenario_name.toLowerCase().includes(searchQuery.toLowerCase());
        } else {
          const searchableText = [
            s.scenario_name,
            s.scenario_description,
            JSON.stringify(s.flows || []),
          ]
            .join(" ")
            .toLowerCase();
          return searchableText.includes(searchQuery.toLowerCase());
        }
      });
    }

    // Flow type filter
    if (selectedFlowTypes.size > 0) {
      filtered = filtered.filter((s) => {
        return s.flows?.some((f) => f.Type && selectedFlowTypes.has(f.Type));
      });
    }

    // Requirement filter
    if (selectedRequirementId) {
      filtered = filtered.filter((s) => {
        return s.requirement_id === selectedRequirementId;
      });
    }

    return filtered;
  }, [scenarios, searchQuery, searchMode, selectedFlowTypes, selectedRequirementId]);

  const handleExpand = () => {
    if (messageId && onExpand) {
      onExpand(messageId);
    }
  };

  if (!scenarios || scenarios.length === 0) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden bg-chat-assistant border border-primary/30 mr-auto shadow-sm">
          <div className="text-sm text-muted-foreground">
            No scenarios found for this usecase.
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
            Scenarios ({scenarios.length})
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
        
        {/* Scenarios List - Scrollable */}
        <ScrollArea className="w-full max-w-full flex-1 max-h-[600px] pr-4 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', overflow: 'hidden' }}>
          <div className="w-full max-w-full space-y-2 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
            {scenarios.map((scenario, index) => (
              <ScenarioCard
                key={scenario.id}
                scenario={scenario}
                index={index}
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
    console.log('[SCENARIOS-EXPAND] Rendering expanded view, messageId:', messageId, 'scenarios:', scenarios.length, 'filtered:', filteredScenarios.length, 'isExpanded:', isExpanded);
    
    const titleText = scenarios.length === 0 
      ? 'Scenarios (0)'
      : `Scenarios (${filteredScenarios.length}${searchQuery || selectedFlowTypes.size > 0 || selectedRequirementId ? ` filtered from ${scenarios.length}` : ''})`;
    
    return (
      <ExpandedContentView
        isExpanded={true}
        onClose={onMinimize}
        title={titleText}
        searchComponent={
          <div className="flex items-center gap-2 w-full max-w-md">
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search scenarios..."
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
        filterComponent={
          <div className="flex items-center gap-4">
            {/* Flow Type Filter */}
            {flowTypes.length > 0 && (
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Flow Types:</Label>
                <div className="flex items-center gap-2">
                  {flowTypes.map((type) => (
                    <div key={type} className="flex items-center gap-1">
                      <Checkbox
                        id={`flow-${type}`}
                        checked={selectedFlowTypes.has(type)}
                        onCheckedChange={(checked) => {
                          const newSet = new Set(selectedFlowTypes);
                          if (checked) {
                            newSet.add(type);
                          } else {
                            newSet.delete(type);
                          }
                          setSelectedFlowTypes(newSet);
                        }}
                      />
                      <Label
                        htmlFor={`flow-${type}`}
                        className="text-xs cursor-pointer"
                      >
                        {type}
                      </Label>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Requirement Filter */}
            {requirements.length > 0 && (
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Requirement:</Label>
                <Select
                  value={selectedRequirementId || "all"}
                  onValueChange={(value) => setSelectedRequirementId(value === "all" ? "" : value)}
                >
                  <SelectTrigger className="w-[150px] h-8 text-xs">
                    <SelectValue placeholder="All Requirements" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Requirements</SelectItem>
                    {requirements.map((req) => (
                      <SelectItem key={req.id} value={req.id}>
                        REQ-{req.displayId}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        }
      >
        {scenarios.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-8">
            No scenarios available.
          </div>
        ) : filteredScenarios.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-8">
            No scenarios match your filters.
          </div>
        ) : (
          <div className="space-y-2">
            {            filteredScenarios.map((scenario, index) => (
              <ScenarioCard
                key={scenario.id}
                scenario={scenario}
                index={index}
                searchQuery={searchQuery}
              />
            ))}
          </div>
        )}
      </ExpandedContentView>
    );
  }

  return collapsedView;
}

