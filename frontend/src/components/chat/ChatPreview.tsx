import React from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import Markdown from "react-markdown";

interface ChatPreviewProps {
  content: string;
  title: string;
  onClose: () => void;
}

export const ChatPreview: React.FC<ChatPreviewProps> = ({ content, title, onClose }) => {
  return (
    <div className="flex flex-col h-full bg-[#141518] border-l border-gray-800">
      <div className="flex items-center justify-between border-b border-gray-800 p-4">
        <h3 className="font-semibold text-gray-100">{title}</h3>
        <Button
          variant="ghost"
          size="sm"
          className="p-1 hover:bg-gray-700 hover:text-gray-100 text-gray-400"
          onClick={onClose}
        >
          <X className="h-5 w-5" />
        </Button>
      </div>
      
      <ScrollArea className="flex-1 p-4">
        <div className="prose prose-invert max-w-none prose-headings:text-gray-200 prose-p:text-gray-300">
          <Markdown>{content}</Markdown>
        </div>
      </ScrollArea>
    </div>
  );
};
