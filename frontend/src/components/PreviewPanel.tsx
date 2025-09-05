import { X, Copy, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";

interface PreviewPanelProps {
  content: string;
  title: string;
  onClose: () => void;
}

export function PreviewPanel({ content, title, onClose }: PreviewPanelProps) {
  const handleCopy = () => {
    navigator.clipboard.writeText(content);
  };

  return (
    <div className="w-full h-full bg-card border-l border-border flex flex-col animate-in slide-in-from-right duration-300">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold text-card-foreground truncate">
            {title}
          </h2>
          <p className="text-sm text-muted-foreground">
            Generated test cases preview
          </p>
        </div>
        
        <div className="flex items-center gap-2 ml-4">
          <Button
            onClick={handleCopy}
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
          >
            <Copy className="w-4 h-4" />
          </Button>
          
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
          >
            <Download className="w-4 h-4" />
          </Button>
          
          <Button
            onClick={onClose}
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0 hover:bg-destructive hover:text-destructive-foreground"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 p-4">
        <Card className="p-6 bg-chat-code border-border">
          <pre className="whitespace-pre-wrap text-sm leading-relaxed text-foreground font-mono">
            {content}
          </pre>
        </Card>
      </ScrollArea>
    </div>
  );
}