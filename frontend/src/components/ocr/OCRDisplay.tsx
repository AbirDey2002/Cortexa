import React, { useState, useEffect, useRef } from "react";
import { 
  FileText, 
  Maximize2, 
  Minimize2, 
  X, 
  Clock, 
  CheckCircle2, 
  AlertCircle,
  RefreshCw,
  Eye,
  EyeOff
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { apiGet } from "@/lib/utils";

interface OCRPage {
  page_number: number;
  text: string;
  is_completed: boolean;
  error_msg?: string;
  created_at?: string;
}

interface OCRFile {
  file_id: string;
  file_name: string;
  status: string;
  total_pages: number;
  completed_pages: number;
  error_pages: number;
  progress_percentage: number;
  pages: OCRPage[];
  created_at: string;
}

interface OCRResult {
  usecase_id: string;
  total_files: number;
  total_pages: number;
  completed_pages: number;
  error_pages: number;
  overall_progress_percentage: number;
  overall_status: string;
  files: OCRFile[];
  last_updated: string;
}

interface OCRDisplayProps {
  usecaseId: string;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onClose: () => void;
}

export const OCRDisplay: React.FC<OCRDisplayProps> = ({
  usecaseId,
  isExpanded,
  onToggleExpand,
  onClose,
}) => {
  const [ocrData, setOcrData] = useState<OCRResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [showPreview, setShowPreview] = useState<{[key: string]: boolean}>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Fetch OCR data
  const fetchOCRData = async () => {
    try {
      setError("");
      const response = await apiGet<OCRResult>(`/files/ocr/${usecaseId}/results`);
      setOcrData(response);
      
      // Stop polling if OCR is completed
      if (response.overall_status === "completed") {
        stopPolling();
      }
    } catch (err) {
      console.error("Error fetching OCR data:", err);
      setError("Failed to fetch OCR data");
    }
  };

  // Start polling
  const startPolling = () => {
    stopPolling(); // Clear any existing polling
    pollingRef.current = setInterval(fetchOCRData, 2000);
  };

  // Stop polling
  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  // Initial load and polling setup
  useEffect(() => {
    if (usecaseId) {
      setIsLoading(true);
      fetchOCRData().finally(() => setIsLoading(false));
      startPolling();
    }

    return () => stopPolling();
  }, [usecaseId]);

  // Auto-scroll when new data comes in
  useEffect(() => {
    if (ocrData) {
      setTimeout(scrollToBottom, 100);
    }
  }, [ocrData]);

  const togglePreview = (pageKey: string) => {
    setShowPreview(prev => ({
      ...prev,
      [pageKey]: !prev[pageKey]
    }));
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case "in_progress":
        return <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />;
      case "failed":
        return <AlertCircle className="w-4 h-4 text-red-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const variants: {[key: string]: "default" | "secondary" | "destructive" | "outline"} = {
      completed: "default",
      in_progress: "secondary", 
      failed: "destructive",
      not_started: "outline"
    };
    
    return (
      <Badge variant={variants[status] || "outline"} className="text-xs">
        {status.replace("_", " ").toUpperCase()}
      </Badge>
    );
  };

  const formatTimestamp = (timestamp?: string) => {
    if (!timestamp) return "";
    try {
      return new Date(timestamp).toLocaleTimeString();
    } catch {
      return "";
    }
  };

  if (!ocrData && !isLoading && !error) return null;

  return (
    <Card className={`
      ${isExpanded 
        ? 'fixed top-0 right-0 w-full h-full z-50' 
        : 'w-full max-w-md h-96'
      } 
      bg-background border border-border shadow-lg transition-all duration-300
    `}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border bg-muted/50">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary" />
          <h3 className="font-medium text-foreground">OCR Processing</h3>
          {ocrData && (
            <Badge variant="outline" className="text-xs ml-2">
              {ocrData.completed_pages}/{ocrData.total_pages} pages
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleExpand}
            className="h-8 w-8 p-0"
          >
            {isExpanded ? (
              <Minimize2 className="h-4 w-4" />
            ) : (
              <Maximize2 className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-8 w-8 p-0"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex flex-col h-full">
        <ScrollArea className={`flex-1 p-4 ${isExpanded ? 'h-[calc(100vh-64px)]' : 'h-80'}`}>
          {isLoading && !ocrData && (
            <div className="flex items-center justify-center py-8">
              <div className="flex items-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span className="text-sm text-muted-foreground">Loading OCR data...</span>
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg">
              <AlertCircle className="w-4 h-4 text-red-500" />
              <span className="text-sm text-red-700 dark:text-red-300">{error}</span>
            </div>
          )}

          {ocrData && (
            <div className="space-y-4">
              {/* Overall Progress */}
              <div className="bg-muted/50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">Overall Progress</span>
                  {getStatusBadge(ocrData.overall_status)}
                </div>
                <Progress 
                  value={ocrData.overall_progress_percentage} 
                  className="h-2 mb-2" 
                />
                <div className="text-xs text-muted-foreground">
                  {ocrData.completed_pages} of {ocrData.total_pages} pages completed
                  {ocrData.error_pages > 0 && (
                    <span className="text-red-500 ml-2">
                      ({ocrData.error_pages} errors)
                    </span>
                  )}
                </div>
              </div>

              {/* Files */}
              {ocrData.files.map((file) => (
                <div key={file.file_id} className="border border-border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(file.status)}
                      <span className="font-medium text-sm truncate">
                        {file.file_name}
                      </span>
                    </div>
                    {getStatusBadge(file.status)}
                  </div>

                  <Progress value={file.progress_percentage} className="h-2 mb-2" />
                  <div className="text-xs text-muted-foreground mb-3">
                    {file.completed_pages}/{file.total_pages} pages
                  </div>

                  {/* Pages */}
                  {file.pages.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-muted-foreground">
                        Pages Processed:
                      </div>
                      {file.pages.map((page) => {
                        const pageKey = `${file.file_id}-${page.page_number}`;
                        return (
                          <div key={pageKey} className="bg-background border border-border rounded p-3">
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-medium">
                                  Page {page.page_number}
                                </span>
                                {page.is_completed ? (
                                  <CheckCircle2 className="w-3 h-3 text-green-500" />
                                ) : (
                                  <AlertCircle className="w-3 h-3 text-red-500" />
                                )}
                                {formatTimestamp(page.created_at) && (
                                  <span className="text-xs text-muted-foreground">
                                    {formatTimestamp(page.created_at)}
                                  </span>
                                )}
                              </div>
                              {page.text && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => togglePreview(pageKey)}
                                  className="h-6 px-2 text-xs"
                                >
                                  {showPreview[pageKey] ? (
                                    <><EyeOff className="w-3 h-3 mr-1" /> Hide</>
                                  ) : (
                                    <><Eye className="w-3 h-3 mr-1" /> Preview</>
                                  )}
                                </Button>
                              )}
                            </div>

                            {page.error_msg && (
                              <div className="text-xs text-red-500 mb-2">
                                Error: {page.error_msg}
                              </div>
                            )}

                            {page.text && showPreview[pageKey] && (
                              <div className="mt-2 p-2 bg-muted rounded text-xs font-mono max-h-32 overflow-y-auto">
                                {page.text.substring(0, 500)}
                                {page.text.length > 500 && "..."}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))}

              {/* Status Footer */}
              <div className="text-xs text-muted-foreground text-center pt-2">
                Last updated: {formatTimestamp(ocrData.last_updated)}
                {ocrData.overall_status === "in_progress" && (
                  <span className="ml-2">• Refreshing every 2 seconds</span>
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </ScrollArea>
      </div>
    </Card>
  );
};
