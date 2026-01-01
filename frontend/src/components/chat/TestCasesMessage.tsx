import { useState, useMemo } from "react";
import { TestCaseCard } from "./TestCaseCard";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Maximize2 } from "lucide-react";
import { ExpandedContentView } from "./ExpandedContentView";
import { Label } from "@/components/ui/label";

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

interface TestCasesMessageProps {
  testCases: TestCase[];
  usecaseId: string;
  messageId?: string;
  onExpand?: (messageId: string) => void;
  isExpanded?: boolean;
  onMinimize?: () => void;
}

export function TestCasesMessage({
  testCases,
  usecaseId,
  messageId,
  onExpand,
  isExpanded = false,
  onMinimize,
}: TestCasesMessageProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState<"name" | "content">("name");
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("");
  const [selectedRequirementId, setSelectedRequirementId] = useState<string>("");

  // Extract unique scenarios from test cases
  const scenarios = useMemo(() => {
    const scens = new Map<string, { id: string; displayId: number; name?: string }>();
    testCases.forEach((tc) => {
      if (tc.scenarioId && tc.scenario_display_id) {
        scens.set(tc.scenarioId, {
          id: tc.scenarioId,
          displayId: tc.scenario_display_id,
          name: tc.scenario_name,
        });
      }
    });
    return Array.from(scens.values()).sort((a, b) => a.displayId - b.displayId);
  }, [testCases]);

  // Extract unique requirements from test cases
  const requirements = useMemo(() => {
    const reqs = new Map<string, { id: string; displayId: number }>();
    testCases.forEach((tc) => {
      if (tc.requirementId && tc.requirement_display_id) {
        reqs.set(tc.requirementId, {
          id: tc.requirementId,
          displayId: tc.requirement_display_id,
        });
      }
    });
    return Array.from(reqs.values()).sort((a, b) => a.displayId - b.displayId);
  }, [testCases]);

  // Filter test cases
  const filteredTestCases = useMemo(() => {
    let filtered = testCases;

    // Search filter
    if (searchQuery.trim()) {
      filtered = filtered.filter((tc) => {
        if (searchMode === "name") {
          return tc.test_case.toLowerCase().includes(searchQuery.toLowerCase());
        } else {
          const searchableText = [
            tc.test_case,
            tc.description,
            tc.flow,
            JSON.stringify(tc.preConditions || []),
            JSON.stringify(tc.testData || []),
            JSON.stringify(tc.testSteps || []),
            JSON.stringify(tc.expectedResults || []),
            JSON.stringify(tc.postConditions || []),
            tc.risk_analysis,
            tc.requirement_category,
            tc.lens,
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
          return searchableText.includes(searchQuery.toLowerCase());
        }
      });
    }

    // Scenario filter
    if (selectedScenarioId) {
      filtered = filtered.filter((tc) => {
        return tc.scenarioId === selectedScenarioId;
      });
    }

    // Requirement filter
    if (selectedRequirementId) {
      filtered = filtered.filter((tc) => {
        return tc.requirementId === selectedRequirementId;
      });
    }

    return filtered;
  }, [testCases, searchQuery, searchMode, selectedScenarioId, selectedRequirementId]);

  const handleExpand = () => {
    if (messageId && onExpand) {
      onExpand(messageId);
    }
  };

  if (!testCases || testCases.length === 0) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden bg-chat-assistant border border-primary/30 mr-auto shadow-sm">
          <div className="text-sm text-muted-foreground">
            No test cases found for this usecase.
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
            Test Cases ({testCases.length})
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
        
        {/* Test Cases List - Scrollable */}
        <ScrollArea className="w-full max-w-full flex-1 max-h-[600px] pr-4 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', overflow: 'hidden' }}>
          <div className="w-full max-w-full space-y-2 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
            {testCases.map((testCase, index) => (
              <TestCaseCard
                key={testCase.id}
                testCase={testCase}
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
    const titleText = testCases.length === 0 
      ? 'Test Cases (0)'
      : `Test Cases (${filteredTestCases.length}${searchQuery || selectedScenarioId || selectedRequirementId ? ` filtered from ${testCases.length}` : ''})`;
    
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
              placeholder="Search test cases..."
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
            {/* Scenario Filter */}
            {scenarios.length > 0 && (
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Scenario:</Label>
                <Select
                  value={selectedScenarioId || "all"}
                  onValueChange={(value) => setSelectedScenarioId(value === "all" ? "" : value)}
                >
                  <SelectTrigger className="w-[150px] h-8 text-xs">
                    <SelectValue placeholder="All Scenarios" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Scenarios</SelectItem>
                    {scenarios.map((scen) => (
                      <SelectItem key={scen.id} value={scen.id}>
                        TS-{scen.displayId} {scen.name ? `: ${scen.name}` : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
        {testCases.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-8">
            No test cases available.
          </div>
        ) : filteredTestCases.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-8">
            No test cases match your filters.
          </div>
        ) : (
          <div className="space-y-2">
            {filteredTestCases.map((testCase, index) => (
              <TestCaseCard
                key={testCase.id}
                testCase={testCase}
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

