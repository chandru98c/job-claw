"use client";

import React, { useEffect, useState, useCallback } from "react";
import { 
  Activity, 
  X, 
  Bookmark, 
  Send, 
  Loader2, 
  AlertCircle, 
  Building2, 
  MapPin, 
  ExternalLink, 
  CheckCircle2, 
  RefreshCw, 
  Compass, 
  ChevronRight, 
  ChevronLeft,
  RotateCcw,
  SlidersHorizontal,
  Code2,
  GraduationCap,
  Globe2,
  Search,
  Briefcase,
  Banknote,
  Clock,
  FilterX
} from "lucide-react";
import { api } from "@/lib/api";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type RecommendationItem = {
  id: string;
  profile_id: string;
  job_id: string;
  score: number;
  reasons?: string[];
  matched_skills?: string[];
  experience_level?: string;
  education_level?: string;
  role_category?: string;
  corridor?: string;
  city?: string;
  posted_at?: string;
  state: "NEW" | "SEEN" | "SAVED" | "DISMISSED" | "APPLIED";
  title?: string;
  company_name?: string;
  location?: string;
  job_type?: string;
  remote_status?: string;
  apply_url?: string;
  salary_min?: number;
  salary_max?: number;
  first_seen_at?: string;
  created_at?: string;
};

type ProfileInfo = {
  id: string;
  name: string;
  location?: string;
  education?: string;
  experience?: string;
  experience_level?: string;
  experience_years?: number;
  skills?: string[];
  preferred_locations?: string[];
  preferred_job_types?: string[];
};

const ROLES = [
  { id: "", label: "All Roles" },
  { id: "software_engineer", label: "Software Engineer" },
  { id: "fullstack", label: "Full Stack" },
  { id: "backend", label: "Backend" },
  { id: "frontend", label: "Frontend" },
  { id: "data_ai", label: "Data & AI" },
  { id: "devops_cloud", label: "DevOps & Cloud" },
  { id: "qa_testing", label: "QA & Testing" },
  { id: "mobile", label: "Mobile" },
];

const DEGREES = [
  { id: "", label: "All Degrees" },
  { id: "MCA", label: "🎓 MCA" },
  { id: "B.Tech", label: "🎓 B.Tech / BE" },
  { id: "M.Tech", label: "🎓 M.Tech" },
  { id: "BCA", label: "🎓 BCA" },
  { id: "Any Graduate", label: "🎓 Any Graduate" },
];

const EXPERIENCES = [
  { id: "", label: "All Experience" },
  { id: "fresher", label: "🌱 Fresher (0 Yrs)" },
  { id: "junior", label: "Junior (1-3 Yrs)" },
  { id: "mid", label: "Mid-Level (3-5 Yrs)" },
  { id: "senior", label: "Senior (5+ Yrs)" },
];

const TARGET_HUBS = [
  { id: "", label: "All Tech Hubs" },
  { id: "chennai", label: "Chennai" },
  { id: "omr", label: "OMR / Siruseri" },
  { id: "guindy", label: "Guindy / MEPZ" },
  { id: "porur", label: "DLF Porur" },
  { id: "bangalore", label: "Bengaluru" },
  { id: "whitefield", label: "Whitefield" },
  { id: "electronic_city", label: "Electronic City" },
  { id: "hyderabad", label: "Hyderabad" },
  { id: "hitec_city", label: "HITEC City" },
  { id: "coimbatore", label: "Coimbatore" },
  { id: "pune", label: "Pune" },
  { id: "delhi", label: "Delhi NCR" },
  { id: "mumbai", label: "Mumbai" },
  { id: "remote", label: "Remote" },
];

const ROLE_LABELS: Record<string, { label: string; color: string }> = {
  software_engineer: { label: "Software Engineer", color: "bg-blue-500/10 text-blue-400 border-blue-500/20" },
  frontend: { label: "Frontend", color: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20" },
  backend: { label: "Backend", color: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20" },
  fullstack: { label: "Full Stack", color: "bg-violet-500/10 text-violet-400 border-violet-500/20" },
  data_ai: { label: "Data & AI", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
  devops_cloud: { label: "DevOps & Cloud", color: "bg-amber-500/10 text-amber-400 border-amber-500/20" },
  qa_testing: { label: "QA & Testing", color: "bg-teal-500/10 text-teal-400 border-teal-500/20" },
  mobile: { label: "Mobile", color: "bg-pink-500/10 text-pink-400 border-pink-500/20" },
};

function formatExpBadge(exp?: string | null) {
  if (!exp) return null;
  const l = exp.toLowerCase();
  if (l.includes("fresher") || l.includes("entry") || l.includes("0 yr") || l.includes("intern")) {
    return { label: "🌱 Fresher (0 Yrs)", color: "bg-lime-500/15 text-[#c8f542] border-[#c8f542]/30 font-semibold" };
  }
  if (l.includes("junior") || l.includes("1-3") || l.includes("associate")) {
    return { label: "Junior (1-3 Yrs)", color: "bg-sky-500/10 text-sky-400 border-sky-500/20 font-medium" };
  }
  if (l.includes("mid") || l.includes("3-5")) {
    return { label: "Mid-Level (3-5 Yrs)", color: "bg-purple-500/10 text-purple-400 border-purple-500/20 font-medium" };
  }
  if (l.includes("senior") || l.includes("5+") || l.includes("lead") || l.includes("principal")) {
    return { label: "Senior (5+ Yrs)", color: "bg-rose-500/10 text-rose-400 border-rose-500/20 font-medium" };
  }
  return { label: exp, color: "bg-zinc-800 text-zinc-300 border-zinc-700 font-medium" };
}

function formatSalary(min?: number | null, max?: number | null): string | null {
  if (!min && !max) return null;
  const formatLakh = (val: number) => {
    const lpa = val / 100000;
    return lpa % 1 === 0 ? `${lpa}` : `${lpa.toFixed(1)}`;
  };
  if (min && min >= 100000) {
    if (min && max) return `₹${formatLakh(min)} - ${formatLakh(max)} LPA`;
    if (min) return `₹${formatLakh(min)}+ LPA`;
    if (max) return `Up to ₹${formatLakh(max)} LPA`;
  }
  return null;
}

function formatTimeAgo(dateStr?: string | null): string {
  if (!dateStr) return "Recently";
  try {
    const dt = new Date(dateStr);
    const diff = Math.floor((Date.now() - dt.getTime()) / 1000);
    if (diff < 60) return "Just now";
    const minutes = Math.floor(diff / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;
    const weeks = Math.floor(days / 7);
    if (weeks < 4) return `${weeks}w ago`;
    return `${Math.floor(days / 30)}mo ago`;
  } catch {
    return "Recently";
  }
}

function RecommendationCard({ 
  rec, 
  onDismiss,
  onSave
}: { 
  rec: RecommendationItem, 
  onDismiss: (id: string) => void,
  onSave: (id: string) => void
}) {
  const router = useRouter();
  const [preparing, setPreparing] = useState(false);

  const handlePrepare = async (e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
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

  const isRemote = (rec.remote_status && rec.remote_status.toLowerCase().includes("remote")) || 
                   (rec.location && rec.location.toLowerCase().includes("remote"));

  const expBadge = formatExpBadge(rec.experience_level);
  const salaryStr = formatSalary(rec.salary_min, rec.salary_max);
  const roleBadge = rec.role_category ? ROLE_LABELS[rec.role_category] : null;
  const timeDisplay = formatTimeAgo(rec.posted_at || rec.first_seen_at || rec.created_at);

  const handleCardClick = () => {
    if (rec.apply_url) {
      window.open(rec.apply_url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div 
      onClick={handleCardClick}
      className={`bg-[#121216]/90 hover:bg-[#16161c] transition-all duration-300 border border-white/[0.08] hover:border-[#c8f542]/50 hover:shadow-[0_12px_36px_rgba(0,0,0,0.6)] rounded-[24px] p-6 flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-xl relative overflow-hidden group ${
        rec.apply_url ? "cursor-pointer" : ""
      }`}
    >
      {/* Glow highlight on hover */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-[#c8f542]/[0.03] group-hover:bg-[#c8f542]/[0.08] rounded-full blur-2xl transition-all pointer-events-none" />

      <div className="flex-1 min-w-0">
        {/* Top Badges */}
        <div className="flex flex-wrap items-center gap-2 mb-2.5">
          {/* Match Score */}
          <span className={`inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full font-mono font-bold text-xs ${
            rec.score >= 90 
              ? "bg-[#c8f542]/15 border border-[#c8f542]/40 text-[#c8f542]" 
              : "bg-emerald-500/15 border border-emerald-500/30 text-emerald-400"
          }`}>
            <CheckCircle2 className="w-3.5 h-3.5" />
            {rec.score}% Match
          </span>

          {/* Time Ago */}
          <span className={`inline-flex items-center gap-1 text-xs font-mono px-2 py-0.5 rounded-full border ${
            rec.posted_at
              ? "bg-[#c8f542]/10 text-[#c8f542] border-[#c8f542]/30"
              : "bg-white/[0.04] text-zinc-400 border-white/10"
          }`}>
            <Clock className={`w-3 h-3 ${rec.posted_at ? "text-[#c8f542]" : "text-zinc-500"}`} />
            {rec.posted_at ? `Posted ${timeDisplay}` : `Found ${timeDisplay}`}
          </span>

          {/* Corridor / Hub Badge */}
          {rec.corridor && (
            <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border bg-amber-400/10 border-amber-400/25 text-amber-300">
              <MapPin className="w-3 h-3" />
              {rec.corridor}
            </span>
          )}

          {/* Location Badge */}
          {rec.location && !rec.corridor && (
            <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full border ${
              isRemote
                ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-400"
                : "bg-white/[0.05] border-white/10 text-zinc-300"
            }`}>
              <MapPin className="w-3.5 h-3.5" />
              {rec.location}
            </span>
          )}

          {/* Remote Badge */}
          {isRemote && !rec.location?.toLowerCase().includes("remote") && (
            <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">
              <Globe2 className="w-3 h-3" />
              Remote Eligible
            </span>
          )}

          {/* Company Name */}
          {rec.company_name && (
            <span className="flex items-center gap-1 text-xs font-semibold text-zinc-200 bg-white/[0.04] px-2.5 py-0.5 rounded-full border border-white/5">
              <Building2 className="w-3.5 h-3.5 text-zinc-400" />
              {rec.company_name}
            </span>
          )}

          {/* Degree Badge */}
          {rec.education_level && (
            <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-0.5 rounded-full border bg-white/[0.06] text-zinc-300 border-white/10">
              <GraduationCap className="w-3 h-3 text-[#c8f542]" />
              {rec.education_level}
            </span>
          )}

          {/* Role Badge */}
          {roleBadge && (
            <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded-full border ${roleBadge.color}`}>
              {roleBadge.label}
            </span>
          )}

          {/* Experience Level Badge */}
          {expBadge && (
            <span className={`inline-flex items-center gap-1 text-[11px] px-2.5 py-0.5 rounded-full border ${expBadge.color}`}>
              {expBadge.label}
            </span>
          )}

          {/* Salary Badge */}
          {salaryStr && (
            <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-300">
              <Banknote className="w-3 h-3" />
              {salaryStr}
            </span>
          )}

          {/* State Tag */}
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
            rec.state === "SAVED" 
              ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
              : rec.state === "APPLIED"
              ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
              : "bg-zinc-800/80 text-zinc-400 border border-zinc-700/50"
          }`}>
            {rec.state}
          </span>
        </div>

        {/* Job Title */}
        <h3 className="text-lg sm:text-xl font-bold text-white group-hover:text-[#c8f542] transition-colors break-words flex items-center gap-2">
          <span>{rec.title || `Software Position (${rec.job_id.slice(0, 8)})`}</span>
          {rec.apply_url && (
            <ExternalLink className="w-4 h-4 text-zinc-500 group-hover:text-[#c8f542] opacity-75 group-hover:opacity-100 transition-all shrink-0" />
          )}
        </h3>

        {/* Matched Skills Pills */}
        {rec.matched_skills && rec.matched_skills.length > 0 && (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-zinc-400 font-medium mr-1 flex items-center gap-1">
              <Code2 className="w-3 h-3 text-[#c8f542]" /> Matched Stack:
            </span>
            {rec.matched_skills.map((skill, idx) => (
              <span 
                key={idx}
                className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-[#c8f542]/10 border border-[#c8f542]/20 text-[#c8f542]"
              >
                {skill}
              </span>
            ))}
          </div>
        )}

        {/* Justification Reasons */}
        {rec.reasons && rec.reasons.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {rec.reasons.map((r: string, i: number) => (
              <span key={i} className="inline-flex items-center gap-1.5 text-xs bg-white/[0.04] text-zinc-300 border border-white/[0.06] px-2.5 py-1 rounded-full font-medium">
                <CheckCircle2 className="w-3 h-3 text-[#c8f542]" />
                {r}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div 
        onClick={(e) => e.stopPropagation()} 
        className="flex flex-col sm:flex-row md:flex-col gap-2.5 shrink-0 min-w-[200px]"
      >
        <Button 
          onClick={(e) => { e.stopPropagation(); handlePrepare(e); }}
          disabled={rec.state === "APPLIED" || preparing}
          className="rounded-full gap-2 bg-[#c8f542] hover:bg-[#d4f85e] text-black font-semibold shadow-lg shadow-[#c8f542]/20 py-2.5 text-xs sm:text-sm"
        >
          {preparing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          {preparing ? "Preparing..." : rec.state === "APPLIED" ? "Applied" : "Prepare Application"}
        </Button>

        <div className="flex gap-2">
          {rec.apply_url && (
            <a
              href={rec.apply_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-full border border-white/10 hover:border-[#c8f542]/40 bg-white/[0.03] hover:bg-white/[0.08] text-zinc-200 hover:text-white transition-all flex-1"
            >
              <ExternalLink className="w-3.5 h-3.5 text-[#c8f542]" />
              Direct Apply
            </a>
          )}
          <Button 
            variant="outline"
            onClick={(e) => { e.stopPropagation(); onSave(rec.id); }}
            className={`rounded-full px-3 gap-1.5 border-white/10 text-xs transition-colors ${
              rec.state === "SAVED" 
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40" 
                : "text-zinc-300 hover:text-white hover:bg-white/5"
            }`}
            title="Save for later"
          >
            <Bookmark className="w-3.5 h-3.5" />
            {rec.state === "SAVED" ? "Saved" : "Save"}
          </Button>
          <Button 
            variant="outline"
            onClick={(e) => { e.stopPropagation(); onDismiss(rec.id); }}
            className="rounded-full px-2.5 border-white/10 text-zinc-400 hover:bg-destructive/20 hover:text-destructive hover:border-destructive/30"
            title="Dismiss from matches"
          >
            <X className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function RecommendationsPage() {
  const [recs, setRecs] = useState<RecommendationItem[]>([]);
  const [profile, setProfile] = useState<ProfileInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Interactive Filter Controls
  const [scope, setScope] = useState<string>("all"); // 'all', 'local', 'remote', 'saved'
  const [q, setQ] = useState<string>("");
  const [role, setRole] = useState<string>("");
  const [degree, setDegree] = useState<string>("");
  const [experience, setExperience] = useState<string>("");
  const [targetLocation, setTargetLocation] = useState<string>("");
  
  const [page, setPage] = useState<number>(1);
  const [refreshCount, setRefreshCount] = useState<number>(0);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

  // Load profile info for candidate context
  useEffect(() => {
    async function loadProfile() {
      try {
        const data = await api.get<any>("/profiles/me");
        if (data) setProfile(data);
      } catch {
        try {
          const list = await api.get<any[]>("/profiles");
          if (list && list.length > 0) setProfile(list[0]);
        } catch {
          // ignore
        }
      }
    }
    loadProfile();
  }, []);

  // Fetch recommendations with full filter parameters
  const loadRecommendations = useCallback(async (
    targetPage: number = 1, 
    targetScope: string = "all", 
    isForceRefresh: boolean = false
  ) => {
    if (isForceRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      let data: RecommendationItem[] = [];

      const params = new URLSearchParams();
      params.append("page", targetPage.toString());
      params.append("limit", "15");
      params.append("scope", targetScope);

      if (q.trim()) params.append("q", q.trim());
      if (role) params.append("role", role);
      if (degree) params.append("degree", degree);
      if (experience) params.append("experience_level", experience);
      if (targetLocation) params.append("location", targetLocation);

      if (targetScope === "saved") {
        data = await api.get<RecommendationItem[]>("/recommendations?state=SAVED");
      } else if (isForceRefresh) {
        data = await api.post<RecommendationItem[]>(
          `/recommendations/refresh?${params.toString()}`
        );
        setFeedbackMessage(`Discovered ${data.length} fresh roles matching your stack!`);
        setTimeout(() => setFeedbackMessage(null), 3500);
      } else {
        data = await api.get<RecommendationItem[]>(
          `/recommendations?${params.toString()}`
        );
      }

      setRecs(data);
      setPage(targetPage);
    } catch (err: any) {
      setError(err.message || "Failed to load recommendations");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [q, role, degree, experience, targetLocation]);

  // Initial and reactive load on filter changes
  useEffect(() => {
    loadRecommendations(1, scope, false);
  }, [scope, role, degree, experience, targetLocation, loadRecommendations]);

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      loadRecommendations(1, scope, true);
    }
  };

  const handleClearFilters = () => {
    setQ("");
    setRole("");
    setDegree("");
    setExperience("");
    setTargetLocation("");
    setScope("all");
  };

  const hasActiveFilters = Boolean(q || role || degree || experience || targetLocation || scope !== "all");

  // Click handler for "Discover New Set"
  const handleDiscoverNewSet = () => {
    const nextPage = page + 1;
    setRefreshCount(c => c + 1);
    loadRecommendations(nextPage, scope, true);
  };

  // Reset & start fresh
  const handleReset = async () => {
    setLoading(true);
    try {
      const data = await api.post<RecommendationItem[]>("/recommendations/reset");
      setRecs(data);
      setPage(1);
      setFeedbackMessage("Recommendations reset to top matching roles!");
      setTimeout(() => setFeedbackMessage(null), 3500);
    } catch (err: any) {
      setError(err.message || "Failed to reset recommendations");
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (id: string, action: string) => {
    try {
      await api.post(`/recommendations/${id}/action`, { action });
      if (action === "dismiss") {
        setRecs(r => r.filter(x => x.id !== id));
      } else if (action === "save") {
        setRecs(r => r.map(x => x.id === id ? { ...x, state: "SAVED" } : x));
      }
    } catch (err: any) {
      alert(err.message || "Failed to perform action");
    }
  };

  return (
    <div className="flex flex-col max-w-6xl mx-auto w-full px-4 sm:px-6 py-8 relative">
      {/* Ambient Top Glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[850px] h-[300px] bg-gradient-to-b from-[#c8f542]/[0.07] via-[#c8f542]/[0.02] to-transparent blur-3xl pointer-events-none -z-10" />

      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2.5">
            <Activity className="w-7 h-7 text-[#c8f542] shrink-0" />
            Job Recommendations
            <span className="text-xs sm:text-sm font-semibold px-2.5 py-0.5 rounded-full bg-[#c8f542]/10 border border-[#c8f542]/30 text-[#c8f542] font-mono">
              {recs.length} matches
            </span>
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Personalized positions matched to your candidate profile with 100% accurate degree & experience filters.
          </p>
        </div>

        {/* Primary Action Buttons */}
        <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
          <Button
            onClick={handleDiscoverNewSet}
            disabled={refreshing || loading}
            className="h-9 px-4 rounded-xl gap-1.5 bg-[#c8f542] hover:bg-[#d8ff4e] text-black font-semibold text-xs transition-all shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Discovering..." : "Discover New Set"}
          </Button>

          <Button
            variant="outline"
            onClick={handleReset}
            disabled={loading || refreshing}
            className="h-9 px-3 rounded-xl gap-1.5 border-white/10 hover:border-white/20 bg-card/40 text-xs text-zinc-300 hover:text-white"
            title="Reset and re-rank from all available positions"
          >
            <RotateCcw className="w-3.5 h-3.5 text-zinc-400" />
            Reset
          </Button>
        </div>
      </div>

      {/* Profile Match Context Banner */}
      {profile && (
        <div className="mb-6 p-4 rounded-[20px] bg-gradient-to-r from-white/[0.04] to-white/[0.01] border border-white/[0.08] flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5 font-bold text-white">
              <GraduationCap className="w-4 h-4 text-[#c8f542]" />
              {profile.name} {profile.education ? `(${profile.education})` : ""}
            </div>
            <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-semibold">
              {profile.experience || "All Experience Levels"}
            </div>
            <div className="flex items-center gap-1.5 text-zinc-300">
              <MapPin className="w-3.5 h-3.5 text-[#c8f542]" />
              Target Hubs: <span className="text-[#c8f542] font-semibold">{profile.preferred_locations?.length ? profile.preferred_locations.join(", ") : "All Locations"}</span>
            </div>
            {profile.skills && profile.skills.length > 0 && (
              <div className="flex items-center gap-1.5 text-zinc-400">
                <Code2 className="w-3.5 h-3.5 text-zinc-400" />
                Active Stack: <span className="text-zinc-200">{profile.skills.slice(0, 5).join(" · ")}</span>
              </div>
            )}
          </div>
          <div className="text-[11px] font-mono text-zinc-400 bg-white/5 px-2.5 py-1 rounded-full border border-white/5">
            Set #{page}
          </div>
        </div>
      )}

      {/* Interactive Filter Bar */}
      <div className="mb-6 p-4 rounded-[22px] bg-[#121216]/80 border border-white/[0.08] space-y-3.5">
        <div className="flex flex-wrap items-center gap-3">
          {/* Keyword Search */}
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="Search stack, title or company..."
              className="pl-9 h-10 bg-white/[0.03] border-white/10 rounded-xl text-xs text-white placeholder:text-zinc-500 focus:border-[#c8f542]/50"
            />
          </div>

          {/* Role Filter */}
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="h-10 px-3 bg-[#18181f] border border-white/10 rounded-xl text-xs text-zinc-200 focus:outline-none focus:border-[#c8f542]/50"
          >
            {ROLES.map((r) => (
              <option key={r.id} value={r.id} className="bg-[#18181f] text-zinc-200">
                {r.label}
              </option>
            ))}
          </select>

          {/* Degree Filter */}
          <select
            value={degree}
            onChange={(e) => setDegree(e.target.value)}
            className="h-10 px-3 bg-[#18181f] border border-white/10 rounded-xl text-xs text-zinc-200 focus:outline-none focus:border-[#c8f542]/50"
          >
            {DEGREES.map((d) => (
              <option key={d.id} value={d.id} className="bg-[#18181f] text-zinc-200">
                {d.label}
              </option>
            ))}
          </select>

          {/* Experience Filter */}
          <select
            value={experience}
            onChange={(e) => setExperience(e.target.value)}
            className="h-10 px-3 bg-[#18181f] border border-white/10 rounded-xl text-xs text-zinc-200 focus:outline-none focus:border-[#c8f542]/50"
          >
            {EXPERIENCES.map((exp) => (
              <option key={exp.id} value={exp.id} className="bg-[#18181f] text-zinc-200">
                {exp.label}
              </option>
            ))}
          </select>

          {/* Target Location / Hub Filter */}
          <select
            value={targetLocation}
            onChange={(e) => setTargetLocation(e.target.value)}
            className="h-10 px-3 bg-[#18181f] border border-white/10 rounded-xl text-xs text-zinc-200 focus:outline-none focus:border-[#c8f542]/50"
          >
            {TARGET_HUBS.map((h) => (
              <option key={h.id} value={h.id} className="bg-[#18181f] text-zinc-200">
                {h.label}
              </option>
            ))}
          </select>

          {/* Clear Filters Button */}
          {hasActiveFilters && (
            <Button
              variant="ghost"
              onClick={handleClearFilters}
              className="h-10 px-3 text-xs text-zinc-400 hover:text-white hover:bg-white/5 rounded-xl gap-1.5"
            >
              <FilterX className="w-3.5 h-3.5" />
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Scope Filter Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6 pb-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-2 overflow-x-auto">
          {[
            { id: "all", label: "All Profile Matches" },
            { id: "local", label: "Target Hubs First" },
            { id: "remote", label: "Remote & Hybrid" },
            { id: "saved", label: "Saved Roles" },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => {
                setScope(tab.id);
                setPage(1);
              }}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all whitespace-nowrap ${
                scope === tab.id
                  ? "bg-[#c8f542] text-black shadow-md shadow-[#c8f542]/20"
                  : "bg-white/[0.04] text-zinc-400 hover:text-white hover:bg-white/[0.08] border border-white/5"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {feedbackMessage && (
          <div className="text-xs font-semibold text-[#c8f542] bg-[#c8f542]/10 border border-[#c8f542]/20 px-3 py-1 rounded-full animate-fade-in flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" />
            {feedbackMessage}
          </div>
        )}
      </div>

      {/* Recommendations Feed */}
      <div className="grid gap-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="w-8 h-8 text-[#c8f542] animate-spin" />
            <p className="text-xs text-zinc-400 font-medium">Loading recommendations...</p>
          </div>
        ) : error ? (
          <div className="text-center py-12 bg-destructive/10 border border-destructive/20 rounded-[24px]">
            <AlertCircle className="w-8 h-8 text-destructive mx-auto mb-4" />
            <p className="text-destructive font-medium">{error}</p>
            <Button onClick={() => loadRecommendations(1, scope, true)} className="mt-4 rounded-full" variant="outline">
              Retry
            </Button>
          </div>
        ) : recs.length === 0 ? (
          <div className="text-center py-16 bg-[#121216]/60 border border-white/[0.08] rounded-[24px] p-8 flex flex-col items-center gap-4">
            <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center text-zinc-400">
              <Compass className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-base font-bold text-white mb-1">No positions found in this filter view</h4>
              <p className="text-xs text-zinc-400 max-w-md">
                Try adjusting your search criteria or click below to discover fresh personalized roles.
              </p>
            </div>
            <div className="flex gap-3">
              <Button onClick={handleDiscoverNewSet} className="rounded-full bg-[#c8f542] hover:bg-[#d4f85e] text-black font-semibold text-xs">
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                Discover Fresh Roles
              </Button>
              <Button onClick={handleClearFilters} variant="outline" className="rounded-full border-white/10 text-xs">
                Clear Filters
              </Button>
            </div>
          </div>
        ) : (
          recs.map(rec => (
            <RecommendationCard 
              key={rec.id} 
              rec={rec} 
              onDismiss={(id) => handleAction(id, "dismiss")}
              onSave={(id) => handleAction(id, "save")}
            />
          ))
        )}
      </div>

      {/* Pagination Footer */}
      {!loading && recs.length > 0 && (
        <div className="mt-8 pt-4 border-t border-white/[0.06] flex items-center justify-between text-xs text-zinc-400">
          <div className="flex items-center gap-1.5">
            <span>Showing Set #{page} · {recs.length} personalized positions</span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              disabled={page <= 1 || loading}
              onClick={() => loadRecommendations(Math.max(1, page - 1), scope, true)}
              className="rounded-full px-3 py-1 text-xs border-white/10"
            >
              <ChevronLeft className="w-3.5 h-3.5 mr-1" /> Previous Set
            </Button>
            <Button
              onClick={handleDiscoverNewSet}
              disabled={loading || refreshing}
              className="rounded-full px-4 py-1 text-xs bg-[#c8f542] hover:bg-[#d4f85e] text-black font-bold"
            >
              Next Set <ChevronRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
