"use client";

import { useEffect, useState, useCallback } from "react";
import { 
  Database, 
  Loader2, 
  Server, 
  ExternalLink, 
  Globe, 
  Edit, 
  Trash2, 
  Search, 
  Play, 
  Plus, 
  RefreshCw, 
  ChevronLeft, 
  ChevronRight, 
  CheckCircle2, 
  AlertTriangle,
  Wrench,
  Activity,
  Check
} from "lucide-react";
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
  job_count: number;
  consecutive_failures: number;
  last_error: string | null;
  circuit_status: string | null;
  last_status_code: number | null;
  last_success_at: string | null;
  last_failure_at: string | null;
};

type SourceStats = {
  total_sources: number;
  active_sources: number;
  inactive_sources: number;
  working_sources: number;
  failing_sources: number;
  pending_sources?: number;
  total_jobs: number;
  ats_counts: Record<string, number>;
};

const ATS_FILTERS = [
  { id: "all", label: "All ATS" },
  { id: "zohorecruit", label: "Zoho Recruit" },
  { id: "greenhouse", label: "Greenhouse" },
  { id: "ashby", label: "Ashby" },
  { id: "lever", label: "Lever" },
  { id: "keka", label: "Keka HR" },
  { id: "workable", label: "Workable" },
  { id: "bamboohr", label: "BambooHR" },
  { id: "recruitee", label: "Recruitee" },
  { id: "teamtailor", label: "Teamtailor" },
  { id: "personio", label: "Personio" },
  { id: "smartrecruiters", label: "SmartRecruiters" },
  { id: "breezy", label: "Breezy HR" },
  { id: "workday", label: "Workday" },
  { id: "custom", label: "Custom / Direct" },
];

export default function SourcesPage() {
  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [stats, setStats] = useState<SourceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanningId, setScanningId] = useState<string | null>(null);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [fixingFailing, setFixingFailing] = useState(false);
  const [scanningPending, setScanningPending] = useState(false);
  const [pendingScanBatch, setPendingScanBatch] = useState<number>(100);

  // Pagination & Filtering
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(25);
  const [limitInput, setLimitInput] = useState<string>("25");
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [search, setSearch] = useState("");
  const [selectedAts, setSelectedAts] = useState("all");
  const [registryStatus, setRegistryStatus] = useState<string>("all"); // "all", "working", "failing", "pending", "inactive"

  useEffect(() => {
    setLimitInput(limit.toString());
  }, [limit]);

  const handleLimitCommit = () => {
    const parsed = parseInt(limitInput.trim(), 10);
    if (!isNaN(parsed) && parsed > 0) {
      const clamped = Math.min(Math.max(1, parsed), 200);
      setLimit(clamped);
      setLimitInput(clamped.toString());
      setPage(1);
    } else {
      setLimitInput(limit.toString());
    }
  };

  // Modals
  const [createOpen, setCreateOpen] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [newAtsType, setNewAtsType] = useState("");
  const [newStartUrl, setNewStartUrl] = useState("");

  const [editOpen, setEditOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<SourceResponse | null>(null);

  const fetchStats = async () => {
    try {
      const data: any = await api.get("/sources/stats");
      setStats(data);
    } catch (err) {
      console.error("Failed to fetch sources stats", err);
    }
  };

  const fetchSources = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString(),
      });
      if (search.trim()) params.append("search", search.trim());
      if (selectedAts && selectedAts !== "all") params.append("ats_type", selectedAts);
      if (registryStatus && registryStatus !== "all") {
        if (registryStatus === "inactive") {
          params.append("is_active", "false");
        } else {
          params.append("registry_status", registryStatus);
        }
      }

      const res: any = await api.get(`/sources?${params.toString()}`);
      if (res && res.items) {
        setSources(res.items);
        setTotalCount(res.total);
        setTotalPages(res.pages || 1);
      } else if (Array.isArray(res)) {
        setSources(res);
        setTotalCount(res.length);
        setTotalPages(1);
      }
    } catch (err) {
      console.error("Failed to fetch sources", err);
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, selectedAts, registryStatus]);

  useEffect(() => {
    fetchStats();
    fetchSources();
  }, [fetchSources]);

  const handleCreate = async () => {
    try {
      const payload: any = { domain: newDomain.trim() };
      if (newStartUrl.trim()) payload.start_url = newStartUrl.trim();
      if (newAtsType.trim()) payload.ats_type = newAtsType.trim();

      await api.post("/sources", payload);
      setCreateOpen(false);
      setNewDomain("");
      setNewStartUrl("");
      setNewAtsType("");
      fetchStats();
      fetchSources();
    } catch (err: any) {
      alert("Error creating source: " + (err.message || "Unknown error"));
    }
  };

  const handleEditSave = async () => {
    if (!editingSource) return;
    try {
      await api.patch(`/sources/${editingSource.id}`, {
        domain: editingSource.domain,
        start_url: editingSource.start_url,
        ats_type: editingSource.ats_type,
        is_active: editingSource.is_active,
      });
      setEditOpen(false);
      setEditingSource(null);
      fetchSources();
    } catch (err: any) {
      alert(`Error updating source: ${err.message || "Unknown error"}`);
    }
  };

  const handleToggle = async (id: string) => {
    try {
      await api.post(`/sources/${id}/toggle`);
      setSources((prev) =>
        prev.map((s) => (s.id === id ? { ...s, is_active: !s.is_active } : s))
      );
      fetchStats();
    } catch (err: any) {
      alert("Failed to toggle source: " + (err.message || "Unknown error"));
    }
  };

  const handleScan = async (source: SourceResponse) => {
    setScanningId(source.id);
    setScanMessage(`Triggering discovery scan for ${source.domain}...`);
    try {
      await api.post(`/sources/${source.id}/scan`);
      setScanMessage(`Discovery scan launched for ${source.domain}! Analyzing board...`);
      setTimeout(() => {
        fetchStats();
        fetchSources();
        setScanMessage(null);
      }, 3500);
    } catch (err: any) {
      alert("Failed to trigger scan: " + (err.message || "Unknown error"));
      setScanMessage(null);
    } finally {
      setScanningId(null);
    }
  };

  const handleFixFailing = async () => {
    setFixingFailing(true);
    setScanMessage("Launching automated re-scans and diagnostic fixes for failing sources...");
    try {
      const res: any = await api.post("/sources/fix-failing?limit=25");
      setScanMessage(res.message || "Diagnostic scans queued!");
      setTimeout(() => {
        fetchStats();
        fetchSources();
        setScanMessage(null);
      }, 5000);
    } catch (err: any) {
      alert("Failed to fix failing sources: " + (err.message || "Unknown error"));
      setScanMessage(null);
    } finally {
      setFixingFailing(false);
    }
  };

  const handleScanPending = async (batchSize = 100) => {
    setScanningPending(true);
    setScanMessage(`Triggering bulk real discovery scans on ${batchSize} pending sources...`);
    try {
      const params = new URLSearchParams({ limit: batchSize.toString() });
      if (selectedAts && selectedAts !== "all") {
        params.append("ats_type", selectedAts);
      }
      const res: any = await api.post(`/sources/scan-pending?${params.toString()}`);
      setScanMessage(res.message || `Queued ${res.queued} pending sources for discovery scanning!`);
      setTimeout(() => {
        fetchStats();
        fetchSources();
      }, 3500);
    } catch (err: any) {
      alert("Failed to queue pending scans: " + (err.message || "Unknown error"));
      setScanMessage(null);
    } finally {
      setScanningPending(false);
    }
  };

  const handleDelete = async (id: string, domain: string) => {
    if (!confirm(`Are you sure you want to remove ${domain} from the registry?`)) return;
    try {
      await api.delete(`/sources/${id}`);
      setSources((prev) => prev.filter((s) => s.id !== id));
      fetchStats();
    } catch (err: any) {
      alert("Failed to delete source: " + (err.message || "Unknown error"));
    }
  };

  return (
    <div className="flex flex-col max-w-6xl mx-auto w-full px-4 sm:px-6 py-8 relative">
      {/* Ambient Top Glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[850px] h-[300px] bg-gradient-to-b from-[#c8f542]/[0.07] via-[#c8f542]/[0.02] to-transparent blur-3xl pointer-events-none -z-10" />

      {/* Top Header & Overview */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2.5">
            <Database className="w-7 h-7 text-[#c8f542] shrink-0" />
            Source Registry
            <span className="text-xs sm:text-sm font-semibold px-2.5 py-0.5 rounded-full bg-[#c8f542]/10 border border-[#c8f542]/30 text-[#c8f542] font-mono">
              {(stats?.total_sources || totalCount).toLocaleString()} total sources
            </span>
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Verified employer career boards and monitored ATS endpoints.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button
            id="refresh-sources-btn"
            variant="outline"
            size="sm"
            onClick={() => {
              fetchStats();
              fetchSources();
            }}
            className="h-9 gap-1.5 border-white/10 text-xs hover:border-[#c8f542]/40 hover:text-[#c8f542] bg-card/40 backdrop-blur-md"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>

          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger className="inline-flex items-center gap-1.5 px-4 h-9 text-xs font-bold text-black bg-[#c8f542] hover:bg-[#d8ff4e] rounded-xl shadow-md transition-all hover:scale-105 cursor-pointer">
              <Plus className="w-4 h-4" /> Add Source
            </DialogTrigger>
            <DialogContent className="sm:max-w-md bg-card/95 border-border backdrop-blur-2xl text-white">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Plus className="w-5 h-5 text-[#c8f542]" />
                  Add New Career Source
                </DialogTitle>
              </DialogHeader>
              <div className="flex flex-col gap-4 py-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs text-muted-foreground">Company Identifier / Domain *</label>
                  <Input
                    value={newDomain}
                    onChange={(e) => setNewDomain(e.target.value)}
                    className="bg-zinc-900 border-white/10"
                    placeholder="e.g. zohorecruit.com/zoho or greenhouse.io/stripe"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs text-muted-foreground">Start / Careers URL (Optional)</label>
                  <Input
                    value={newStartUrl}
                    onChange={(e) => setNewStartUrl(e.target.value)}
                    className="bg-zinc-900 border-white/10"
                    placeholder="https://careers.company.com"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs text-muted-foreground">ATS Platform Type (Optional)</label>
                  <Input
                    value={newAtsType}
                    onChange={(e) => setNewAtsType(e.target.value)}
                    className="bg-zinc-900 border-white/10"
                    placeholder="e.g. zohorecruit, greenhouse, ashby, lever"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setCreateOpen(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  className="bg-[#c8f542] hover:bg-[#d8ff4e] text-black font-semibold"
                  onClick={handleCreate}
                  disabled={!newDomain.trim()}
                >
                  Add to Registry
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Real-Time Stats Overview: 4-Card Balanced Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-2.5">
        {/* Card 1: Total Registry */}
        <div 
          onClick={() => { setRegistryStatus("all"); setPage(1); }}
          className={`px-3 py-2 rounded-xl border transition-all cursor-pointer backdrop-blur-md flex flex-col justify-between ${
            registryStatus === "all"
              ? "bg-white/[0.08] border-white/30 shadow-md"
              : "bg-card/40 border-white/10 hover:border-white/20"
          }`}
        >
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Total Registry</span>
            <Database className="w-3 h-3 text-zinc-400" />
          </div>
          <div className="flex items-baseline justify-between gap-1.5 mt-0.5">
            <span className="text-lg font-bold text-white font-mono">
              {(stats?.total_sources ?? totalCount ?? 0).toLocaleString()}
            </span>
            <span className="text-[10px] text-zinc-400 truncate">Total Boards</span>
          </div>
        </div>

        {/* Card 2: Working Registry */}
        <div 
          onClick={() => { setRegistryStatus("working"); setPage(1); }}
          className={`px-3 py-2 rounded-xl border transition-all cursor-pointer backdrop-blur-md relative overflow-hidden flex flex-col justify-between ${
            registryStatus === "working"
              ? "bg-[#c8f542]/15 border-[#c8f542] shadow-[0_0_15px_rgba(200,245,66,0.15)]"
              : "bg-card/40 border-emerald-500/20 hover:border-emerald-500/40 hover:bg-emerald-500/[0.04]"
          }`}
        >
          <div className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center justify-between">
            <span className="flex items-center gap-1 font-bold">
              <CheckCircle2 className="w-3 h-3" /> Working
            </span>
            <span className="font-mono text-[9px] px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-300 font-normal">
              {(stats?.total_jobs ?? 0).toLocaleString()} Jobs
            </span>
          </div>
          <div className="flex items-baseline justify-between gap-1.5 mt-0.5">
            <span className="text-lg font-bold text-[#c8f542] font-mono">
              {(stats?.working_sources ?? 0).toLocaleString()}
            </span>
            <span className="text-[10px] text-emerald-300/80 truncate">Verified active</span>
          </div>
        </div>

        {/* Card 3: Pending Scan */}
        <div 
          onClick={() => { setRegistryStatus("pending"); setPage(1); }}
          className={`px-3 py-2 rounded-xl border transition-all cursor-pointer backdrop-blur-md relative overflow-hidden flex flex-col justify-between ${
            registryStatus === "pending"
              ? "bg-amber-400/15 border-amber-400 shadow-[0_0_15px_rgba(251,191,36,0.15)]"
              : "bg-card/40 border-amber-500/20 hover:border-amber-500/40 hover:bg-amber-500/[0.04]"
          }`}
        >
          <div className="text-[10px] font-semibold text-amber-300 uppercase tracking-wider flex items-center justify-between">
            <span className="flex items-center gap-1 font-bold">
              <Activity className="w-3 h-3 text-amber-300" /> Pending Scan
            </span>
            <span className="font-mono text-[9px] px-1.5 py-0.2 rounded-full bg-amber-500/20 text-amber-300 font-normal">
              Ready
            </span>
          </div>
          <div className="flex items-baseline justify-between gap-1.5 mt-0.5">
            <span className="text-lg font-bold text-amber-300 font-mono">
              {(stats?.pending_sources ?? 0).toLocaleString()}
            </span>
            <span className="text-[10px] text-amber-300/80 truncate">Queued for scan</span>
          </div>
        </div>

        {/* Card 4: Not Working / Errors */}
        <div 
          onClick={() => { setRegistryStatus("failing"); setPage(1); }}
          className={`px-3 py-2 rounded-xl border transition-all cursor-pointer backdrop-blur-md relative overflow-hidden flex flex-col justify-between ${
            registryStatus === "failing"
              ? "bg-rose-500/15 border-rose-500 shadow-[0_0_15px_rgba(244,63,94,0.15)]"
              : "bg-card/40 border-rose-500/20 hover:border-rose-500/40 hover:bg-rose-500/[0.04]"
          }`}
        >
          <div className="text-[10px] font-semibold text-rose-400 uppercase tracking-wider flex items-center justify-between">
            <span className="flex items-center gap-1 font-bold">
              <AlertTriangle className="w-3 h-3" /> Not Working
            </span>
            <span className="font-mono text-[9px] px-1.5 py-0.2 rounded-full bg-rose-500/20 text-rose-300 font-normal">
              Needs Fix
            </span>
          </div>
          <div className="flex items-baseline justify-between gap-1.5 mt-0.5">
            <span className="text-lg font-bold text-rose-400 font-mono">
              {(stats?.failing_sources ?? 0).toLocaleString()}
            </span>
            <span className="text-[10px] text-rose-300/80 truncate">Errors logged</span>
          </div>
        </div>
      </div>

      {/* Exact Math Balance & Transparency Bar */}
      <div className="flex items-center justify-between px-3.5 py-2 rounded-xl bg-zinc-950/70 border border-white/[0.08] text-[11px] text-zinc-400 mb-4 font-mono shadow-inner">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-zinc-500 uppercase tracking-wider text-[10px] font-bold">Registry Breakdown:</span>
          <span className="text-emerald-400 font-bold bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">{(stats?.working_sources ?? 0).toLocaleString()} Working</span>
          <span className="text-zinc-600 font-bold">+</span>
          <span className="text-amber-300 font-bold bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">{(stats?.pending_sources ?? 0).toLocaleString()} Pending</span>
          <span className="text-zinc-600 font-bold">+</span>
          <span className="text-rose-400 font-bold bg-rose-500/10 px-1.5 py-0.5 rounded border border-rose-500/20">{(stats?.failing_sources ?? 0).toLocaleString()} Not Working</span>
          <span className="text-zinc-600 font-bold">=</span>
          <span className="text-white font-extrabold bg-white/10 px-2 py-0.5 rounded border border-white/20">{(stats?.total_sources ?? totalCount ?? 0).toLocaleString()} Total Boards</span>
        </div>
        <div className="hidden md:flex items-center gap-2 text-zinc-400 text-[10px]">
          <Server className="w-3 h-3 text-purple-400" />
          <span>{stats ? Object.keys(stats.ats_counts).length : 17} Supported ATS Engines</span>
        </div>
      </div>

      {/* Registry Health & Quick Filter Tab Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground mr-1 uppercase font-semibold text-[10px]">Filter View:</span>
          
          <button
            onClick={() => { setRegistryStatus("all"); setPage(1); }}
            className={`px-3 py-1 rounded-full text-xs transition-all cursor-pointer font-medium border ${
              registryStatus === "all"
                ? "bg-white text-black font-bold border-white"
                : "bg-card/40 border-white/10 text-zinc-300 hover:border-white/30"
            }`}
          >
            All Registry ({(stats?.total_sources ?? totalCount ?? 0).toLocaleString()})
          </button>

          <button
            onClick={() => { setRegistryStatus("working"); setPage(1); }}
            className={`px-3 py-1 rounded-full text-xs transition-all cursor-pointer font-medium border flex items-center gap-1.5 ${
              registryStatus === "working"
                ? "bg-[#c8f542] text-black font-bold border-[#c8f542] shadow-[0_0_12px_rgba(200,245,66,0.3)]"
                : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20"
            }`}
          >
            <CheckCircle2 className="w-3 h-3" />
            Working ({(stats?.working_sources ?? 0).toLocaleString()})
          </button>

          <button
            onClick={() => { setRegistryStatus("pending"); setPage(1); }}
            className={`px-3 py-1 rounded-full text-xs transition-all cursor-pointer font-medium border flex items-center gap-1.5 ${
              registryStatus === "pending"
                ? "bg-amber-400 text-black font-bold border-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.3)]"
                : "bg-amber-500/10 border-amber-500/30 text-amber-300 hover:bg-amber-500/20"
            }`}
          >
            <Activity className="w-3 h-3" />
            Pending Scan ({(stats?.pending_sources ?? 0).toLocaleString()})
          </button>

          <button
            onClick={() => { setRegistryStatus("failing"); setPage(1); }}
            className={`px-3 py-1 rounded-full text-xs transition-all cursor-pointer font-medium border flex items-center gap-1.5 ${
              registryStatus === "failing"
                ? "bg-rose-500 text-white font-bold border-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.3)]"
                : "bg-rose-500/10 border-rose-500/30 text-rose-400 hover:bg-rose-500/20"
            }`}
          >
            <AlertTriangle className="w-3 h-3" />
            Not Working ({(stats?.failing_sources ?? 0).toLocaleString()})
          </button>
        </div>

        {/* Action Buttons for Filter Views */}
        <div className="flex items-center gap-2">
          {/* Bulk Discovery Scan for Pending */}
          {registryStatus === "pending" && (
            <div className="flex items-center gap-1.5">
              <select
                value={pendingScanBatch}
                onChange={(e) => setPendingScanBatch(Number(e.target.value))}
                className="h-8 px-2 text-xs bg-zinc-900 border border-amber-500/30 text-amber-300 rounded-xl focus:outline-none cursor-pointer"
              >
                <option value={50}>Batch: 50</option>
                <option value={100}>Batch: 100</option>
                <option value={250}>Batch: 250</option>
                <option value={500}>Batch: 500</option>
              </select>
              <Button
                id="bulk-scan-pending-btn"
                size="sm"
                onClick={() => handleScanPending(pendingScanBatch)}
                disabled={scanningPending}
                className="h-8 gap-1.5 bg-amber-400 hover:bg-amber-300 text-black font-extrabold text-xs rounded-xl shadow-md cursor-pointer transition-all hover:scale-105"
              >
                {scanningPending ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Play className="w-3.5 h-3.5 text-black fill-black" />
                )}
                Bulk Discovery Scan
              </Button>
            </div>
          )}

          {/* Auto-Fix Failing Button */}
          {registryStatus === "failing" && (
            <Button
              size="sm"
              onClick={handleFixFailing}
              disabled={fixingFailing}
              className="h-8 gap-1.5 bg-rose-500 hover:bg-rose-600 text-white font-bold text-xs rounded-xl shadow-md cursor-pointer transition-all hover:scale-105"
            >
              {fixingFailing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Wrench className="w-3.5 h-3.5" />
              )}
              Auto-Fix & Retry Failing Sources
            </Button>
          )}
        </div>
      </div>

      {/* Search & Filter Toolbar */}
      <div className="flex flex-col gap-3 p-3.5 rounded-2xl bg-card/40 border border-white/10 backdrop-blur-md mb-6">
        {/* Search Input */}
        <div className="relative w-full">
          <Search className="absolute left-3.5 top-3 h-4 w-4 text-muted-foreground" />
          <input
            id="source-search-input"
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search source by domain, company, or URL..."
            className="w-full bg-zinc-950/70 border border-white/10 rounded-xl pl-10 pr-4 py-2 text-xs text-white placeholder:text-muted-foreground focus:outline-none focus:border-[#c8f542]/70 focus:ring-1 focus:ring-[#c8f542]/30 transition-all"
          />
        </div>

        {/* ATS Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-white/[0.04] text-xs">
          <span className="text-muted-foreground text-[11px] font-medium uppercase mr-1">ATS:</span>
          {ATS_FILTERS.map((f) => {
            const active = selectedAts === f.id;
            const count = stats?.ats_counts?.[f.id];
            return (
              <button
                key={f.id}
                onClick={() => {
                  setSelectedAts(f.id);
                  setPage(1);
                }}
                className={`px-2.5 py-0.5 rounded-full border text-[11px] cursor-pointer transition-all flex items-center gap-1 ${
                  active
                    ? "bg-[#c8f542] text-black font-bold border-[#c8f542] shadow-[0_0_8px_rgba(200,245,66,0.2)]"
                    : "bg-white/[0.04] border-white/10 text-zinc-400 hover:text-white hover:bg-white/[0.08]"
                }`}
              >
                <span>{f.label}</span>
                {count !== undefined && (
                  <span
                    className={`font-mono text-[9px] px-1 rounded-full ${
                      active ? "bg-black/20 text-black font-bold" : "bg-white/10 text-zinc-400"
                    }`}
                  >
                    {count.toLocaleString()}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {scanMessage && (
        <div className="mb-4 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center gap-2 animate-fade-in shadow-md">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-[#c8f542]" />
          <span>{scanMessage}</span>
        </div>
      )}

      {/* Edit Modal */}
      <Dialog
        open={editOpen}
        onOpenChange={(open) => {
          setEditOpen(open);
          if (!open) setEditingSource(null);
        }}
      >
        <DialogContent className="sm:max-w-md bg-card/95 border-border backdrop-blur-2xl text-white">
          <DialogHeader>
            <DialogTitle>Edit Source Configuration</DialogTitle>
          </DialogHeader>
          {editingSource && (
            <div className="flex flex-col gap-4 py-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">Company Identifier / Domain *</label>
                <Input
                  value={editingSource.domain}
                  onChange={(e) =>
                    setEditingSource({ ...editingSource, domain: e.target.value })
                  }
                  className="bg-zinc-900 border-white/10 text-xs"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">Start URL (Optional)</label>
                <Input
                  value={editingSource.start_url || ""}
                  onChange={(e) =>
                    setEditingSource({ ...editingSource, start_url: e.target.value })
                  }
                  className="bg-zinc-900 border-white/10 text-xs"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">ATS Platform Type</label>
                <Input
                  value={editingSource.ats_type || ""}
                  onChange={(e) =>
                    setEditingSource({ ...editingSource, ats_type: e.target.value })
                  }
                  className="bg-zinc-900 border-white/10 text-xs"
                />
              </div>
              <div className="flex items-center justify-between pt-2">
                <span className="text-xs text-zinc-300">Active Engine Status</span>
                <Switch
                  checked={editingSource.is_active}
                  onCheckedChange={(checked) =>
                    setEditingSource({ ...editingSource, is_active: checked })
                  }
                />
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              className="bg-[#c8f542] hover:bg-[#d8ff4e] text-black font-semibold"
              onClick={handleEditSave}
            >
              Save Changes
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Source Registry Table */}
      <div className="rounded-2xl border border-white/10 bg-card/30 backdrop-blur-md overflow-hidden shadow-xl">
        {loading ? (
          <div className="p-16 flex flex-col items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="w-7 h-7 animate-spin text-[#c8f542]" />
            <p className="text-xs font-mono">Loading registry entries...</p>
          </div>
        ) : sources.length === 0 ? (
          <div className="p-16 flex flex-col items-center justify-center gap-3 text-center">
            <Database className="w-10 h-10 text-zinc-600" />
            <h3 className="text-sm font-bold text-white">No sources found</h3>
            <p className="text-xs text-muted-foreground max-w-sm">
              No career boards match the current search or status filter.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSearch("");
                setSelectedAts("all");
                setRegistryStatus("all");
              }}
              className="mt-2 text-xs border-white/10"
            >
              Reset Filters
            </Button>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs whitespace-nowrap">
                <thead className="bg-white/[0.03] border-b border-white/10">
                  <tr>
                    <th className="px-5 py-3.5 font-semibold text-zinc-400">Domain / Identifier</th>
                    <th className="px-5 py-3.5 font-semibold text-zinc-400">ATS Engine</th>
                    <th className="px-5 py-3.5 font-semibold text-zinc-400">Registry Status</th>
                    <th className="px-5 py-3.5 font-semibold text-zinc-400">Health</th>
                    <th className="px-5 py-3.5 font-semibold text-zinc-400">Last Swept</th>
                    <th className="px-5 py-3.5 font-semibold text-zinc-400 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {sources.map((source) => (
                    <tr key={source.id} className="hover:bg-white/[0.02] transition-colors group">
                      <td className="px-5 py-3.5">
                        <div className="flex flex-col">
                          <div className="flex items-center gap-2">
                            <Globe className="w-3.5 h-3.5 text-zinc-500 group-hover:text-[#c8f542] transition-colors" />
                            <span className="font-semibold text-zinc-200 group-hover:text-white transition-colors">
                              {source.domain}
                            </span>
                          </div>
                          {source.start_url && (
                            <a
                              href={source.start_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[11px] text-zinc-400 hover:text-[#c8f542] mt-0.5 truncate max-w-sm flex items-center gap-1 transition-colors"
                            >
                              <span>{source.start_url}</span>
                              <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                            </a>
                          )}
                        </div>
                      </td>

                      <td className="px-5 py-3.5">
                        {source.ats_type ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20 text-[10px] font-mono uppercase tracking-wider font-semibold">
                            <Server className="w-3 h-3" />
                            {source.ats_type}
                          </span>
                        ) : (
                          <span className="text-zinc-400 text-[11px] font-mono">Custom ATS</span>
                        )}
                      </td>

                      {/* Registry Status Column: Working vs Not Working */}
                      <td className="px-5 py-3.5">
                        {source.job_count > 0 ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 font-bold text-[11px] shadow-sm">
                            <CheckCircle2 className="w-3 h-3" />
                            Working ({source.job_count} Jobs)
                          </span>
                        ) : source.consecutive_failures > 0 || source.last_error ? (
                          <div className="flex flex-col gap-0.5 max-w-xs">
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-500/15 border border-rose-500/30 text-rose-400 font-semibold text-[10px] w-fit">
                              <AlertTriangle className="w-3 h-3" />
                              Not Working ({source.consecutive_failures || 1} fails)
                            </span>
                            {source.last_error && (
                              <span 
                                className="text-[10px] text-rose-300/80 truncate block" 
                                title={source.last_error}
                              >
                                {source.last_error}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-zinc-800/80 border border-white/10 text-zinc-400 text-[10px]">
                            Ready / Idle
                          </span>
                        )}
                      </td>

                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <Switch
                            checked={source.is_active}
                            onCheckedChange={() => handleToggle(source.id)}
                            className="scale-75"
                            title={source.is_active ? "Click to Disable" : "Click to Enable"}
                          />
                          <span
                            className={`text-[11px] font-medium ${
                              source.is_active ? "text-emerald-400" : "text-zinc-400"
                            }`}
                          >
                            {source.is_active ? "Active" : "Disabled"}
                          </span>
                        </div>
                      </td>

                      <td className="px-5 py-3.5 text-zinc-400 font-mono text-[11px]">
                        {source.last_run_at ? new Date(source.last_run_at).toLocaleString() : "Never swept"}
                      </td>

                      <td className="px-5 py-3.5 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Scan Now Action */}
                          <button
                            onClick={() => handleScan(source)}
                            disabled={scanningId === source.id || !source.is_active}
                            className={`p-1.5 rounded-lg border transition-all cursor-pointer ${
                              source.job_count === 0 && (source.consecutive_failures > 0 || source.last_error)
                                ? "border-rose-500/30 hover:border-rose-500 bg-rose-500/10 text-rose-400"
                                : "border-white/10 hover:border-[#c8f542]/40 bg-card hover:bg-[#c8f542]/10 text-zinc-400 hover:text-[#c8f542]"
                            }`}
                            title="Trigger Real Discovery Scan Now"
                          >
                            {scanningId === source.id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-[#c8f542]" />
                            ) : (
                              <Play className="w-3.5 h-3.5" />
                            )}
                          </button>

                          {/* Edit Source */}
                          <button
                            onClick={() => {
                              setEditingSource({ ...source });
                              setEditOpen(true);
                            }}
                            className="p-1.5 rounded-lg border border-white/10 hover:border-blue-500/40 bg-card hover:bg-blue-500/10 text-zinc-400 hover:text-blue-400 transition-all cursor-pointer"
                            title="Edit Source Config"
                          >
                            <Edit className="w-3.5 h-3.5" />
                          </button>

                          {/* Delete Source */}
                          <button
                            onClick={() => handleDelete(source.id, source.domain)}
                            className="p-1.5 rounded-lg border border-white/10 hover:border-red-500/40 bg-card hover:bg-red-500/10 text-zinc-400 hover:text-red-400 transition-all cursor-pointer"
                            title="Remove from Registry"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Toolbar */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 py-3.5 bg-white/[0.02] border-t border-white/10 text-xs">
              <div className="flex flex-wrap items-center gap-3 text-zinc-400">
                <div>
                  Showing page <span className="font-semibold text-white">{page}</span> of{" "}
                  <span className="font-semibold text-white">{totalPages}</span>{" "}
                  (<span className="text-[#c8f542] font-semibold">{totalCount.toLocaleString()}</span> matching sources)
                </div>

                <div className="flex items-center gap-2 pl-3 border-l border-white/10">
                  <label htmlFor="sources-rows-input" className="text-zinc-400 text-xs font-medium cursor-pointer">
                    Rows:
                  </label>
                  <input
                    id="sources-rows-input"
                    type="number"
                    min={1}
                    max={200}
                    value={limitInput}
                    onChange={(e) => setLimitInput(e.target.value)}
                    onBlur={handleLimitCommit}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        handleLimitCommit();
                        (e.target as HTMLInputElement).blur();
                      }
                    }}
                    className="w-16 h-7 bg-zinc-950/80 border border-white/15 rounded-lg px-2 text-xs text-white text-center font-mono focus:outline-none focus:border-[#c8f542] focus:ring-1 focus:ring-[#c8f542]/40 transition-all"
                    title="Enter rows per page and press Enter"
                  />
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="h-8 gap-1 text-xs border-white/10 disabled:opacity-40"
                >
                  <ChevronLeft className="w-3.5 h-3.5" /> Previous
                </Button>
                <div className="px-3 py-1 font-mono text-zinc-400">
                  {page} / {totalPages}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="h-8 gap-1 text-xs border-white/10 disabled:opacity-40"
                >
                  Next <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
