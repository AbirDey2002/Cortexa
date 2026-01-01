import { useState, useEffect, useMemo, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Search, Maximize2, ArrowUp, ArrowDown } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { ExpandedContentView } from "./ExpandedContentView";

interface PdfPage {
  page_number: number;
  markdown: string;
  is_completed: boolean;
}

interface PdfFile {
  fileId: string;
  fileName: string;
  pages: PdfPage[];
}

interface Match {
  pageNumber: number;
  pageIndex: number;
  matchIndex: number;
}

interface PdfContentMessageProps {
  files: PdfFile[];
  messageId?: string;
  onExpand?: (messageId: string) => void;
  isExpanded?: boolean;
  onMinimize?: () => void;
}

export function PdfContentMessage({
  files,
  messageId,
  onExpand,
  isExpanded = false,
  onMinimize,
}: PdfContentMessageProps) {
  // Handle single file for backward compatibility
  const fileArray = Array.isArray(files) ? files : [files];
  const totalFiles = fileArray.length;
  
  const [currentFileIndex, setCurrentFileIndex] = useState(0);
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentMatchIndex, setCurrentMatchIndex] = useState(0);
  const matchRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  
  const currentFile = fileArray[currentFileIndex];
  const sortedPages = currentFile ? [...currentFile.pages].sort((a, b) => a.page_number - b.page_number) : [];
  const currentPage = sortedPages[currentPageIndex];
  const totalPages = sortedPages.length;
  
  // Reset page index when file changes
  useEffect(() => {
    setCurrentPageIndex(0);
  }, [currentFileIndex]);

  // Find all matches across all pages
  const matches = useMemo(() => {
    if (!searchQuery.trim()) return [];
    
    const allMatches: Match[] = [];
    const query = searchQuery.toLowerCase();
    
    sortedPages.forEach((page, pageIdx) => {
      const text = page.markdown.toLowerCase();
      let startIndex = 0;
      while (true) {
        const index = text.indexOf(query, startIndex);
        if (index === -1) break;
        allMatches.push({
          pageNumber: page.page_number,
          pageIndex: pageIdx,
          matchIndex: index,
        });
        startIndex = index + 1;
      }
    });
    
    return allMatches;
  }, [sortedPages, searchQuery]);

  // Navigate to match
  const navigateToMatch = (matchIndex: number) => {
    if (matches.length === 0) return;
    const match = matches[matchIndex];
    setCurrentPageIndex(match.pageIndex);
    setCurrentMatchIndex(matchIndex);
    
    // Scroll to match after a short delay
    setTimeout(() => {
      const matchKey = `${match.pageNumber}-${match.matchIndex}`;
      const element = matchRefs.current.get(matchKey);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        element.classList.add('animate-pulse');
        setTimeout(() => element.classList.remove('animate-pulse'), 2000);
      }
    }, 100);
  };

  // Handle search query change
  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
    setCurrentMatchIndex(0);
    if (query.trim() && matches.length > 0) {
      navigateToMatch(0);
    }
  };

  // Navigate to next/previous match
  const handleNextMatch = () => {
    if (matches.length === 0) return;
    const nextIndex = (currentMatchIndex + 1) % matches.length;
    navigateToMatch(nextIndex);
  };

  const handlePreviousMatch = () => {
    if (matches.length === 0) return;
    const prevIndex = (currentMatchIndex - 1 + matches.length) % matches.length;
    navigateToMatch(prevIndex);
  };

  // Simple text highlighting component
  // Note: Full markdown-aware highlighting would require a more complex solution
  const HighlightedText = ({ text, query }: { text: string; query: string }) => {
    if (!query.trim()) {
      return <span>{text}</span>;
    }

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
  
  const canGoPreviousFile = currentFileIndex > 0;
  const canGoNextFile = currentFileIndex < totalFiles - 1;
  const canGoPreviousPage = currentPageIndex > 0;
  const canGoNextPage = currentPageIndex < totalPages - 1;
  
  const handlePreviousFile = () => {
    if (canGoPreviousFile) {
      setCurrentFileIndex(prev => prev - 1);
    }
  };
  
  const handleNextFile = () => {
    if (canGoNextFile) {
      setCurrentFileIndex(prev => prev + 1);
    }
  };
  
  const handlePreviousPage = () => {
    if (canGoPreviousPage) {
      setCurrentPageIndex(prev => prev - 1);
    }
  };
  
  const handleNextPage = () => {
    if (canGoNextPage) {
      setCurrentPageIndex(prev => prev + 1);
    }
  };
  
  if (!currentFile) {
    return null;
  }

  const handleExpand = () => {
    if (messageId && onExpand) {
      onExpand(messageId);
    }
  };

  // Expanded view content
  const expandedContent = (
    <>
      {/* All pages with highlighting */}
      <div className="space-y-6">
        {sortedPages.map((page, pageIdx) => {
          const pageMatches = matches.filter(m => m.pageIndex === pageIdx);

          return (
            <div
              key={page.page_number}
              className="border border-border rounded-lg p-4 bg-card"
            >
              <div className="text-sm font-semibold mb-2 text-muted-foreground">
                Page {page.page_number}
              </div>
              <div className="text-sm leading-relaxed break-words markdown-content">
                {searchQuery.trim() ? (
                  // For search mode, render as plain text with highlighting
                  // This is simpler than trying to highlight within markdown
                  <div className="whitespace-pre-wrap">
                    <HighlightedText text={page.markdown || ""} query={searchQuery} />
                  </div>
                ) : (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeHighlight]}
                  >
                    {page.markdown || ""}
                  </ReactMarkdown>
                )}
              </div>
              {pageMatches.map((match, matchIdx) => {
                const matchKey = `${match.pageNumber}-${match.matchIndex}`;
                return (
                  <div
                    key={matchKey}
                    ref={(el) => {
                      if (el) matchRefs.current.set(matchKey, el);
                      else matchRefs.current.delete(matchKey);
                    }}
                    className="search-match-marker"
                  />
                );
              })}
            </div>
          );
        })}
      </div>
    </>
  );

  // Collapsed view
  const collapsedView = (
    <div className="flex justify-start">
      <div className="max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden bg-chat-assistant border border-primary/30 mr-auto flex flex-col shadow-sm">
        {/* File-level navigation (top) - only show if multiple files */}
        {totalFiles > 1 && (
          <div className="flex items-center justify-between gap-2 mb-3 pb-3 border-b border-border">
            <Button
              variant="outline"
              size="sm"
              onClick={handlePreviousFile}
              disabled={!canGoPreviousFile}
              className="flex items-center gap-1"
            >
              <ChevronLeft className="w-4 h-4" />
              Previous
            </Button>
            <div className="flex flex-col items-center gap-1">
              <div className="text-xs font-semibold text-muted-foreground">
                {currentFile.fileName}
              </div>
              <div className="text-xs text-muted-foreground">
                File {currentFileIndex + 1} of {totalFiles}
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleNextFile}
              disabled={!canGoNextFile}
              className="flex items-center gap-1"
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        )}
        
        {/* File name header (single file or current file name when multiple) */}
        {totalFiles === 1 && (
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-semibold text-muted-foreground">
              {currentFile.fileName}
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
        )}
        
        {/* Page indicator */}
        {totalPages > 0 && (
          <div className="text-xs font-semibold mb-2 text-muted-foreground">
            Page {currentPage?.page_number || 0} of {totalPages}
          </div>
        )}
        
        {/* Current page content - scrollable */}
        {totalPages === 0 ? (
          <div className="text-sm text-muted-foreground">
            No content available
          </div>
        ) : currentPage ? (
          <ScrollArea className="flex-1 max-h-[600px] pr-4">
            <div className="text-sm leading-relaxed break-words overflow-x-auto overflow-y-visible markdown-content">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {currentPage.markdown || ""}
              </ReactMarkdown>
            </div>
          </ScrollArea>
        ) : null}
        
        {/* Page navigation controls (bottom) */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between gap-2 mt-3 pt-3 border-t border-border">
            <Button
              variant="outline"
              size="sm"
              onClick={handlePreviousPage}
              disabled={!canGoPreviousPage}
              className="flex items-center gap-1"
            >
              <ChevronLeft className="w-4 h-4" />
              Previous
            </Button>
            <div className="text-xs text-muted-foreground">
              {currentPageIndex + 1} / {totalPages}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleNextPage}
              disabled={!canGoNextPage}
              className="flex items-center gap-1"
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );

  // Render expanded or collapsed view
  if (isExpanded && onMinimize) {
    return (
      <ExpandedContentView
        isExpanded={isExpanded}
        onClose={onMinimize}
        title={currentFile.fileName}
        searchComponent={
          <div className="flex items-center gap-2 w-full max-w-md">
            <div className="relative flex-1">
              <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search in document..."
                className="pl-8"
              />
            </div>
            {matches.length > 0 && (
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handlePreviousMatch}
                  className="h-8 w-8 p-0"
                  title="Previous match"
                >
                  <ArrowUp className="h-3 w-3" />
                </Button>
                <span className="text-xs text-muted-foreground min-w-[60px] text-center">
                  {currentMatchIndex + 1} / {matches.length}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleNextMatch}
                  className="h-8 w-8 p-0"
                  title="Next match"
                >
                  <ArrowDown className="h-3 w-3" />
                </Button>
              </div>
            )}
          </div>
        }
      >
        {expandedContent}
      </ExpandedContentView>
    );
  }

  return collapsedView;
}

