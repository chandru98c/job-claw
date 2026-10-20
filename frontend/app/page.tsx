"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { JobCard } from "@/components/jobs/job-card";
import {
  SlidersHorizontal,
  ArrowDownWideNarrow,
  Search,
  MapPin,
  Loader2,
  AlertCircle,
  GraduationCap,
  Briefcase,
  Banknote,
  Clock,
  X,
  Filter,
  RefreshCw,
  Compass,
  Building2,
  ChevronDown,
  Globe,
  Sparkles,
} from "lucide-react";
import { useSearchMode, useAppState } from "@/components/providers";
import { api } from "@/lib/api";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";

export type JobResponse = {
  id: string;
  title: string;
  company_name: string;
  location: string | null;
  job_type: string | null;
  canonical_apply_url: string;
  status: string;
  matchScore: number | null;
  matchReasons: string[] | null;
  timeAgo: string;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string | null;
  education_level?: string | null;
  role_category?: string | null;
  experience_level?: string | null;
  corridor?: string | null;
  city?: string | null;
  created_at?: string | null;
  discovered_at?: string | null;
  posted_at?: string | null;
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
  { id: "MCA", label: "🎓 MCA (Master of Computer Apps)" },
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

const SALARY_PRESETS = [
  { id: "", label: "Any Salary", min: undefined, max: undefined },
  { id: "3_6_lpa", label: "₹3 - 6 LPA", min: 300000, max: 600000 },
  { id: "6_12_lpa", label: "₹6 - 12 LPA", min: 600000, max: 1200000 },
  { id: "12_25_lpa", label: "₹12 - 25 LPA", min: 1200000, max: 2500000 },
  { id: "25_plus_lpa", label: "₹25+ LPA", min: 2500000, max: undefined },
  { id: "usd_80k", label: "$80k+ USD", min: 80000, max: undefined },
];

const METRO_HUBS = [
  { id: "chennai", label: "Chennai", statKey: "chennai" },
  { id: "bangalore", label: "Bengaluru", statKey: "bangalore" },
  { id: "hyderabad", label: "Hyderabad", statKey: "hyderabad" },
  { id: "coimbatore", label: "Coimbatore", statKey: "coimbatore" },
  { id: "pune", label: "Pune", statKey: "pune" },
  { id: "delhi", label: "Delhi NCR", statKey: "delhi" },
  { id: "mumbai", label: "Mumbai", statKey: "mumbai" },
];

const SOUTH_INDIA_CORRIDORS = [
  { id: "omr", label: "OMR / Siruseri", city: "Chennai", statKey: "omr", desc: "TIDEL Park, Sholinganallur, SIPCOT Siruseri" },
  { id: "whitefield", label: "Whitefield", city: "Bengaluru", statKey: "whitefield", desc: "ITPL, EPIP Zone, Brookfield" },
  { id: "hitec_city", label: "HITEC City", city: "Hyderabad", statKey: "hitec_city", desc: "Madhapur, Cyber Towers, Mindspace" },
  { id: "coimbatore", label: "Coimbatore TIDEL", city: "Coimbatore", statKey: "coimbatore", desc: "TIDEL Park, CHIL SEZ, Saravanampatti" },
  { id: "electronic_city", label: "Electronic City", city: "Bengaluru", statKey: "electronic_city", desc: "Electronic City Phases 1 & 2" },
  { id: "guindy", label: "Guindy / MEPZ", city: "Chennai", statKey: "guindy", desc: "Olympia Tech Park, MEPZ, Ekkatuthangal" },
  { id: "porur", label: "DLF Porur", city: "Chennai", statKey: "porur", desc: "DLF Cybercity, Manapakkam" },
];

interface CorridorItem {
  id: string;
  label: string;
  city: string;
  statKey?: string;
  landmarks: string;
}

const ALL_INDIA_CORRIDORS: { region: string; corridors: CorridorItem[] }[] = [
  {
    region: "Chennai Tech Corridors",
    corridors: [
      { id: "omr", label: "OMR / Siruseri", city: "Chennai", statKey: "omr", landmarks: "TIDEL, Taramani, Sholinganallur, SIPCOT" },
      { id: "guindy", label: "Guindy / MEPZ", city: "Chennai", statKey: "guindy", landmarks: "Olympia Tech Park, MEPZ, Ekkatuthangal" },
      { id: "porur", label: "DLF Porur", city: "Chennai", statKey: "porur", landmarks: "DLF Cybercity, Manapakkam, Commerzone" },
      { id: "ambattur", label: "Ambattur IT Estate", city: "Chennai", statKey: "ambattur", landmarks: "Industrial Estate, IT Parks" },
      { id: "chengalpattu", label: "Mahindra World City", city: "Chennai", statKey: "chengalpattu", landmarks: "MWC Special Economic Zone" },
    ],
  },
  {
    region: "Bengaluru Tech Corridors",
    corridors: [
      { id: "whitefield", label: "Whitefield & ITPL", city: "Bengaluru", statKey: "whitefield", landmarks: "EPIP Zone, ITPL, Brookfield" },
      { id: "electronic_city", label: "Electronic City", city: "Bengaluru", statKey: "electronic_city", landmarks: "Phases 1 & 2, Hosur Road" },
      { id: "outer_ring_road", label: "Outer Ring Road (ORR)", city: "Bengaluru", statKey: "outer_ring_road", landmarks: "Bellandur, Marathahalli, Ecospace" },
      { id: "manyata", label: "Manyata & Hebbal", city: "Bengaluru", statKey: "manyata", landmarks: "Manyata Tech Park, Nagavara" },
    ],
  },
  {
    region: "Hyderabad Tech Corridors",
    corridors: [
      { id: "hitec_city", label: "HITEC City & Madhapur", city: "Hyderabad", statKey: "hitec_city", landmarks: "Cyber Towers, Raheja Mindspace" },
      { id: "gachibowli", label: "Gachibowli & Financial Dist", city: "Hyderabad", statKey: "gachibowli", landmarks: "Nanakramguda, Waverock, Wipro Circle" },
      { id: "kondapur", label: "Kondapur & Knowledge City", city: "Hyderabad", statKey: "kondapur", landmarks: "Knowledge City, Hafeezpet" },
    ],
  },
  {
    region: "Coimbatore & Regional TN",
    corridors: [
      { id: "coimbatore", label: "Coimbatore TIDEL & CHIL", city: "Coimbatore", statKey: "coimbatore", landmarks: "Saravanampatti, TIDEL Park, Eachanari" },
      { id: "hosur", label: "Hosur Electronics Belt", city: "Hosur", statKey: "hosur", landmarks: "EV & Tech Manufacturing Corridor" },
      { id: "madurai", label: "Madurai ELCOT IT Park", city: "Madurai", statKey: "madurai", landmarks: "Vadapalanji IT Park" },
    ],
  },
  {
    region: "Pune & Mumbai Corridors",
    corridors: [
      { id: "hinjewadi", label: "Hinjewadi IT Park", city: "Pune", statKey: "hinjewadi", landmarks: "Phases 1, 2 & 3, Quadron" },
      { id: "magarpatta", label: "Magarpatta & Kharadi", city: "Pune", statKey: "magarpatta", landmarks: "Cybercity, EON Free Zone" },
      { id: "bkc", label: "Bandra Kurla Complex (BKC)", city: "Mumbai", statKey: "bkc", landmarks: "Financial & Tech Center" },
      { id: "navi_mumbai", label: "Navi Mumbai Mindspace", city: "Navi Mumbai", statKey: "navi_mumbai", landmarks: "Airoli, Mahape Millennium Business Park" },
    ],
  },
  {
    region: "Delhi NCR Corridors",
    corridors: [
      { id: "cyber_city", label: "DLF Cyber City & Golf Course", city: "Gurugram", statKey: "cyber_city", landmarks: "Cyber Hub, Horizon Center, Udyog Vihar" },
      { id: "noida", label: "Noida IT Corridor (Sec 62/135)", city: "Noida", statKey: "noida", landmarks: "Sector 62, Advant Navis, Expressway" },
    ],
  },
];

export default function Home() {
  const { isOpenSearch } = useSearchMode();
  const { apiMode } = useAppState();

  // Data states
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pagination states
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const observerTarget = useRef<HTMLDivElement>(null);

  // Multi-attribute filter states
  const [q, setQ] = useState("");
  const [location, setLocation] = useState("");
  const [remote, setRemote] = useState(false);
  const [role, setRole] = useState("");
  const [degree, setDegree] = useState("");
  const [experience, setExperience] = useState("");
  const [salaryPreset, setSalaryPreset] = useState("");
  const [sortMode, setSortMode] = useState<"posted_at" | "discovered" | "score">(isOpenSearch ? "posted_at" : "score");
  const [locationStats, setLocationStats] = useState<Record<string, { count: number }>>({});

  // Load real-time location counts from backend API
  useEffect(() => {
    api.get<Record<string, { count: number }>>("/jobs/locations/stats")
      .then((data) => setLocationStats(data))
      .catch((err) => console.warn("Failed to load location stats", err));
  }, []);

  // Selected salary numbers
  const currentSalary = SALARY_PRESETS.find((s) => s.id === salaryPreset);

  const fetchJobs = useCallback(
    async (pageNumber: number = 1, signal?: AbortSignal) => {
      if (pageNumber === 1) {
        setLoading(true);
      } else {
        setLoadingMore(true);
      }
      setError(null);

      try {
        const params = new URLSearchParams();
        params.append("page", pageNumber.toString());
        params.append("limit", "20");
        params.append("sort_by", sortMode);

        if (q.trim()) params.append("q", q.trim());
        if (location.trim()) params.append("location", location.trim());
        if (remote) params.append("remote", "true");
        if (role) params.append("role", role);
        if (degree) params.append("degree", degree);
        if (experience) params.append("experience_level", experience);
        if (currentSalary?.min !== undefined) params.append("salary_min", currentSalary.min.toString());
        if (currentSalary?.max !== undefined) params.append("salary_max", currentSalary.max.toString());

        const endpoint = isOpenSearch ? `/jobs?${params.toString()}` : `/jobs/match?${params.toString()}`;

        const res = await api.get<{ items: JobResponse[]; total: number }>(endpoint, { signal });

        if (signal?.aborted) return;

        const newJobs = res.items || [];
        if (pageNumber === 1) {
          setJobs(newJobs);
        } else {
          setJobs((prev) => {
            const existingIds = new Set(prev.map((j) => j.id));
            const uniqueNewJobs = newJobs.filter((j) => !existingIds.has(j.id));
            return [...prev, ...uniqueNewJobs];
          });
        }

        setTotal(res.total || 0);
        setHasMore(newJobs.length === 20);
        setPage(pageNumber);
      } catch (e: any) {
        if (signal?.aborted) return;
        console.error("Failed to fetch jobs", e);
        if (pageNumber === 1) {
          setError(e.message || "Failed to load jobs");
        }
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [isOpenSearch, q, location, remote, role, degree, experience, currentSalary, sortMode]
  );

  // Trigger search on filter changes or mode change
  useEffect(() => {
    const controller = new AbortController();
    fetchJobs(1, controller.signal);

    const handleProfileUpdate = () => {
      fetchJobs(1, controller.signal);
    };
    window.addEventListener("profileUpdated", handleProfileUpdate);

    return () => {
      controller.abort();
      window.removeEventListener("profileUpdated", handleProfileUpdate);
    };
  }, [fetchJobs, apiMode, isOpenSearch]);

  // Infinite Scroll Observer
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading && !loadingMore) {
          fetchJobs(page + 1);
        }
      },
      { threshold: 0.5 }
    );

    if (observerTarget.current) {
      observer.observe(observerTarget.current);
    }

    return () => {
      if (observerTarget.current) {
        observer.unobserve(observerTarget.current);
      }
    };
  }, [hasMore, loading, loadingMore, page, fetchJobs]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      fetchJobs(1);
    }
  };

  const handleClearAllFilters = () => {
    setQ("");
    setLocation("");
    setRemote(false);
    setRole("");
    setDegree("");
    setExperience("");
    setSalaryPreset("");
  };

  const hasActiveFilters = Boolean(
    q || location || remote || role || degree || experience || salaryPreset
  );

  const sortedJobs = [...jobs].sort((a, b) => {
    if (sortMode === "score") {
      const scoreDiff = (b.matchScore || 0) - (a.matchScore || 0);
      if (scoreDiff !== 0) return scoreDiff;
    }
    if (sortMode === "discovered") {
      const tsB = b.discovered_at || b.created_at;
      const tsA = a.discovered_at || a.created_at;
      const timeB = tsB ? new Date(tsB).getTime() : 0;
      const timeA = tsA ? new Date(tsA).getTime() : 0;
      return timeB - timeA;
    }
    // "posted_at" mode (Default): strictly newest employer posting date first, NULLS LAST
    const timeB = b.posted_at ? new Date(b.posted_at).getTime() : -1;
    const timeA = a.posted_at ? new Date(a.posted_at).getTime() : -1;
    if (timeB !== timeA) return timeB - timeA;

    // Tie-breaker if both posted_at are equal or null: discovered timestamp
    const discB = b.discovered_at || b.created_at;
    const discA = a.discovered_at || a.created_at;
    return (discB ? new Date(discB).getTime() : 0) - (discA ? new Date(discA).getTime() : 0);
  });

  return (
    <div className="flex flex-col max-w-6xl mx-auto w-full px-4 sm:px-6 py-8 relative">
      {/* Ambient Cyber Hero Glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[850px] h-[300px] bg-gradient-to-b from-[#c8f542]/[0.07] via-[#c8f542]/[0.02] to-transparent blur-3xl pointer-events-none -z-10" />

      {/* Top Header & Search Bar */}
      <div className="flex flex-col gap-5 mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2.5">
              <Compass className="w-7 h-7 text-[#c8f542] shrink-0" />
              {isOpenSearch ? "All Opportunities" : "Matched Opportunities"}
              <span className="text-xs sm:text-sm font-semibold px-2.5 py-0.5 rounded-full bg-[#c8f542]/10 border border-[#c8f542]/30 text-[#c8f542] font-mono">
                {total.toLocaleString()} opportunities
              </span>
            </h1>
            <p className="text-xs sm:text-sm text-muted-foreground mt-1">
              Direct job opportunities from verified employer career boards.
            </p>
          </div>

          {/* Quick Stats / Action Bar */}
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <Button
              id="refresh-jobs-btn"
              variant="outline"
              size="sm"
              onClick={() => fetchJobs(1)}
              className="h-9 gap-1.5 border-white/10 text-xs hover:border-[#c8f542]/40 hover:text-[#c8f542] bg-card/40 backdrop-blur-md"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>

            {/* Sort Menu */}
            <DropdownMenu>
              <DropdownMenuTrigger
                id="sort-menu-btn"
                className={buttonVariants({ variant: "outline", size: "sm" }) + " h-9 gap-1.5 border-white/10 text-xs cursor-pointer bg-card/40 backdrop-blur-md hover:border-[#c8f542]/40 hover:text-[#c8f542]"}
              >
                <ArrowDownWideNarrow className="w-3.5 h-3.5 text-[#c8f542]" />
                Sort: {sortMode === "posted_at" ? "Recently Posted" : sortMode === "discovered" ? "Recently Discovered" : "Match Score"}
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 bg-card/95 border-border backdrop-blur-xl">
                <DropdownMenuItem
                  id="sort-posted-btn"
                  className={`cursor-pointer text-xs flex items-center justify-between ${sortMode === "posted_at" ? "text-[#c8f542] font-semibold bg-[#c8f542]/10" : ""}`}
                  onClick={() => {
                    setSortMode("posted_at");
                    setPage(1);
                  }}
                >
                  <span className="flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-[#c8f542]" />
                    Recently Posted (Job Post Time)
                  </span>
                  {sortMode === "posted_at" && <span className="text-[#c8f542] text-xs font-bold">✓</span>}
                </DropdownMenuItem>
                <DropdownMenuItem
                  id="sort-discovered-btn"
                  className={`cursor-pointer text-xs flex items-center justify-between ${sortMode === "discovered" ? "text-[#c8f542] font-semibold bg-[#c8f542]/10" : ""}`}
                  onClick={() => {
                    setSortMode("discovered");
                    setPage(1);
                  }}
                >
                  <span className="flex items-center gap-2">
                    <Compass className="w-3.5 h-3.5 text-zinc-400" />
                    Recently Discovered (Found Time)
                  </span>
                  {sortMode === "discovered" && <span className="text-[#c8f542] text-xs font-bold">✓</span>}
                </DropdownMenuItem>
                <DropdownMenuItem
                  id="sort-score-btn"
                  className={`cursor-pointer text-xs flex items-center justify-between ${sortMode === "score" ? "text-[#c8f542] font-semibold bg-[#c8f542]/10" : ""}`}
                  onClick={() => {
                    setSortMode("score");
                    setPage(1);
                  }}
                >
                  <span className="flex items-center gap-2">
                    <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                    Highest Match Score
                  </span>
                  {sortMode === "score" && <span className="text-[#c8f542] text-xs font-bold">✓</span>}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Primary Search Inputs (Keyword & Location Command Center) */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 p-3 bg-card/60 border border-white/10 rounded-2xl backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.35)] focus-within:border-white/20 transition-all">
          <div className="relative md:col-span-6 flex items-center">
            <Search className="absolute left-3.5 top-3.5 h-4 w-4 text-muted-foreground" />
            <input
              id="keyword-search-input"
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Title, skills, or company (e.g. Software Engineer, React, Python...)"
              className="w-full bg-zinc-950/70 border border-white/10 rounded-xl pl-10 pr-9 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:outline-none focus:border-[#c8f542]/70 focus:ring-1 focus:ring-[#c8f542]/30 transition-all"
            />
            {q && (
              <button
                onClick={() => setQ("")}
                className="absolute right-3 text-zinc-400 hover:text-white transition-colors"
                title="Clear keyword"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <div className="relative md:col-span-4 flex items-center">
            <MapPin className="absolute left-3.5 top-3.5 h-4 w-4 text-muted-foreground" />
            <input
              id="location-search-input"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Location (e.g. Chennai, Bengaluru, Remote...)"
              className="w-full bg-zinc-950/70 border border-white/10 rounded-xl pl-10 pr-9 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:outline-none focus:border-[#c8f542]/70 focus:ring-1 focus:ring-[#c8f542]/30 transition-all"
            />
            {location && (
              <button
                onClick={() => setLocation("")}
                className="absolute right-3 text-zinc-400 hover:text-white transition-colors"
                title="Clear location"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 md:col-span-2">
            <Button
              id="search-submit-btn"
              onClick={() => fetchJobs(1)}
              className="w-full h-full min-h-[42px] bg-[#c8f542] hover:bg-[#d8ff4e] text-black font-bold text-sm rounded-xl shadow-[0_0_15px_rgba(200,245,66,0.25)] transition-all hover:scale-[1.02]"
            >
              Search
            </Button>
          </div>
        </div>

        {/* Multi-Attribute Filter Bar: Degree, Role, Experience, Salary, Location Pills */}
        <div className="flex flex-col gap-2 p-3 rounded-2xl bg-card/30 border border-white/[0.06] backdrop-blur-md">
          {/* Tier 1: Macro Region & Major Metros */}
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-muted-foreground mr-1 font-medium flex items-center gap-1 text-[11px] tracking-wide uppercase">
              <MapPin className="w-3.5 h-3.5 text-[#c8f542]" /> Metros:
            </span>
            {METRO_HUBS.map((hub) => {
              const active = location.toLowerCase().includes(hub.id);
              const count = locationStats[hub.statKey]?.count;
              return (
                <button
                  key={hub.id}
                  id={`hub-pill-${hub.id.replace(/\s+/g, "-")}`}
                  onClick={() => {
                    setLocation(active ? "" : hub.label);
                  }}
                  className={`px-3 py-1 rounded-full border transition-all text-xs flex items-center gap-1.5 cursor-pointer ${
                    active
                      ? "bg-[#c8f542] text-black font-bold border-[#c8f542] shadow-[0_0_12px_rgba(200,245,66,0.25)]"
                      : "bg-card/40 border-white/10 text-zinc-300 hover:border-white/30 hover:bg-white/[0.05]"
                  }`}
                >
                  <span>{hub.label}</span>
                  {count !== undefined && (
                    <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded-full ${
                      active ? "bg-black/20 text-black font-bold" : "bg-white/10 text-zinc-300"
                    }`}>
                      {count.toLocaleString()}
                    </span>
                  )}
                </button>
              );
            })}

            <button
              id="remote-only-toggle"
              onClick={() => setRemote(!remote)}
              className={`px-3 py-1 rounded-full border transition-all text-xs flex items-center gap-1.5 cursor-pointer ${
                remote
                  ? "bg-[#c8f542] text-black font-bold border-[#c8f542] shadow-[0_0_10px_rgba(200,245,66,0.25)]"
                  : "bg-card/40 border-white/10 text-zinc-300 hover:border-white/30 hover:bg-white/[0.05]"
              }`}
            >
              <Globe className="w-3.5 h-3.5" />
              <span>Remote Only</span>
            </button>
          </div>

          {/* Tier 2: Corridors Dropdown (All India) + South India City Corridors */}
          <div className="flex flex-wrap items-center gap-1.5 text-xs pt-1 border-t border-white/[0.04]">
            {/* The "Corridors" Dropdown Button */}
            <DropdownMenu>
              <DropdownMenuTrigger
                id="corridors-dropdown-btn"
                className={`px-3 py-1 rounded-full border transition-all text-xs flex items-center gap-1.5 cursor-pointer font-semibold ${
                  ALL_INDIA_CORRIDORS.some((g) =>
                    g.corridors.some(
                      (c) =>
                        location.toLowerCase().includes(c.id) ||
                        location.toLowerCase().includes(c.label.toLowerCase())
                    )
                  )
                    ? "bg-[#c8f542] text-black border-[#c8f542] shadow-[0_0_12px_rgba(200,245,66,0.3)]"
                    : "bg-card/50 border-white/20 text-white hover:border-[#c8f542]/50 hover:bg-white/[0.06]"
                }`}
              >
                <Building2
                  className={`w-3.5 h-3.5 ${
                    ALL_INDIA_CORRIDORS.some((g) =>
                      g.corridors.some(
                        (c) =>
                          location.toLowerCase().includes(c.id) ||
                          location.toLowerCase().includes(c.label.toLowerCase())
                      )
                    )
                      ? "text-black"
                      : "text-[#c8f542]"
                  }`}
                />
                <span>Corridors</span>
                <ChevronDown className="w-3 h-3 opacity-70" />
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="start"
                className="w-80 sm:w-96 max-h-[460px] overflow-y-auto bg-card/95 border-border backdrop-blur-xl p-2 z-50 custom-scrollbar shadow-2xl"
              >
                <div className="px-2 py-1.5 mb-1 border-b border-white/[0.08] flex items-center justify-between">
                  <div>
                    <p className="text-xs font-bold text-white flex items-center gap-1.5">
                      <Building2 className="w-3.5 h-3.5 text-[#c8f542]" /> All India Tech Corridors
                    </p>
                    <p className="text-[11px] text-muted-foreground">Select any tech corridor to filter jobs</p>
                  </div>
                  {location && (
                    <button
                      onClick={() => setLocation("")}
                      className="text-[11px] text-zinc-400 hover:text-white underline cursor-pointer"
                    >
                      Clear
                    </button>
                  )}
                </div>
                {ALL_INDIA_CORRIDORS.map((group) => (
                  <div key={group.region} className="mb-2 last:mb-0">
                    <DropdownMenuLabel className="text-[11px] font-semibold text-[#c8f542] uppercase tracking-wider px-2 py-1 flex items-center gap-1.5">
                      {group.region}
                    </DropdownMenuLabel>
                    <div className="space-y-0.5">
                      {group.corridors.map((c) => {
                        const active =
                          location.toLowerCase().includes(c.id) ||
                          location.toLowerCase().includes(c.label.toLowerCase());
                        const count = c.statKey ? locationStats[c.statKey]?.count : undefined;
                        return (
                          <DropdownMenuItem
                            key={c.id}
                            onClick={() => setLocation(active ? "" : c.label)}
                            className={`flex items-start justify-between p-2 rounded-lg cursor-pointer text-xs transition-colors ${
                              active
                                ? "bg-[#c8f542]/15 text-[#c8f542] font-semibold"
                                : "hover:bg-white/[0.05] text-zinc-200"
                            }`}
                          >
                            <div className="flex flex-col gap-0.5 pr-2">
                              <span className="font-medium text-white flex items-center gap-1.5">
                                {c.label}
                                <span className="text-[10px] text-muted-foreground font-normal">
                                  ({c.city})
                                </span>
                              </span>
                              <span className="text-[10px] text-muted-foreground line-clamp-1">
                                {c.landmarks}
                              </span>
                            </div>
                            {count !== undefined && (
                              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-white/10 text-zinc-300 shrink-0">
                                {count.toLocaleString()}
                              </span>
                            )}
                          </DropdownMenuItem>
                        );
                      })}
                    </div>
                    <DropdownMenuSeparator className="my-1.5 bg-white/[0.06]" />
                  </div>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Quick South India City Corridor Pills */}
            {SOUTH_INDIA_CORRIDORS.map((c) => {
              const active =
                location.toLowerCase().includes(c.id) ||
                location.toLowerCase().includes(c.label.toLowerCase());
              const count = locationStats[c.statKey]?.count;
              return (
                <button
                  key={c.id}
                  id={`corridor-pill-${c.id.replace(/\s+/g, "-")}`}
                  title={`${c.city}: ${c.desc}`}
                  onClick={() => {
                    setLocation(active ? "" : c.label);
                  }}
                  className={`px-3 py-1 rounded-full border transition-all text-xs flex items-center gap-1.5 cursor-pointer ${
                    active
                      ? "bg-[#c8f542] text-black font-bold border-[#c8f542] shadow-[0_0_12px_rgba(200,245,66,0.25)]"
                      : "bg-card/30 border-white/10 text-zinc-300 hover:border-white/30 hover:bg-white/[0.04]"
                  }`}
                >
                  <span>{c.label}</span>
                  <span className="text-[10px] text-zinc-400">({c.city})</span>
                  {count !== undefined && (
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.2 rounded-full ${
                        active ? "bg-black/20 text-black font-bold" : "bg-white/10 text-zinc-300"
                      }`}
                    >
                      {count.toLocaleString()}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Dropdown Filters row */}
          <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-white/[0.04]">
            {/* Degree Dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger
                id="degree-filter-btn"
                className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full border text-xs font-medium cursor-pointer transition-all ${
                  degree
                    ? "bg-[#c8f542]/15 text-[#c8f542] border-[#c8f542]/50 font-bold"
                    : "bg-card/40 border-white/10 text-zinc-300 hover:border-white/20"
                }`}
              >
                <GraduationCap className="w-3.5 h-3.5" />
                {degree ? `Degree: ${degree}` : "Degree"}
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-64 bg-card/95 border-border backdrop-blur-xl">
                <DropdownMenuLabel className="text-xs text-muted-foreground">Select Qualification</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {DEGREES.map((d) => (
                  <DropdownMenuItem
                    key={d.id}
                    id={`degree-opt-${d.id || "all"}`}
                    onClick={() => setDegree(d.id)}
                    className={`cursor-pointer text-xs flex items-center justify-between ${
                      degree === d.id ? "text-[#c8f542] font-bold" : ""
                    }`}
                  >
                    {d.label}
                    {degree === d.id && <span className="text-[#c8f542]">✓</span>}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Role Dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger
                id="role-filter-btn"
                className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full border text-xs font-medium cursor-pointer transition-all ${
                  role
                    ? "bg-blue-500/15 text-blue-400 border-blue-500/50 font-bold"
                    : "bg-card/40 border-white/10 text-zinc-300 hover:border-white/20"
                }`}
              >
                <Briefcase className="w-3.5 h-3.5" />
                {role ? `Role: ${ROLES.find((r) => r.id === role)?.label || role}` : "Role Category"}
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-56 bg-card/95 border-border backdrop-blur-xl">
                <DropdownMenuLabel className="text-xs text-muted-foreground">Tech Role Specialization</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {ROLES.map((r) => (
                  <DropdownMenuItem
                    key={r.id}
                    id={`role-opt-${r.id || "all"}`}
                    onClick={() => setRole(r.id)}
                    className={`cursor-pointer text-xs flex items-center justify-between ${
                      role === r.id ? "text-[#c8f542] font-bold" : ""
                    }`}
                  >
                    {r.label}
                    {role === r.id && <span className="text-[#c8f542]">✓</span>}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Experience Level Dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger
                id="exp-filter-btn"
                className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full border text-xs font-medium cursor-pointer transition-all ${
                  experience
                    ? "bg-purple-500/15 text-purple-400 border-purple-500/50 font-bold"
                    : "bg-card/40 border-white/10 text-zinc-300 hover:border-white/20"
                }`}
              >
                <Clock className="w-3.5 h-3.5" />
                {experience
                  ? `Exp: ${EXPERIENCES.find((e) => e.id === experience)?.label || experience}`
                  : "Experience"}
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-56 bg-card/95 border-border backdrop-blur-xl">
                <DropdownMenuLabel className="text-xs text-muted-foreground">Experience Range</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {EXPERIENCES.map((e) => (
                  <DropdownMenuItem
                    key={e.id}
                    id={`exp-opt-${e.id || "all"}`}
                    onClick={() => setExperience(e.id)}
                    className={`cursor-pointer text-xs flex items-center justify-between ${
                      experience === e.id ? "text-[#c8f542] font-bold" : ""
                    }`}
                  >
                    {e.label}
                    {experience === e.id && <span className="text-[#c8f542]">✓</span>}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Salary Range Dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger
                id="salary-filter-btn"
                className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full border text-xs font-medium cursor-pointer transition-all ${
                  salaryPreset
                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/50 font-bold"
                    : "bg-card/40 border-white/10 text-zinc-300 hover:border-white/20"
                }`}
              >
                <Banknote className="w-3.5 h-3.5" />
                {salaryPreset
                  ? `Salary: ${SALARY_PRESETS.find((s) => s.id === salaryPreset)?.label}`
                  : "Salary Bracket"}
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-52 bg-card/95 border-border backdrop-blur-xl">
                <DropdownMenuLabel className="text-xs text-muted-foreground">Compensation Range</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {SALARY_PRESETS.map((s) => (
                  <DropdownMenuItem
                    key={s.id}
                    id={`salary-opt-${s.id || "all"}`}
                    onClick={() => setSalaryPreset(s.id)}
                    className={`cursor-pointer text-xs flex items-center justify-between ${
                      salaryPreset === s.id ? "text-[#c8f542] font-bold" : ""
                    }`}
                  >
                    {s.label}
                    {salaryPreset === s.id && <span className="text-[#c8f542]">✓</span>}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Clear All Button */}
            {hasActiveFilters && (
              <button
                id="clear-all-filters-btn"
                onClick={handleClearAllFilters}
                className="inline-flex items-center gap-1 h-8 px-2.5 rounded-full text-xs text-muted-foreground hover:text-white hover:bg-white/[0.08] transition-colors"
              >
                <X className="w-3.5 h-3.5" />
                Clear All
              </button>
            )}
          </div>
        </div>

        {/* Active Filter Chips Bar */}
        {hasActiveFilters && (
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-[11px] text-muted-foreground font-medium">Active Filters:</span>
            {q && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs bg-white/[0.06] border border-white/10 text-white">
                "{q}"
                <X className="w-3 h-3 cursor-pointer hover:text-red-400" onClick={() => setQ("")} />
              </span>
            )}
            {location && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs bg-white/[0.06] border border-white/10 text-white">
                <MapPin className="w-3 h-3 text-[#c8f542]" />
                {location}
                <X className="w-3 h-3 cursor-pointer hover:text-red-400" onClick={() => setLocation("")} />
              </span>
            )}
            {degree && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs bg-[#c8f542]/10 border border-[#c8f542]/30 text-[#c8f542] font-medium">
                <GraduationCap className="w-3 h-3" />
                {degree}
                <X className="w-3 h-3 cursor-pointer hover:text-white" onClick={() => setDegree("")} />
              </span>
            )}
            {role && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs bg-blue-500/10 border border-blue-500/30 text-blue-400 font-medium">
                <Briefcase className="w-3 h-3" />
                {ROLES.find((r) => r.id === role)?.label || role}
                <X className="w-3 h-3 cursor-pointer hover:text-white" onClick={() => setRole("")} />
              </span>
            )}
            {experience && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs bg-purple-500/10 border border-purple-500/30 text-purple-400 font-medium">
                <Clock className="w-3 h-3" />
                {EXPERIENCES.find((e) => e.id === experience)?.label || experience}
                <X className="w-3 h-3 cursor-pointer hover:text-white" onClick={() => setExperience("")} />
              </span>
            )}
            {salaryPreset && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-medium">
                <Banknote className="w-3 h-3" />
                {SALARY_PRESETS.find((s) => s.id === salaryPreset)?.label}
                <X className="w-3 h-3 cursor-pointer hover:text-white" onClick={() => setSalaryPreset("")} />
              </span>
            )}
            {remote && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs bg-teal-500/10 border border-teal-500/30 text-teal-400 font-medium">
                <Globe className="w-3 h-3" />
                Remote
                <X className="w-3 h-3 cursor-pointer hover:text-white" onClick={() => setRemote(false)} />
              </span>
            )}
          </div>
        )}

        {/* Active Location & Corridor Banner */}
        {location && (
          <div className="flex items-center justify-between px-4 py-2.5 rounded-2xl bg-gradient-to-r from-card/80 via-card/50 to-transparent border-l-4 border-l-[#c8f542] border border-white/10 text-xs backdrop-blur-md shadow-md">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[#c8f542] font-semibold flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5" /> Active Location Filter:
              </span>
              <span className="text-white font-bold bg-[#c8f542]/20 text-[#c8f542] px-2.5 py-0.5 rounded-lg border border-[#c8f542]/40 shadow-sm flex items-center gap-1.5">
                {location}
                <X
                  className="w-3 h-3 cursor-pointer hover:text-white"
                  onClick={() => setLocation("")}
                />
              </span>
              <span className="inline-flex items-center gap-1.5 bg-white/[0.06] text-zinc-300 px-2.5 py-0.5 rounded-full text-[11px] font-mono border border-white/10 ml-1">
                {total.toLocaleString()} Matching Jobs
              </span>
            </div>
            <button
              id="reset-location-breadcrumb"
              onClick={() => setLocation("")}
              className="text-xs text-zinc-400 hover:text-white transition-colors underline cursor-pointer ml-3 shrink-0"
            >
              Clear Location ✕
            </button>
          </div>
        )}
      </div>

      {/* Job Feed List */}
      <div className="flex-1 pr-1 pb-8 space-y-3.5">
        {loading ? (
          <div className="flex flex-col justify-center items-center py-24 gap-3">
            <Loader2 className="w-8 h-8 text-[#c8f542] animate-spin" />
            <p className="text-sm text-muted-foreground">
              Loading opportunities...
            </p>
          </div>
        ) : error ? (
          <div className="text-center py-16 bg-destructive/10 rounded-[24px] border border-destructive/20 p-6">
            <AlertCircle className="w-8 h-8 text-destructive mx-auto mb-3" />
            <p className="text-destructive font-medium mb-1">Failed to query jobs</p>
            <p className="text-xs text-muted-foreground mb-4">{error}</p>
            <Button
              variant="outline"
              onClick={() => fetchJobs(1)}
              className="text-destructive border-destructive/20 hover:bg-destructive/10"
            >
              Try Again
            </Button>
          </div>
        ) : sortedJobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center bg-card/20 rounded-[24px] border border-white/5 p-8">
            <div className="p-4 rounded-full bg-white/[0.03] border border-white/10 mb-4 text-muted-foreground">
              <Search className="w-10 h-10" />
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">No matching jobs found</h3>
            <p className="text-sm text-muted-foreground max-w-md mb-5">
              We couldn't find active listings matching your exact combination of criteria. Try broadening your location, degree, or role filters.
            </p>
            {hasActiveFilters && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearAllFilters}
                className="border-white/10 hover:border-[#c8f542]/50 hover:text-[#c8f542]"
              >
                Reset All Filters
              </Button>
            )}
          </div>
        ) : (
          <>
            {sortedJobs.map((job) => (
              <JobCard
                key={job.id}
                id={job.id}
                title={job.title}
                company={job.company_name}
                location={job.location || "Remote"}
                source={job.status === "ACTIVE" ? "Direct" : job.status}
                matchScore={job.matchScore}
                matchReasons={job.matchReasons}
                timeAgo={job.timeAgo}
                type={job.job_type || "Full-time"}
                hideMatchScore={isOpenSearch}
                externalUrl={job.canonical_apply_url}
                salaryMin={job.salary_min}
                salaryMax={job.salary_max}
                salaryCurrency={job.salary_currency}
                educationLevel={job.education_level}
                roleCategory={job.role_category}
                experienceLevel={job.experience_level}
                corridor={job.corridor}
                city={job.city}
                postedAt={job.posted_at}
                discoveredAt={job.discovered_at}
                onPrepareApplication={async () => {
                  try {
                    await api.post("/applications", { job_id: job.id });
                    alert("Application preparation started. View it in the Applications tab.");
                  } catch (e: any) {
                    alert(e.message || "Failed to prepare application");
                  }
                }}
              />
            ))}

            {/* Infinite Scroll Sentinel */}
            {hasMore && (
              <div ref={observerTarget} className="flex justify-center items-center py-8">
                {loadingMore && <Loader2 className="w-6 h-6 text-[#c8f542] animate-spin" />}
              </div>
            )}

            {!hasMore && jobs.length > 0 && (
              <div className="py-8 text-center">
                <p className="text-xs text-muted-foreground">
                  Showing all {total} discovered opportunities. Use filters above to narrow your search.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
