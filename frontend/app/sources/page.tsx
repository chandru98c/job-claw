"use client";

import { useEffect, useState } from "react";
import { Database, Loader2, Server, ExternalLink, Globe, Edit, SwitchCamera } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

type SourceResponse = {
  id: string;
  domain: string;
  start_url: string | null;
  is_active: boolean;
  last_run_at: string | null;
  ats_type: string | null;
};

export default function SourcesPage() {
  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [loading, setLoading] = useState(true);
  
  const [createOpen, setCreateOpen] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  
  const [editOpen, setEditOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<SourceResponse | null>(null);

  const fetchSources = async () => {
    try {
      const data: any = await api.get("/sources");
      setSources(data);
    } catch (err) {
      console.error("Failed to fetch sources", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSources();
  }, []);

  const handleCreate = async () => {
    try {
      const source: any = await api.post("/sources", { domain: newDomain });
      setSources([...sources, source]);
      setCreateOpen(false);
      setNewDomain("");
    } catch (err: any) {
      alert("Error creating source: " + (err.message || "Unknown error"));
    }
  };

  const handleEditSave = async () => {
    if (!editingSource) return;
    try {
      const updatedSource: any = await api.patch(`/sources/${editingSource.id}`, {
        domain: editingSource.domain,
        start_url: editingSource.start_url,
        ats_type: editingSource.ats_type,
        is_active: editingSource.is_active
      });
      setSources(sources.map(s => s.id === updatedSource.id ? updatedSource : s));
      setEditOpen(false);
      setEditingSource(null);
    } catch (err: any) {
      alert(`Error updating source: ${err.message || "Unknown error"}`);
    }
  };

  const openEditModal = (source: SourceResponse) => {
    setEditingSource({ ...source });
    setEditOpen(true);
  };

  return (
    <div className="flex flex-col h-full max-w-6xl mx-auto w-full px-6 py-8 overflow-y-auto">
      <div className="flex items-end justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2 mb-2">
            <Database className="w-6 h-6 text-primary" />
            Source Registry
          </h1>
          <p className="text-muted-foreground">Manage companies and trigger on-demand job discovery.</p>
        </div>
        
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger className="px-4 py-2 text-sm font-medium text-black bg-primary rounded-full hover:bg-primary transition-colors">
            + Add Source
          </DialogTrigger>
          <DialogContent className="sm:max-w-md bg-background border-border text-white">
            <DialogHeader>
              <DialogTitle>Add New Source</DialogTitle>
            </DialogHeader>
            <div className="flex flex-col gap-4 py-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">Company Domain *</label>
                <Input value={newDomain} onChange={(e) => setNewDomain(e.target.value)} className="bg-card border-border" placeholder="e.g. greenhouse.io/companyname" />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button className="bg-primary hover:bg-primary text-black" onClick={handleCreate} disabled={!newDomain}>Add</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
      
      {/* Edit Modal */}
      <Dialog open={editOpen} onOpenChange={(open) => { setEditOpen(open); if(!open) setEditingSource(null); }}>
        <DialogContent className="sm:max-w-md bg-background border-border text-white">
          <DialogHeader>
            <DialogTitle>Edit Source</DialogTitle>
          </DialogHeader>
          {editingSource && (
            <div className="flex flex-col gap-4 py-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">Company Domain *</label>
                <Input 
                  value={editingSource.domain} 
                  onChange={(e) => setEditingSource({...editingSource, domain: e.target.value})} 
                  className="bg-card border-border" 
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">Start URL (Optional)</label>
                <Input 
                  value={editingSource.start_url || ""} 
                  onChange={(e) => setEditingSource({...editingSource, start_url: e.target.value})} 
                  className="bg-card border-border" 
                  placeholder="e.g. https://careers.company.com"
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-muted-foreground">ATS Type (Optional)</label>
                <Input 
                  value={editingSource.ats_type || ""} 
                  onChange={(e) => setEditingSource({...editingSource, ats_type: e.target.value})} 
                  className="bg-card border-border" 
                  placeholder="e.g. greenhouse"
                />
              </div>
              <div className="flex items-center justify-between pt-2">
                <label className="text-sm text-muted-foreground">Status</label>
                <div className="flex items-center gap-2">
                  <span className="text-sm">{editingSource.is_active ? "Active" : "Disabled"}</span>
                  <Switch 
                    checked={editingSource.is_active} 
                    onCheckedChange={(checked) => setEditingSource({...editingSource, is_active: checked})}
                  />
                </div>
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditOpen(false)}>Cancel</Button>
            <Button onClick={handleEditSave} disabled={!editingSource?.domain}>Save</Button>
          </div>
        </DialogContent>
      </Dialog>

      <div className="flex-1 bg-card/40 border border-white/[0.05] rounded-[24px] overflow-hidden flex flex-col">
        {loading ? (
          <div className="flex flex-col items-center justify-center flex-1 py-20">
            <Loader2 className="w-8 h-8 text-primary animate-spin mb-4" />
            <p className="text-muted-foreground">Loading sources registry...</p>
          </div>
        ) : (
          <div className="overflow-x-auto overflow-y-auto max-h-[70vh]">
            <table className="w-full text-left text-sm whitespace-nowrap min-w-[600px]">
              <thead className="bg-white/[0.02] border-b border-white/[0.05] sticky top-0 backdrop-blur-md">
                <tr>
                  <th className="px-6 py-4 font-medium text-muted-foreground">Domain</th>
                  <th className="px-6 py-4 font-medium text-muted-foreground">ATS Type</th>
                  <th className="px-6 py-4 font-medium text-muted-foreground">Status</th>
                  <th className="px-6 py-4 font-medium text-muted-foreground">Last Synced</th>
                  <th className="px-6 py-4 font-medium text-muted-foreground text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {sources.map((source) => (
                  <tr key={source.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                          <Globe className="w-4 h-4 text-muted-foreground" />
                          <span className="font-medium text-white">{source.domain}</span>
                        </div>
                        {source.start_url && (
                          <span className="text-xs text-muted-foreground mt-1 truncate max-w-xs">{source.start_url}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {source.ats_type ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-purple-500/10 text-purple-400 text-xs font-medium">
                          <Server className="w-3.5 h-3.5" />
                          {source.ats_type.toUpperCase()}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {source.is_active ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
                          <div className="w-1.5 h-1.5 rounded-full bg-primary" />
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-destructive/10 text-destructive text-xs font-medium">
                          <div className="w-1.5 h-1.5 rounded-full bg-destructive" />
                          Disabled
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-muted-foreground">
                      {source.last_run_at ? new Date(source.last_run_at).toLocaleString() : "Never"}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="ghost" size="icon" onClick={() => openEditModal(source)} className="text-muted-foreground hover:text-foreground hover:bg-white/5 h-8 w-8" title="Edit Source">
                          <Edit className="w-4 h-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-primary hover:bg-primary/10 h-8 w-8" title="Scan Now">
                          <ExternalLink className="w-4 h-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {sources.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                      No sources found in the registry.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
