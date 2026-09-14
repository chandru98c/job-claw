"use client";

import React, { useEffect, useState } from "react";
import { Activity, X, Bookmark, Send, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useTaskStream } from "@/hooks/useTaskStream";
import { useRouter } from "next/navigation";

function RecommendationCard({ 
  rec, 
  onAction,
  onDismiss,
  onSave
}: { 
  rec: any, 
  onAction: (id: string, action: string) => void,
  onDismiss: (id: string) => void,
  onSave: (id: string) => void
}) {
  const router = useRouter();
  const [preparing, setPreparing] = useState(false);

  const handlePrepare = async () => {
    setPreparing(true);
    try {
      const res = await api.post<any>(`/recommendations/${rec.id}/action`, { action: "prepare" });
      if (res.application_id) {
        if (res.task_id) {
          router.push(`/applications/${res.application_id}?taskId=${res.task_id}`);
        } else {
          router.push(`/applications/${res.application_id}`);
        }
      } else {
        alert("Failed to get application ID from server");
      }
    } catch (err: any) {
      alert(err.message || "Failed to prepare application");
    } finally {
      setPreparing(false);
    }
  };

  return (
    <div className="bg-zinc-900 border border-white/5 rounded-xl p-5 flex items-center justify-between">
      <div>
        <div className="flex items-center gap-3 mb-1">
          <span className="text-2xl font-bold text-green-400">{rec.score}%</span>
          <span className="text-xs px-2 py-0.5 bg-zinc-800 text-zinc-300 rounded">{rec.state}</span>
        </div>
        <div className="text-sm text-zinc-400">Job ID: {rec.job_id}</div>
        
        {rec.reasons && rec.reasons.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {rec.reasons.map((r: string, i: number) => (
              <span key={i} className="text-xs bg-zinc-800/50 text-zinc-500 px-2 py-1 rounded">
                {r}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <button 
          onClick={handlePrepare}
          className="flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-md text-sm font-semibold transition-colors disabled:opacity-50"
          disabled={rec.state === "APPLIED" || preparing}
        >
          {preparing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          {preparing ? "Preparing..." : "Prepare Application"}
        </button>

        <div className="flex gap-2">
          <button 
            onClick={() => onSave(rec.id)}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-md text-sm transition-colors"
          >
            <Bookmark className="w-4 h-4" /> Save
          </button>
          <button 
            onClick={() => onDismiss(rec.id)}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-1.5 bg-zinc-800 hover:bg-red-500/20 hover:text-red-400 text-zinc-400 rounded-md text-sm transition-colors"
          >
            <X className="w-4 h-4" /> Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

export default function RecommendationsPage() {
  const [recs, setRecs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRecs = async () => {
    setLoading(true);
    try {
      const data = await api.get<any[]>("/recommendations");
      setRecs(data);
    } catch (err: any) {
      setError(err.message || "Failed to load recommendations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecs();
  }, []);

  const handleAction = async (id: string, action: string) => {
    try {
      await api.post(`/recommendations/${id}/action`, { action });
      if (action === "dismiss") {
        setRecs(r => r.filter(x => x.id !== id));
      } else {
        const newState = action === "save" ? "SAVED" : "APPLIED";
        setRecs(r => r.map(x => x.id === id ? { ...x, state: newState } : x));
      }
    } catch (err: any) {
      alert(err.message || "Failed to perform action");
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 h-full flex flex-col overflow-y-auto">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Activity className="w-8 h-8 text-pink-500" />
          Job Recommendations
        </h1>
      </div>

      <div className="grid gap-4">
        {loading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 text-pink-500 animate-spin" />
          </div>
        ) : error ? (
          <div className="text-center py-12 bg-red-500/10 border border-red-500/20 rounded-xl">
            <AlertCircle className="w-8 h-8 text-red-500 mx-auto mb-4" />
            <p className="text-red-400">{error}</p>
          </div>
        ) : recs.length === 0 ? (
          <div className="text-center py-12 bg-zinc-900/30 border border-white/5 rounded-xl text-zinc-500">
            No recommendations yet. Create a saved search to get started.
          </div>
        ) : (
          recs.map(rec => (
            <RecommendationCard 
              key={rec.id} 
              rec={rec} 
              onAction={handleAction}
              onDismiss={(id) => handleAction(id, "dismiss")}
              onSave={(id) => handleAction(id, "save")}
            />
          ))
        )}
      </div>
    </div>
  );
}
