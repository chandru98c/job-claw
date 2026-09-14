import React from "react";

export function ApplicationReview({ applicationId }: { applicationId: string }) {
  return (
    <div className="p-4 bg-zinc-900 border border-white/10 rounded-lg">
      <h2 className="text-xl font-bold mb-4 text-white">Application Review</h2>
      <p className="text-zinc-400 mb-4">Reviewing application ID: {applicationId}</p>
      
      <div className="flex gap-4">
        <button className="px-4 py-2 bg-zinc-800 text-white rounded hover:bg-zinc-700">
          Cancel
        </button>
        <button className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-500">
          Approve & Submit
        </button>
      </div>
    </div>
  );
}
