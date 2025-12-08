import { useState, useRef, useEffect } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";

interface Requirement {
  id: string;
  display_id?: number;
  name: string;
  description: string;
  requirement_entities?: any;
  created_at?: string;
}

interface RequirementCardProps {
  requirement: Requirement;
  index: number;
  isInExpandedView?: boolean;
  searchQuery?: string;
}

export function RequirementCard({ requirement, index, isInExpandedView = false, searchQuery = "" }: RequirementCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const descriptionRef = useRef<HTMLDivElement>(null);
  const [needsScrolling, setNeedsScrolling] = useState(false);
  
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

  // ScrollingText component for long descriptions
  const ScrollingText = ({ text, query }: { text: string; query: string }) => {
    const textRef = useRef<HTMLDivElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [shouldScroll, setShouldScroll] = useState(false);
    const [textWidth, setTextWidth] = useState(0);

    useEffect(() => {
      if (textRef.current && containerRef.current) {
        const measuredWidth = textRef.current.scrollWidth;
        const containerWidth = containerRef.current.offsetWidth;
        setTextWidth(measuredWidth);
        setShouldScroll(measuredWidth > containerWidth);
      }
    }, [text, query]);

    if (!shouldScroll) {
      return (
        <div ref={containerRef} className="overflow-hidden">
          {query ? (
            <HighlightedText text={text} query={query} />
          ) : (
            <span>{text}</span>
          )}
        </div>
      );
    }

    // Calculate animation duration based on text width (roughly 50px per second)
    const duration = Math.max(10, textWidth / 50);

    return (
      <div 
        ref={containerRef}
        className="relative overflow-hidden"
        style={{ width: '100%' }}
      >
        <div
          ref={textRef}
          className="inline-flex whitespace-nowrap"
          style={{
            animation: shouldScroll ? `scroll-text-${index} ${duration}s linear infinite` : 'none',
          }}
        >
          <span style={{ paddingRight: '3rem' }}>
            {query ? (
              <HighlightedText text={text} query={query} />
            ) : (
              <span>{text}</span>
            )}
          </span>
          {/* Duplicate for seamless loop */}
          <span style={{ paddingRight: '3rem' }}>
            {query ? (
              <HighlightedText text={text} query={query} />
            ) : (
              <span>{text}</span>
            )}
          </span>
        </div>
        <style>{`
          @keyframes scroll-text-${index} {
            0% {
              transform: translateX(0);
            }
            100% {
              transform: translateX(calc(-50% - 1.5rem));
            }
          }
        `}</style>
      </div>
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

  // Extract requirement entities data
  const requirementEntities = requirement.requirement_entities || {};
  const entitiesArray = Array.isArray(requirementEntities) 
    ? requirementEntities 
    : (requirementEntities.requirement_entities || []);

  // Get the first entity (most requirements have one entity)
  const entity = entitiesArray.length > 0 ? entitiesArray[0] : {};
  const requirementsData = entity.requirements || {};
  const userStories = entity.user_stories || [];

  // Helper to render a list section
  const renderListSection = (title: string, items: any[], keyPrefix: string) => {
    if (!items || items.length === 0) return null;
    
    return (
      <div className="w-full max-w-full mb-4 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
        <h4 className="text-sm font-semibold text-foreground mb-2">{title}</h4>
        <ul className="w-full max-w-full list-disc list-inside space-y-1 ml-2 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', overflow: 'hidden' }}>
          {items.map((item, idx) => (
            <li key={`${keyPrefix}-${idx}`} className="w-full max-w-full text-sm text-muted-foreground break-words min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
              {typeof item === 'string' ? item : (
                <pre className="w-full max-w-full text-xs break-words whitespace-pre-wrap overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
                  {JSON.stringify(item, null, 2)}
                </pre>
              )}
            </li>
          ))}
        </ul>
      </div>
    );
  };

  // Helper to render nested object sections
  const renderObjectSection = (title: string, obj: any, keyPrefix: string) => {
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null;
    
    const entries = Object.entries(obj);
    if (entries.length === 0) return null;

    return (
      <div className="w-full max-w-full mb-4 overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
        <h4 className="text-sm font-semibold text-foreground mb-2">{title}</h4>
        <div className="w-full max-w-full space-y-2 ml-2 overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, overflow: 'hidden' }}>
          {entries.map(([key, value], idx) => {
            const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
            const displayKey = camelKey.replace(/([A-Z])/g, ' $1').trim();
            
            if (Array.isArray(value) && value.length > 0) {
              return (
                <div key={`${keyPrefix}-${key}-${idx}`} className="w-full max-w-full mb-2 overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, boxSizing: 'border-box', overflow: 'hidden' }}>
                  <span className="text-xs font-medium text-muted-foreground">{displayKey}:</span>
                  <ul className="w-full max-w-full list-disc list-inside space-y-1 ml-3 mt-1 overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, overflow: 'hidden' }}>
                    {value.map((item: any, itemIdx: number) => (
                      <li key={`${keyPrefix}-${key}-${idx}-${itemIdx}`} className="w-full max-w-full text-xs text-muted-foreground break-words min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
                        {typeof item === 'string' ? item : (
                          <pre className="w-full max-w-full text-xs break-words whitespace-pre-wrap overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
                            {JSON.stringify(item, null, 2)}
                          </pre>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            } else if (typeof value === 'object' && value !== null) {
              return (
                <div key={`${keyPrefix}-${key}-${idx}`} className="w-full max-w-full mb-2 overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, boxSizing: 'border-box', overflow: 'hidden' }}>
                  <span className="text-xs font-medium text-muted-foreground">{displayKey}:</span>
                  <div className="w-full max-w-full ml-3 mt-1 text-xs text-muted-foreground break-words overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
                    <pre className="w-full max-w-full whitespace-pre-wrap overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>{JSON.stringify(value, null, 2)}</pre>
                  </div>
                </div>
              );
            } else if (value) {
              return (
                <div key={`${keyPrefix}-${key}-${idx}`} className="w-full max-w-full mb-1 overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, boxSizing: 'border-box', overflow: 'hidden' }}>
                  <span className="text-xs font-medium text-muted-foreground">{displayKey}:</span>
                  <span className="text-xs text-muted-foreground ml-2 break-words min-w-0" style={{ wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>{String(value)}</span>
                </div>
              );
            }
            return null;
          })}
        </div>
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
            <div className="text-sm font-semibold text-foreground truncate break-words" style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}>
              {requirement.display_id ? `REQ-${requirement.display_id} : ` : ''}
              {searchQuery ? (
                <HighlightedText text={requirement.name || `Requirement ${index + 1}`} query={searchQuery} />
              ) : (
                requirement.name || `Requirement ${index + 1}`
              )}
            </div>
            {!isExpanded && requirement.description && (
              <div 
                className="text-xs text-muted-foreground mt-1 overflow-hidden"
                style={{ 
                  width: '100%',
                  maxWidth: '100%',
                  minWidth: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap'
                }}
              >
                {(() => {
                  // Use 125 chars when RequirementsMessage is collapsed, 300 when expanded
                  const maxLength = isInExpandedView ? 300 : 125;
                  const truncated = requirement.description.length > maxLength 
                    ? requirement.description.substring(0, maxLength) + '...'
                    : requirement.description;
                  return searchQuery ? (
                    <HighlightedText text={truncated} query={searchQuery} />
                  ) : (
                    <span>{truncated}</span>
                  );
                })()}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="w-full max-w-full border-t border-border overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
          <ScrollArea className={`w-full max-w-full ${!isInExpandedView ? 'max-h-[600px]' : ''} overflow-y-auto overflow-x-hidden`} style={{ width: '100%', maxWidth: '100%' }}>
            <div className="w-full max-w-full p-4 space-y-4 break-words overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
              {/* Description */}
              {requirement.description && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, boxSizing: 'border-box', overflow: 'hidden' }}>
                  <h4 className="text-sm font-semibold text-foreground mb-2">Description</h4>
                  <p className="w-full max-w-full text-sm text-muted-foreground break-words min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
                    {searchQuery ? (
                      <HighlightedText text={requirement.description} query={searchQuery} />
                    ) : (
                      requirement.description
                    )}
                  </p>
                </div>
              )}

              {/* User Stories */}
              {renderListSection("User Stories", userStories, `req-${requirement.id}-user-stories`)}

              {/* Requirements Sections */}
              {requirementsData && Object.keys(requirementsData).length > 0 && (
                <div className="w-full max-w-full overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, wordWrap: 'break-word', overflowWrap: 'break-word', boxSizing: 'border-box', overflow: 'hidden' }}>
                  <h4 className="text-sm font-semibold text-foreground mb-3">Requirements</h4>
                  <div className="w-full max-w-full space-y-4 overflow-x-hidden min-w-0" style={{ width: '100%', maxWidth: '100%', minWidth: 0, overflow: 'hidden' }}>
                    {/* Functional Requirements */}
                    {requirementsData.functional_requirements && 
                      renderListSection(
                        "Functional Requirements", 
                        requirementsData.functional_requirements,
                        `req-${requirement.id}-functional`
                      )}

                    {/* Business Rules */}
                    {requirementsData.business_rules && 
                      renderListSection(
                        "Business Rules", 
                        requirementsData.business_rules,
                        `req-${requirement.id}-business-rules`
                      )}

                    {/* Data Elements */}
                    {requirementsData.data_elements && 
                      renderListSection(
                        "Data Elements", 
                        requirementsData.data_elements,
                        `req-${requirement.id}-data-elements`
                      )}

                    {/* UI/UX Requirements */}
                    {requirementsData["UI/UX_requirements"] && 
                      renderListSection(
                        "UI/UX Requirements", 
                        requirementsData["UI/UX_requirements"],
                        `req-${requirement.id}-ui-ux`
                      )}

                    {/* API Specifications */}
                    {requirementsData.api_specifications && 
                      renderListSection(
                        "API Specifications", 
                        requirementsData.api_specifications,
                        `req-${requirement.id}-api-specs`
                      )}

                    {/* Request Response Details */}
                    {requirementsData.request_response_details && 
                      renderListSection(
                        "Request/Response Details", 
                        requirementsData.request_response_details,
                        `req-${requirement.id}-req-resp`
                      )}

                    {/* Integration Requirements */}
                    {requirementsData.integration_requirements && 
                      renderListSection(
                        "Integration Requirements", 
                        requirementsData.integration_requirements,
                        `req-${requirement.id}-integration`
                      )}

                    {/* Non-Functional Requirements */}
                    {requirementsData.non_functional_requirements && 
                      renderListSection(
                        "Non-Functional Requirements", 
                        requirementsData.non_functional_requirements,
                        `req-${requirement.id}-non-functional`
                      )}

                    {/* Other Requirements */}
                    {requirementsData.other_requirements && 
                      renderListSection(
                        "Other Requirements", 
                        requirementsData.other_requirements,
                        `req-${requirement.id}-other`
                      )}

                    {/* Pre-conditions */}
                    {requirementsData.pre_conditions && 
                      renderListSection(
                        "Pre-conditions", 
                        requirementsData.pre_conditions,
                        `req-${requirement.id}-preconditions`
                      )}

                    {/* Actions */}
                    {requirementsData.actions && 
                      renderListSection(
                        "Actions", 
                        requirementsData.actions,
                        `req-${requirement.id}-actions`
                      )}

                    {/* Wireframes */}
                    {requirementsData.wireframes && 
                      renderListSection(
                        "Wireframes", 
                        requirementsData.wireframes,
                        `req-${requirement.id}-wireframes`
                      )}

                    {/* Authentication Authorization */}
                    {requirementsData.authentication_authorization && 
                      renderListSection(
                        "Authentication & Authorization", 
                        requirementsData.authentication_authorization,
                        `req-${requirement.id}-auth`
                      )}

                    {/* Error Handling */}
                    {requirementsData.error_handling && 
                      renderListSection(
                        "Error Handling", 
                        requirementsData.error_handling,
                        `req-${requirement.id}-error-handling`
                      )}

                    {/* Service Integration */}
                    {requirementsData.service_integration && 
                      renderListSection(
                        "Service Integration", 
                        requirementsData.service_integration,
                        `req-${requirement.id}-service-integration`
                      )}

                    {/* Render any other dynamic sections */}
                    {Object.entries(requirementsData).map(([key, value]) => {
                      // Skip already rendered sections
                      const renderedKeys = [
                        'functional_requirements', 'business_rules', 'data_elements',
                        'UI/UX_requirements', 'api_specifications', 'request_response_details',
                        'integration_requirements', 'non_functional_requirements', 'other_requirements',
                        'pre_conditions', 'actions', 'wireframes', 'authentication_authorization',
                        'error_handling', 'service_integration'
                      ];
                      if (renderedKeys.includes(key)) return null;

                      if (Array.isArray(value) && value.length > 0) {
                        const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
                        const displayKey = camelKey.replace(/([A-Z])/g, ' $1').trim();
                        return renderListSection(
                          displayKey,
                          value as any[],
                          `req-${requirement.id}-${key}`
                        );
                      } else if (typeof value === 'object' && value !== null) {
                        const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
                        const displayKey = camelKey.replace(/([A-Z])/g, ' $1').trim();
                        return renderObjectSection(
                          displayKey,
                          value,
                          `req-${requirement.id}-${key}`
                        );
                      }
                      return null;
                    })}
                  </div>
                </div>
              )}

              {/* Created At */}
              {requirement.created_at && (
                <div className="text-xs text-muted-foreground pt-2 border-t border-border">
                  Created: {new Date(requirement.created_at).toLocaleString()}
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      )}
    </Card>
  );
}

