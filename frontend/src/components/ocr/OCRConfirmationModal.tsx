import React, { useState, useEffect } from "react";
import { FileText, AlertCircle, CheckCircle2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Card } from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { apiGet, apiPost } from "@/lib/utils";

interface FileMetadata {
  file_id: string;
  file_name: string;
  file_link: string;
  created_at: string;
  user_id: string;
  usecase_id: string;
}

interface OCRConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (selectedFileId: string) => void;
  usecaseId: string;
}

export const OCRConfirmationModal: React.FC<OCRConfirmationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  usecaseId,
}) => {
  const [files, setFiles] = useState<FileMetadata[]>([]);
  const [selectedFileId, setSelectedFileId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>("");

  // Load files for the usecase
  useEffect(() => {
    if (isOpen && usecaseId) {
      loadFiles();
    }
  }, [isOpen, usecaseId]);

  const loadFiles = async () => {
    try {
      setIsLoading(true);
      setError("");
      const response = await apiGet<FileMetadata[]>(`/files/files/${usecaseId}`);
      setFiles(response);
      
      // Auto-select the first file if only one exists
      if (response.length === 1) {
        setSelectedFileId(response[0].file_id);
      }
    } catch (err) {
      console.error("Error loading files:", err);
      setError("Failed to load files. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = () => {
    if (!selectedFileId) {
      setError("Please select a document to process.");
      return;
    }
    onConfirm(selectedFileId);
  };

  const handleClose = () => {
    setSelectedFileId("");
    setError("");
    onClose();
  };

  const formatFileSize = (fileName: string) => {
    // This is a placeholder - in a real app you'd get file size from metadata
    return "PDF Document";
  };

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleDateString();
    } catch {
      return "Unknown date";
    }
  };

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-y-auto">
        <DialogHeader className="flex flex-row items-center justify-between">
          <DialogTitle className="text-xl font-semibold flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary" />
            OCR Document Processing
          </DialogTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClose}
            className="h-6 w-6 p-0"
          >
            <X className="h-4 w-4" />
          </Button>
        </DialogHeader>

        <div className="space-y-6">
          {/* Status Section */}
          <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5" />
              <div>
                <h3 className="font-medium text-blue-900 dark:text-blue-100 mb-1">
                  OCR Processing Required
                </h3>
                <p className="text-sm text-blue-700 dark:text-blue-300">
                  To extract text from your documents, please select a main document for OCR processing.
                  This will convert the document pages to text that can be analyzed.
                </p>
              </div>
            </div>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-sm text-muted-foreground">Loading documents...</span>
              </div>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
                <span className="text-sm text-red-700 dark:text-red-300">{error}</span>
              </div>
            </div>
          )}

          {/* No Files State */}
          {!isLoading && files.length === 0 && !error && (
            <div className="text-center py-8">
              <FileText className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">No Documents Found</h3>
              <p className="text-sm text-muted-foreground mb-4">
                OCR requires at least 1 document. Please upload a document first.
              </p>
              <Button variant="outline" onClick={handleClose}>
                Close
              </Button>
            </div>
          )}

          {/* File Selection */}
          {!isLoading && files.length > 0 && (
            <>
              <div>
                <h3 className="text-lg font-medium text-foreground mb-3">
                  Select Main Document
                </h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Found {files.length} document{files.length > 1 ? 's' : ''}. 
                  Please select which document should be processed for OCR.
                </p>

                <RadioGroup 
                  value={selectedFileId} 
                  onValueChange={setSelectedFileId}
                  className="space-y-3"
                >
                  {files.map((file, index) => (
                    <div key={file.file_id}>
                      <Label 
                        htmlFor={file.file_id}
                        className="cursor-pointer"
                      >
                        <Card className={`p-4 transition-colors hover:bg-accent/50 ${
                          selectedFileId === file.file_id 
                            ? 'border-primary bg-primary/5' 
                            : 'border-border'
                        }`}>
                          <div className="flex items-center gap-3">
                            <RadioGroupItem 
                              value={file.file_id} 
                              id={file.file_id}
                              className="mt-1"
                            />
                            <FileText className="w-8 h-8 text-primary flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <h4 className="font-medium text-foreground truncate">
                                  {file.file_name}
                                </h4>
                                {index === 0 && (
                                  <Badge variant="secondary" className="text-xs">
                                    Latest
                                  </Badge>
                                )}
                              </div>
                              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                                <span>{formatFileSize(file.file_name)}</span>
                                <span>Uploaded {formatDate(file.created_at)}</span>
                              </div>
                            </div>
                            {selectedFileId === file.file_id && (
                              <CheckCircle2 className="w-5 h-5 text-primary" />
                            )}
                          </div>
                        </Card>
                      </Label>
                    </div>
                  ))}
                </RadioGroup>
              </div>

              {/* Confirmation Section */}
              <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400 mt-0.5" />
                  <div>
                    <h3 className="font-medium text-green-900 dark:text-green-100 mb-1">
                      Ready to Process
                    </h3>
                    <p className="text-sm text-green-700 dark:text-green-300">
                      Once confirmed, the selected document will be processed for text extraction. 
                      You can monitor the progress in the OCR display panel.
                    </p>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <Button variant="outline" onClick={handleClose}>
                  Cancel
                </Button>
                <Button 
                  onClick={handleConfirm}
                  disabled={!selectedFileId}
                  className="min-w-[120px]"
                >
                  Start OCR Processing
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
