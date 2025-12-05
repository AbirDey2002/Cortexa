import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

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

interface PdfContentMessageProps {
  files: PdfFile[];  // Changed from single file to array
}

export function PdfContentMessage({
  files,
}: PdfContentMessageProps) {
  // Handle single file for backward compatibility
  const fileArray = Array.isArray(files) ? files : [files];
  const totalFiles = fileArray.length;
  
  const [currentFileIndex, setCurrentFileIndex] = useState(0);
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  
  const currentFile = fileArray[currentFileIndex];
  const sortedPages = currentFile ? [...currentFile.pages].sort((a, b) => a.page_number - b.page_number) : [];
  const currentPage = sortedPages[currentPageIndex];
  const totalPages = sortedPages.length;
  
  // Reset page index when file changes
  useEffect(() => {
    setCurrentPageIndex(0);
  }, [currentFileIndex]);
  
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
  
  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] sm:max-w-[90%] md:max-w-[85%] rounded-lg sm:rounded-xl p-3 sm:p-4 overflow-hidden bg-chat-assistant border border-border mr-auto flex flex-col">
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
          <div className="text-xs font-semibold mb-2 text-muted-foreground">
            {currentFile.fileName}
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
}

