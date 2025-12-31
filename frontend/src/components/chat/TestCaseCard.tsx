import { useState, useRef, useEffect } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";

interface TestCase {
  id: string;
  display_id: number;
  test_case: string;
  description?: string;
  flow?: string;
  requirementId?: string;
  scenarioId?: string;
  preConditions?: string[];
  testData?: string[];
  testSteps?: string[];
  expectedResults?: string[];
  postConditions?: string[];
  risk_analysis?: string;
  requirement_category?: string;
  lens?: string;
  scenario_display_id?: number;
  scenario_name?: string;
  requirement_display_id?: number;
  created_at?: string;
}

interface TestCaseCardProps {
  testCase: TestCase;
  index: number;
  searchQuery?: string;
}

export function TestCaseCard({ testCase, index, searchQuery = "" }: TestCaseCardProps) {
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
      setTimeout(() => {
        cardRef.current?.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'nearest',
          inline: 'nearest'
        });
      }, 100);
    }
  }, [isExpanded]);

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
                TC-{testCase.display_id} : {searchQuery ? (
                  <HighlightedText text={testCase.test_case || `Test Case ${index + 1}`} query={searchQuery} />
                ) : (
                  testCase.test_case || `Test Case ${index + 1}`
                )}
              </div>
              {testCase.scenario_display_id && (
                <Badge
                  variant="outline"
                  className="text-xs bg-green-50 text-green-700 border-green-200 flex-shrink-0"
                >
                  TS-{testCase.scenario_display_id}
                </Badge>
              )}
              {testCase.requirement_display_id && (
                <Badge
                  variant="outline"
                  className="text-xs bg-blue-50 text-blue-700 border-blue-200 flex-shrink-0"
                >
                  REQ-{testCase.requirement_display_id}
                </Badge>
              )}
            </div>
            {!isExpanded && testCase.description && (
              <div className="text-xs text-muted-foreground truncate break-words mt-1" style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}>
                {searchQuery ? (
                  <HighlightedText text={testCase.description} query={searchQuery} />
                ) : (
                  testCase.description
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
              {testCase.description && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Description</h4>
                  <p className="w-full max-w-full text-sm text-muted-foreground break-words min-w-0">
                    {searchQuery ? (
                      <HighlightedText text={testCase.description} query={searchQuery} />
                    ) : (
                      testCase.description
                    )}
                  </p>
                </div>
              )}

              {/* Flow */}
              {testCase.flow && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Flow</h4>
                  <p className="w-full max-w-full text-sm text-muted-foreground break-words min-w-0">
                    {searchQuery ? (
                      <HighlightedText text={testCase.flow} query={searchQuery} />
                    ) : (
                      testCase.flow
                    )}
                  </p>
                </div>
              )}

              {/* Preconditions */}
              {testCase.preConditions && testCase.preConditions.length > 0 && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Preconditions</h4>
                  <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
                    {testCase.preConditions.map((pc, idx) => (
                      <li key={idx}>
                        {searchQuery ? (
                          <HighlightedText text={pc} query={searchQuery} />
                        ) : (
                          pc
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Test Data */}
              {testCase.testData && testCase.testData.length > 0 && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Test Data</h4>
                  <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
                    {testCase.testData.map((td, idx) => (
                      <li key={idx}>
                        {searchQuery ? (
                          <HighlightedText text={td} query={searchQuery} />
                        ) : (
                          td
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Test Steps */}
              {testCase.testSteps && testCase.testSteps.length > 0 && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Test Steps</h4>
                  <ol className="list-decimal list-inside space-y-1 text-sm text-muted-foreground">
                    {testCase.testSteps.map((step, idx) => (
                      <li key={idx}>
                        {searchQuery ? (
                          <HighlightedText text={step} query={searchQuery} />
                        ) : (
                          step
                        )}
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {/* Expected Results */}
              {testCase.expectedResults && testCase.expectedResults.length > 0 && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Expected Results</h4>
                  <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
                    {testCase.expectedResults.map((er, idx) => (
                      <li key={idx}>
                        {searchQuery ? (
                          <HighlightedText text={er} query={searchQuery} />
                        ) : (
                          er
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Post Conditions */}
              {testCase.postConditions && testCase.postConditions.length > 0 && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Post Conditions</h4>
                  <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
                    {testCase.postConditions.map((pc, idx) => (
                      <li key={idx}>
                        {searchQuery ? (
                          <HighlightedText text={pc} query={searchQuery} />
                        ) : (
                          pc
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Risk Analysis */}
              {testCase.risk_analysis && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Risk Analysis</h4>
                  <p className="w-full max-w-full text-sm text-muted-foreground break-words min-w-0">
                    {searchQuery ? (
                      <HighlightedText text={testCase.risk_analysis} query={searchQuery} />
                    ) : (
                      testCase.risk_analysis
                    )}
                  </p>
                </div>
              )}

              {/* Requirement Category */}
              {testCase.requirement_category && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Requirement Category</h4>
                  <p className="w-full max-w-full text-sm text-muted-foreground break-words min-w-0">
                    {searchQuery ? (
                      <HighlightedText text={testCase.requirement_category} query={searchQuery} />
                    ) : (
                      testCase.requirement_category
                    )}
                  </p>
                </div>
              )}

              {/* Lens */}
              {testCase.lens && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0">
                  <h4 className="text-sm font-semibold text-foreground mb-2">Lens</h4>
                  <p className="w-full max-w-full text-sm text-muted-foreground break-words min-w-0">
                    {searchQuery ? (
                      <HighlightedText text={testCase.lens} query={searchQuery} />
                    ) : (
                      testCase.lens
                    )}
                  </p>
                </div>
              )}

              {/* Created At */}
              {testCase.created_at && (
                <div className="text-xs text-muted-foreground pt-2 border-t border-border">
                  Created: {new Date(testCase.created_at).toLocaleString()}
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      )}
    </Card>
  );
}

