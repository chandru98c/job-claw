"use client";

import React, { useEffect, useState } from "react";
import { Database, Plus, Trash2, Play, Power, PowerOff, Loader2, AlertCircle, Edit } from "lucide-react";
import { api } from "@/lib/api";
import { useTaskStream } from "@/hooks/useTaskStream";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button, buttonVariants } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

function SavedSearchCard({ 
  search, 
  onToggle, 
  onDelete,
  onEdit
}: { 
  search: any, 
  onToggle: (id: string, enabled: boolean) => void, 
  onDelete: (id: string) => void,
  onEdit: (search: any) => void
}) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const taskStream = useTaskStream(taskId);

  useEffect(() => {
    const fetchActiveTask = async () => {
      try {
        const res = await api.get<{task_id: string | null}>(`/tasks/active?worker_type=execute_saved_search_task&target_id=${search.id}`);
        if (res.task_id) {
          setTaskId(res.task_id);
        }
      } catch (err) {
        console.error("Failed to fetch active task for search", search.id, err);
      }
    };
    fetchActiveTask();
  }, [search.id]);

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
    <div className="bg-card border border-border rounded-[24px] p-5 flex items-center justify-between group">
      <div>
        <h2 className="text-xl font-semibold text-white mb-1">{search.name}</h2>
        <div className="text-sm text-muted-foreground flex items-center gap-3">
          <span>Query: {search.query || "Any"}</span>
          <span>Location: {search.location || "Any"}</span>
          {search.remote && <span className="px-2 py-0.5 bg-zinc-800 rounded text-xs">Remote</span>}
        </div>
        <div className="text-xs text-muted-foreground mt-2 flex items-center gap-3">
          <span>Last Run: {search.last_run_at ? new Date(search.last_run_at).toLocaleString() : "Never"}</span>
          {taskId && (
            <span className={`font-medium ${taskStream.status === 'FAILED' ? 'text-destructive' : taskStream.status === 'SUCCEEDED' ? 'text-primary' : 'text-purple-400'}`}>
              Task: {taskStream.status}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button 
          variant="ghost" size="icon"
          onClick={() => onToggle(search.id, search.enabled)}
          className={`rounded-full transition-colors ${search.enabled ? "bg-primary/10 text-primary hover:bg-primary/20" : "bg-card text-muted-foreground hover:bg-card/50"}`}
          title={search.enabled ? "Disable" : "Enable"}
        >
          {search.enabled ? <Power className="w-5 h-5" /> : <PowerOff className="w-5 h-5" />}
        </Button>
        
        <Button 
          variant="ghost" size="icon"
          onClick={() => onEdit(search)}
          className="bg-card text-muted-foreground hover:bg-card/50 hover:text-foreground rounded-full transition-colors"
          title="Edit"
        >
          <Edit className="w-5 h-5" />
        </Button>
        
        <Button 
          variant="ghost" size="icon"
          onClick={handleRun}
          disabled={isRunning || !search.enabled}
          className="bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 rounded-full transition-colors"
          title="Run Now"
        >
          {isRunning ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
        </Button>

        <Button 
          variant="ghost" size="icon"
          onClick={() => onDelete(search.id)}
          className="bg-destructive/10 text-destructive hover:bg-destructive/20 rounded-full transition-colors"
          title="Delete"
        >
          <Trash2 className="w-5 h-5" />
        </Button>
      </div>
    </div>
  );
}

export default function SavedSearchesPage() {
  const [searches, setSearches] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newSearch, setNewSearch] = useState({ name: "", query: "", location: "", remote: true });
  
  const [editOpen, setEditOpen] = useState(false);
  const [editingSearch, setEditingSearch] = useState<any | null>(null);

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

  const handleCreate = async () => {
    try {
      const res = await api.post<any>("/saved-searches", newSearch);
      setSearches([...searches, res]);
      setCreateOpen(false);
      setNewSearch({ name: "", query: "", location: "", remote: true });
    } catch (err: any) {
      alert(err.message || "Failed to create saved search");
    }
  };

  const openEditModal = (search: any) => {
    setEditingSearch({ ...search, remote: !!search.remote });
    setEditOpen(true);
  };

  const handleEditSave = async () => {
    if (!editingSearch) return;
    try {
      const res = await api.patch<any>(`/saved-searches/${editingSearch.id}`, {
        name: editingSearch.name,
        query: editingSearch.query,
        location: editingSearch.location,
        remote: editingSearch.remote
      });
      setSearches(s => s.map(x => x.id === res.id ? res : x));
      setEditOpen(false);
      setEditingSearch(null);
    } catch (err: any) {
      alert(err.message || "Failed to edit saved search");
    }
  };

  return (
    <div className="flex flex-col h-full max-w-6xl mx-auto w-full px-6 py-8 overflow-y-auto">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Database className="w-8 h-8 text-primary" />
          Saved Searches
        </h1>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger className={buttonVariants({ variant: "default" }) + " flex items-center gap-2 rounded-full font-semibold"}>
            <Plus className="w-4 h-4" /> New Search
          </DialogTrigger>
          <DialogContent className="sm:max-w-md bg-background border-border text-white">
            <DialogHeader>
              <DialogTitle>Create Saved Search</DialogTitle>
            </DialogHeader>
            <div className="flex flex-col gap-4 py-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">Name *</label>
                <Input value={newSearch.name} onChange={(e) => setNewSearch({...newSearch, name: e.target.value})} className="bg-card border-border" placeholder="e.g. My Next JS Search" />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">Query (Job Title/Keywords)</label>
                <Input value={newSearch.query} onChange={(e) => setNewSearch({...newSearch, query: e.target.value})} className="bg-card border-border" placeholder="e.g. Software Engineer" />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">Location</label>
                <Input value={newSearch.location} onChange={(e) => setNewSearch({...newSearch, location: e.target.value})} className="bg-card border-border" placeholder="e.g. Remote, NY" />
              </div>
              <div className="flex items-center justify-between pt-2">
                <label className="text-sm text-muted-foreground">Remote Only</label>
                <Switch checked={newSearch.remote} onCheckedChange={(checked) => setNewSearch({...newSearch, remote: checked})} />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button onClick={handleCreate} disabled={!newSearch.name}>Create</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
      
      {/* Edit Modal */}
      <Dialog open={editOpen} onOpenChange={(open) => { setEditOpen(open); if(!open) setEditingSearch(null); }}>
        <DialogContent className="sm:max-w-md bg-background border-border text-white">
          <DialogHeader>
            <DialogTitle>Edit Saved Search</DialogTitle>
          </DialogHeader>
          {editingSearch && (
            <div className="flex flex-col gap-4 py-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">Name *</label>
                <Input value={editingSearch.name} onChange={(e) => setEditingSearch({...editingSearch, name: e.target.value})} className="bg-card border-border" />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">Query (Job Title/Keywords)</label>
                <Input value={editingSearch.query || ""} onChange={(e) => setEditingSearch({...editingSearch, query: e.target.value})} className="bg-card border-border" />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">Location</label>
                <Input value={editingSearch.location || ""} onChange={(e) => setEditingSearch({...editingSearch, location: e.target.value})} className="bg-card border-border" />
              </div>
              <div className="flex items-center justify-between pt-2">
                <label className="text-sm text-muted-foreground">Remote Only</label>
                <Switch checked={editingSearch.remote} onCheckedChange={(checked) => setEditingSearch({...editingSearch, remote: checked})} />
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditOpen(false)}>Cancel</Button>
            <Button onClick={handleEditSave} disabled={!editingSearch?.name}>Save</Button>
          </div>
        </DialogContent>
      </Dialog>

      <div className="grid gap-4">
        {loading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 text-primary animate-spin" />
          </div>
        ) : error ? (
          <div className="text-center py-12 bg-destructive/10 border border-destructive/20 rounded-[24px]">
            <AlertCircle className="w-8 h-8 text-destructive mx-auto mb-4" />
            <p className="text-destructive">{error}</p>
          </div>
        ) : searches.length === 0 ? (
          <div className="text-center py-12 bg-card/30 border border-border rounded-[24px] text-muted-foreground">
            No saved searches yet.
          </div>
        ) : (
          searches.map(search => (
            <SavedSearchCard 
              key={search.id} 
              search={search} 
              onToggle={handleToggle} 
              onDelete={handleDelete} 
              onEdit={openEditModal}
            />
          ))
        )}
      </div>
    </div>
  );
}
