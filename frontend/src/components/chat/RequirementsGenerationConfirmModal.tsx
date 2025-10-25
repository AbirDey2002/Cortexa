import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface RequirementsGenerationConfirmModalProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const RequirementsGenerationConfirmModal: React.FC<RequirementsGenerationConfirmModalProps> = ({ open, onConfirm, onCancel }) => {
  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? onCancel() : undefined)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate Requirements?</DialogTitle>
          <DialogDescription>
            This is a crucial workflow step. Once confirmed, any document uploaded after requirement generation will not be included. If you need to upload another document, do it before confirming.
          </DialogDescription>
        </DialogHeader>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} title="Close without starting requirements generation">Cancel</Button>
          <Button onClick={onConfirm} title="Start requirement generation now">Start Requirement Generation</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};


