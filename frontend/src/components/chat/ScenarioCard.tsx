import { useState, useRef, useEffect } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";

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

interface ScenarioCardProps {
  scenario: Scenario;
  index: number;
  searchQuery?: string;
}

export function ScenarioCard({ scenario, index, searchQuery = "" }: ScenarioCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  // HighlightedText component for search highlighting
  const HighlightedText = ({ text, query }: { text: string; query: string }) => {
    if (!query.trim()) return <span>{text}</span>;
    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    const parts = text.split(regex);
    return (
      <>
        {parts.map((part, i) => 
          part.toLowerCase() === query.toLowerCase() ? (
            <mark key={i} className="bg-yellow-400 text-black">{part}</mark>
          ) : (
            <span key={i}>{part}</span>
          )
        )}
      </>
    );
  };

  // Scroll into view when expanded
  useEffect(() => {
    if (isExpanded && cardRef.current) {
      // Small delay to ensure DOM is updated
      setTimeout(() => {
        cardRef.current?.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'nearest',
          inline: 'nearest'
        });
      }, 100);
    }
  }, [isExpanded]);

  // Helper to render a flow
  const renderFlow = (flow: any, flowIndex: number) => {
    return (
      <div key={`flow-${flowIndex}`} className="w-full max-w-full mb-4 p-3 bg-muted/30 rounded-md overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
        {flow.Type && (
          <div className="mb-2">
            <span className="text-xs font-semibold text-foreground">Type: </span>
            <span className="text-sm text-muted-foreground">
              {searchQuery ? (
                <HighlightedText text={flow.Type} query={searchQuery} />
              ) : (
                flow.Type
              )}
            </span>
          </div>
        )}
        {flow.Description && (
          <div className="mb-2">
            <span className="text-xs font-semibold text-foreground">Description: </span>
            <p className="text-sm text-muted-foreground break-words" style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}>
              {searchQuery ? (
                <HighlightedText text={flow.Description} query={searchQuery} />
              ) : (
                flow.Description
              )}
            </p>
          </div>
        )}
        {flow.Coverage && (
          <div className="mb-2">
            <span className="text-xs font-semibold text-foreground">Coverage: </span>
            <p className="text-sm text-muted-foreground break-words" style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}>
              {searchQuery ? (
                <HighlightedText text={flow.Coverage} query={searchQuery} />
              ) : (
                flow.Coverage
              )}
            </p>
          </div>
        )}
        {flow.ExpectedResults && (
          <div>
            <span className="text-xs font-semibold text-foreground">Expected Results: </span>
            <p className="text-sm text-muted-foreground break-words" style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}>
              {searchQuery ? (
                <HighlightedText text={flow.ExpectedResults} query={searchQuery} />
              ) : (
                flow.ExpectedResults
              )}
            </p>
          </div>
        )}
      </div>
    );
  };

  return (
    <Card ref={cardRef} className="w-full max-w-full border border-border bg-card mb-3 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
      {/* Header - Always visible */}
      <div 
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/50 transition-colors overflow-x-hidden w-full max-w-full"
        onClick={() => setIsExpanded(!isExpanded)}
        style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden' }}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0 max-w-full" style={{ width: '100%', maxWidth: '100%', minWidth: 0 }}>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 flex-shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </Button>
          <div className="flex-1 min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, overflow: 'hidden' }}>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="text-sm font-semibold text-foreground truncate break-words" style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}>
                TS-{scenario.display_id} : {searchQuery ? (
                  <HighlightedText text={scenario.scenario_name || `Scenario ${index + 1}`} query={searchQuery} />
                ) : (
                  scenario.scenario_name || `Scenario ${index + 1}`
                )}
              </div>
              <Badge
                variant="outline"
                className="text-xs bg-blue-50 text-blue-700 border-blue-200 flex-shrink-0"
              >
                REQ-{scenario.requirement_display_id}
              </Badge>
            </div>
            {!isExpanded && scenario.scenario_description && (
              <div className="text-xs text-muted-foreground truncate break-words mt-1" style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}>
                {searchQuery ? (
                  <HighlightedText text={scenario.scenario_description} query={searchQuery} />
                ) : (
                  scenario.scenario_description
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="w-full max-w-full border-t border-border overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
          <ScrollArea className="w-full max-w-full max-h-[600px] overflow-y-auto overflow-x-hidden" style={{ width: '100%', maxWidth: '100%' }}>
            <div className="w-full max-w-full p-4 space-y-4 break-words overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
              {/* Description */}
              {scenario.scenario_description && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, boxSizing: 'border-box', overflow: 'hidden' }}>
                  <h4 className="text-sm font-semibold text-foreground mb-2">Description</h4>
                  <p className="w-full max-w-full text-sm text-muted-foreground break-words min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
                    {searchQuery ? (
                      <HighlightedText text={scenario.scenario_description} query={searchQuery} />
                    ) : (
                      scenario.scenario_description
                    )}
                  </p>
                </div>
              )}

              {/* Flows */}
              {scenario.flows && scenario.flows.length > 0 && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
                  <h4 className="text-sm font-semibold text-foreground mb-3">Flows</h4>
                  <div className="w-full max-w-full space-y-3 overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, overflow: 'hidden' }}>
                    {scenario.flows.map((flow, flowIndex) => renderFlow(flow, flowIndex))}
                  </div>
                </div>
              )}

              {/* Created At */}
              {scenario.created_at && (
                <div className="text-xs text-muted-foreground pt-2 border-t border-border">
                  Created: {new Date(scenario.created_at).toLocaleString()}
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      )}
    </Card>
  );
}

