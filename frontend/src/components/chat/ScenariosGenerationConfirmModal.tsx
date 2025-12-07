import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface ScenariosGenerationConfirmModalProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ScenariosGenerationConfirmModal: React.FC<ScenariosGenerationConfirmModalProps> = ({ open, onConfirm, onCancel }) => {
  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? onCancel() : undefined)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate Scenarios?</DialogTitle>
          <DialogDescription>
            This will generate test scenarios for all requirements. The process may take some time as scenarios are generated one requirement at a time. You'll be notified when complete.
          </DialogDescription>
        </DialogHeader>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} title="Close without starting scenario generation">Cancel</Button>
          <Button onClick={onConfirm} title="Start scenario generation now">Start Scenario Generation</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

