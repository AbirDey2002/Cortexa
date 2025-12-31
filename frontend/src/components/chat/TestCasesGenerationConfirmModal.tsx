import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface TestCasesGenerationConfirmModalProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const TestCasesGenerationConfirmModal: React.FC<TestCasesGenerationConfirmModalProps> = ({ open, onConfirm, onCancel }) => {
  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? onCancel() : undefined)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate Test Cases?</DialogTitle>
          <DialogDescription>
            This will generate test cases for all scenarios. The process may take some time as test cases are generated one scenario at a time. You'll be notified when complete.
          </DialogDescription>
        </DialogHeader>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} title="Close without starting test case generation">Cancel</Button>
          <Button onClick={onConfirm} title="Start test case generation now">Start Test Case Generation</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

