"use client";

import { useState, useEffect, useRef } from "react";
import { JobCard } from "@/components/jobs/job-card";
import { Sparkles, SlidersHorizontal, ArrowDownWideNarrow, Search, MapPin, Loader2, AlertCircle } from "lucide-react";
import { useSearchMode, useAppState } from "@/components/providers";
import { api } from "@/lib/api";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type JobResponse = {
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
};

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
  
  // Search states
  const [q, setQ] = useState("");
  const [location, setLocation] = useState("");
  const [remote, setRemote] = useState(false);
  const [sortMode, setSortMode] = useState<"recent" | "score">(isOpenSearch ? "recent" : "score");

  const fetchJobs = async (pageNumber: number = 1, signal?: AbortSignal) => {
    if (pageNumber === 1) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    setError(null);
    
    try {
      let endpoint = "/jobs";
      const params = new URLSearchParams();
      params.append("page", pageNumber.toString());
      params.append("limit", "20");
      
      if (isOpenSearch) {
        if (q) params.append("q", q);
        if (location) params.append("location", location);
        if (remote) params.append("remote", "true");
        endpoint = `/jobs?${params.toString()}`;
      } else {
        endpoint = `/jobs/match?${params.toString()}`;
      }
      
      const res = await api.get<{items: JobResponse[], total: number}>(endpoint);
      
      if (signal?.aborted) return;
      
      const newJobs = res.items || [];
      if (pageNumber === 1) {
        setJobs(newJobs);
      } else {
        setJobs(prev => {
          const existingIds = new Set(prev.map(j => j.id));
          const uniqueNewJobs = newJobs.filter(j => !existingIds.has(j.id));
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
  };

  useEffect(() => {
    const controller = new AbortController();
    fetchJobs(1, controller.signal);
    
    const handleProfileUpdate = () => {
      fetchJobs(1, controller.signal);
    };
    window.addEventListener('profileUpdated', handleProfileUpdate);
    
    return () => {
      controller.abort();
      window.removeEventListener('profileUpdated', handleProfileUpdate);
    };
  }, [apiMode, isOpenSearch]);

  // Infinite Scroll Observer
  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !loading && !loadingMore) {
          fetchJobs(page + 1);
        }
      },
      { threshold: 1.0 }
    );
    
    if (observerTarget.current) {
      observer.observe(observerTarget.current);
    }
    
    return () => {
      if (observerTarget.current) {
        observer.unobserve(observerTarget.current);
      }
    };
  }, [hasMore, loading, loadingMore, page, q, location, remote, isOpenSearch]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      fetchJobs(1);
    }
  };

  const sortedJobs = [...jobs].sort((a, b) => {
    if (sortMode === 'score') {
      return (b.matchScore || 0) - (a.matchScore || 0);
    }
    return 0;
  });

  return (
    <div className="flex flex-col h-full max-w-6xl mx-auto w-full px-6 py-8 overflow-y-auto">
      {/* Header Area */}
      <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
        {isOpenSearch ? (
          <div className="w-full">
            <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2 mb-4">
              <Search className="w-6 h-6 text-primary" />
              Open Search {total > 0 && <span className="text-xl font-normal text-muted-foreground ml-2">({total} jobs)</span>}
            </h1>
            <div className="flex flex-col md:flex-row gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <input 
                  type="text" 
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Job title, keywords, or company (Press Enter to search)" 
                  className="w-full bg-card/40 border border-white/10 rounded-full pl-9 pr-4 py-2 text-sm text-white focus:outline-none focus:border-primary/50"
                />
              </div>
              <div className="relative flex-1">
                <MapPin className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <input 
                  type="text" 
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="City, state, or zip code (Press Enter to search)" 
                  className="w-full bg-card/40 border border-white/10 rounded-full pl-9 pr-4 py-2 text-sm text-white focus:outline-none focus:border-primary/50"
                />
              </div>
              <div className="flex-1" />
            </div>
          </div>
        ) : (
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2 mb-2">
              <Sparkles className="w-6 h-6 text-primary" />
              Discover {total > 0 && <span className="text-xl font-normal text-muted-foreground ml-2">({total} matches)</span>}
            </h1>
            <p className="text-muted-foreground">Curated opportunities matching your active profile.</p>
          </div>
        )}
        
        <div className="flex items-center gap-3 shrink-0">
          <DropdownMenu>
            <DropdownMenuTrigger className={buttonVariants({ variant: "outline", size: "sm" }) + " h-9 gap-2 cursor-pointer"}>
              <SlidersHorizontal className="w-4 h-4" />
              Filters
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48 bg-card border-border backdrop-blur-xl">
              <DropdownMenuCheckboxItem
                checked={remote}
                onCheckedChange={(checked) => {
                  setRemote(checked);
                  setTimeout(() => fetchJobs(1), 50);
                }}
                className="cursor-pointer"
              >
                Remote Only
              </DropdownMenuCheckboxItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger className={buttonVariants({ variant: "outline", size: "sm" }) + " h-9 gap-2 cursor-pointer"}>
              <ArrowDownWideNarrow className="w-4 h-4" />
              Sort: {sortMode === 'recent' ? 'Recent' : 'Match Score'}
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48 bg-card border-border backdrop-blur-xl">
              <DropdownMenuItem className="cursor-pointer" onClick={() => setSortMode('recent')}>
                Most Recent
              </DropdownMenuItem>
              <DropdownMenuItem className="cursor-pointer" onClick={() => setSortMode('score')}>
                Highest Match Score
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Job Feed */}
      <div className="flex-1 pr-2 pb-8 space-y-4">
        {loading ? (
          <div className="flex justify-center items-center py-20">
            <Loader2 className="w-8 h-8 text-primary animate-spin" />
          </div>
        ) : error ? (
          <div className="text-center py-20 bg-destructive/10 rounded-[24px] border border-destructive/20">
            <AlertCircle className="w-8 h-8 text-destructive mx-auto mb-4" />
            <p className="text-destructive font-medium">{error}</p>
            <Button variant="outline" onClick={() => fetchJobs(1)} className="mt-4 text-destructive border-destructive/20 hover:bg-destructive/10">Try Again</Button>
          </div>
        ) : sortedJobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Search className="w-12 h-12 text-muted-foreground mb-4" />
            <h3 className="text-xl font-medium text-white mb-2">No jobs found</h3>
            <p className="text-muted-foreground max-w-md">Try adjusting your filters or search terms.</p>
          </div>
        ) : (
          <>
            {sortedJobs.map(job => (
              <JobCard 
                key={job.id}
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
                {loadingMore && <Loader2 className="w-6 h-6 text-primary animate-spin" />}
              </div>
            )}
            
            {!hasMore && jobs.length > 0 && (
              <div className="py-8 text-center">
                <p className="text-sm text-muted-foreground">
                  {isOpenSearch ? "End of search results." : "You've reached the end of your matched feed."}
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
