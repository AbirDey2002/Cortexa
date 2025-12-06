import { RequirementCard } from "./RequirementCard";
import { ScrollArea } from "@/components/ui/scroll-area";

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
}

export function RequirementsMessage({
  requirements,
  usecaseId,
}: RequirementsMessageProps) {
  if (!requirements || requirements.length === 0) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden bg-chat-assistant border border-border mr-auto">
          <div className="text-sm text-muted-foreground">
            No requirements found for this usecase.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start w-full" style={{ width: '100%', maxWidth: '100%' }}>
      <div className="w-full max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-x-hidden bg-chat-assistant border border-border mr-auto flex flex-col" style={{ width: '100%', maxWidth: '95%', boxSizing: 'border-box', overflow: 'hidden' }}>
        {/* Header */}
        <div className="text-xs font-semibold mb-3 text-muted-foreground">
          Requirements ({requirements.length})
        </div>
        
        {/* Requirements List - Scrollable */}
        <ScrollArea className="w-full max-w-full flex-1 max-h-[600px] pr-4 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', overflow: 'hidden' }}>
          <div className="w-full max-w-full space-y-2 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
            {requirements.map((requirement, index) => (
              <RequirementCard
                key={requirement.id}
                requirement={requirement}
                index={index}
              />
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

