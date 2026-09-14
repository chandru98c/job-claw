"use client";

import React, { useEffect, useState } from "react";
import { Database, Plus, Trash2, Play, Power, PowerOff, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useTaskStream } from "@/hooks/useTaskStream";

function SavedSearchCard({ 
  search, 
  onToggle, 
  onDelete 
}: { 
  search: any, 
  onToggle: (id: string, enabled: boolean) => void, 
  onDelete: (id: string) => void 
}) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const taskStream = useTaskStream(taskId);

  const handleRun = async () => {
    if (taskStream.isActive) return;
    try {
      const res = await api.post<{task_id: string}>(`/saved-searches/${search.id}/run`);
      setTaskId(res.task_id);
    } catch (err: any) {
      alert(err.message || "Failed to run saved search");
    }
  };

  const isRunning = taskStream.isActive;

  return (
    <div className="bg-zinc-900 border border-white/5 rounded-xl p-5 flex items-center justify-between">
      <div>
        <h2 className="text-xl font-semibold text-white mb-1">{search.name}</h2>
        <div className="text-sm text-zinc-400 flex items-center gap-3">
          <span>Query: {search.query || "Any"}</span>
          <span>Location: {search.location || "Any"}</span>
          {search.remote && <span className="px-2 py-0.5 bg-zinc-800 rounded text-xs">Remote</span>}
        </div>
        <div className="text-xs text-zinc-500 mt-2 flex items-center gap-3">
          <span>Last Run: {search.last_run_at ? new Date(search.last_run_at).toLocaleString() : "Never"}</span>
          {taskId && (
            <span className={`font-medium ${taskStream.status === 'FAILED' ? 'text-red-400' : taskStream.status === 'SUCCEEDED' ? 'text-green-400' : 'text-purple-400'}`}>
              Task: {taskStream.status}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button 
          onClick={() => onToggle(search.id, search.enabled)}
          className={`p-2 rounded-lg transition-colors ${search.enabled ? "bg-green-500/10 text-green-400 hover:bg-green-500/20" : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"}`}
          title={search.enabled ? "Disable" : "Enable"}
        >
          {search.enabled ? <Power className="w-5 h-5" /> : <PowerOff className="w-5 h-5" />}
        </button>
        
        <button 
          onClick={handleRun}
          disabled={isRunning || !search.enabled}
          className="p-2 bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 rounded-lg transition-colors disabled:opacity-50"
          title="Run Now"
        >
          {isRunning ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
        </button>

        <button 
          onClick={() => onDelete(search.id)}
          className="p-2 bg-red-500/10 text-red-400 hover:bg-red-500/20 rounded-lg transition-colors"
          title="Delete"
        >
          <Trash2 className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}

export default function SavedSearchesPage() {
  const [searches, setSearches] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSearches = async () => {
    setLoading(true);
    try {
      const data = await api.get<any[]>("/saved-searches");
      setSearches(data);
    } catch (err: any) {
      setError(err.message || "Failed to load saved searches");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSearches();
  }, []);

  const handleToggle = async (id: string, currentEnabled: boolean) => {
    try {
      await api.patch(`/saved-searches/${id}`, { enabled: !currentEnabled });
      setSearches(s => s.map(x => x.id === id ? { ...x, enabled: !currentEnabled } : x));
    } catch (err: any) {
      alert(err.message || "Failed to toggle saved search");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/saved-searches/${id}`);
      setSearches(s => s.filter(x => x.id !== id));
    } catch (err: any) {
      alert(err.message || "Failed to delete saved search");
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 h-full flex flex-col overflow-y-auto">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Database className="w-8 h-8 text-amber-500" />
          Saved Searches
        </h1>
        <button className="flex items-center gap-2 bg-amber-500 hover:bg-amber-600 text-black px-4 py-2 rounded-md font-semibold transition-colors">
          <Plus className="w-4 h-4" /> New Search
        </button>
      </div>

      <div className="grid gap-4">
        {loading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
          </div>
        ) : error ? (
          <div className="text-center py-12 bg-red-500/10 border border-red-500/20 rounded-xl">
            <AlertCircle className="w-8 h-8 text-red-500 mx-auto mb-4" />
            <p className="text-red-400">{error}</p>
          </div>
        ) : searches.length === 0 ? (
          <div className="text-center py-12 bg-zinc-900/30 border border-white/5 rounded-xl text-zinc-500">
            No saved searches yet.
          </div>
        ) : (
          searches.map(search => (
            <SavedSearchCard 
              key={search.id} 
              search={search} 
              onToggle={handleToggle} 
              onDelete={handleDelete} 
            />
          ))
        )}
      </div>
    </div>
  );
}
