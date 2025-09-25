import React from "react";
import { Plus, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
  onFileUpload: () => void;
  onKeyPress: (e: React.KeyboardEvent) => void;
  placeholder?: string;
  isDisabled?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  value,
  onChange,
  onSend,
  onFileUpload,
  onKeyPress,
  placeholder = "Describe the feature you want to test...",
  isDisabled = false,
}) => {
  return (
    <div className="w-full max-w-5xl mx-auto px-3">
      <div className="relative flex items-end gap-2 glassmorphism-input rounded-xl p-3 overflow-hidden shadow-lg">
        <Button
          onClick={onFileUpload}
          variant="ghost"
          size="sm"
          className="flex-shrink-0 p-2 hover:bg-gray-800 hover:text-gray-100 text-gray-400"
          disabled={isDisabled}
        >
          <Plus className="w-5 h-5" />
        </Button>
        
        <Textarea
          value={value}
          onChange={onChange}
          onKeyPress={onKeyPress}
          placeholder={placeholder}
          className="flex-1 bg-transparent border-0 resize-none min-h-[20px] max-h-32 text-gray-300 placeholder:text-gray-500 focus-visible:ring-0 focus-visible:outline-none focus:outline-none overflow-hidden text-wrap break-words w-full"
          rows={1}
          disabled={isDisabled}
        />
        
        <Button
          onClick={onSend}
          disabled={!value.trim() || isDisabled}
          variant="ghost"
          size="sm"
          className="flex-shrink-0 p-2 hover:bg-gray-800 hover:text-gray-100 text-gray-400 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-5 h-5" />
        </Button>
      </div>
    </div>
  );
};
