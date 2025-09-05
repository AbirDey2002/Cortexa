import { X, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";

interface FileChipProps {
  file: {
    name: string;
    type: string;
  };
  onRemove: () => void;
}

export function FileChip({ file, onRemove }: FileChipProps) {
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-accent/50 border border-border rounded-lg text-sm">
      <FileText className="w-4 h-4 text-accent-foreground" />
      <span className="font-medium text-accent-foreground max-w-32 truncate">
        {file.name}
      </span>
      <Button
        onClick={onRemove}
        variant="ghost"
        size="sm"
        className="h-4 w-4 p-0 hover:bg-destructive/20 hover:text-destructive"
      >
        <X className="w-3 h-3" />
      </Button>
    </div>
  );
}