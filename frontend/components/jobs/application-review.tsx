import React from "react";
import { Button } from "@/components/ui/button";

export function ApplicationReview({ applicationId }: { applicationId: string }) {
  return (
    <div className="p-4 bg-card border border-white/10 rounded-[24px]">
      <h2 className="text-xl font-bold mb-4 text-white">Application Review</h2>
      <p className="text-muted-foreground mb-4">Reviewing application ID: {applicationId}</p>
      
      <div className="flex gap-4">
        <Button variant="outline">
          Cancel
        </Button>
        <Button>
          Approve & Submit
        </Button>
      </div>
    </div>
  );
}
