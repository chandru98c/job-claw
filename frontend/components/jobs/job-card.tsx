import React from "react";
import { Building2, MapPin, Clock, ExternalLink, Briefcase } from "lucide-react";
import { Button } from "@/components/ui/button";

interface JobCardProps {
  title: string;
  company: string;
  location: string;
  source: string;
  matchScore: number | null;
  timeAgo: string;
  type?: string;
  hideMatchScore?: boolean;
  matchReasons?: string[] | null;
  onPrepareApplication?: () => void;
  externalUrl?: string;
}

export function JobCard({ title, company, location, source, matchScore, timeAgo, type = "Full-time", hideMatchScore = false, matchReasons = null, onPrepareApplication, externalUrl }: JobCardProps) {
  // Determine color based on match score
  const safeScore = matchScore || 0;
  const scoreColor = safeScore >= 90 ? "text-primary" : safeScore >= 75 ? "text-yellow-400" : "text-muted-foreground";
  const ringColor = safeScore >= 90 ? "stroke-primary" : safeScore >= 75 ? "stroke-yellow-500" : "stroke-zinc-500";
  const glowColor = safeScore >= 90 ? "shadow-[0_0_10px_rgba(34,197,94,0.2)]" : "";

  return (
    <div className={`group relative bg-card/40 border border-white/[0.08] hover:border-white/[0.15] hover:bg-card/60 rounded-[24px] p-5 transition-all duration-300 hover:-translate-y-0.5 ${glowColor}`}>
      <div className="flex items-start justify-between">
        
        {/* Left Content */}
        <div className="flex-1 min-w-0 pr-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider bg-white/[0.03] border border-white/[0.05] text-muted-foreground rounded-full">
              Source: {source}
            </span>
            <span className="text-xs text-muted-foreground">{timeAgo}</span>
          </div>
          
          <h3 className="text-lg font-semibold text-zinc-100 truncate mb-1 group-hover:text-white transition-colors">
            {title}
          </h3>
          
          <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
            <div className="flex items-center gap-1.5">
              <Building2 className="w-4 h-4" />
              <span className="truncate">{company}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <MapPin className="w-4 h-4" />
              <span className="truncate">{location}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-medium bg-zinc-800/50 text-muted-foreground px-2 py-1 rounded-full border border-border">
              <Briefcase className="w-3.5 h-3.5" />
              {type}
            </span>
            {matchReasons && matchReasons.map((reason, idx) => (
              <span key={idx} className="inline-flex items-center text-[10px] font-mono text-primary/80 bg-primary/10 px-2 py-1 rounded-full border border-primary/20 uppercase">
                {reason.replace("_MATCH", "")}
              </span>
            ))}
          </div>
        </div>

        {/* Right Content (Match Score & Actions) */}
        <div className="flex flex-col items-end justify-between h-full">
          {!hideMatchScore && (
            <div className="relative w-14 h-14 flex items-center justify-center">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                <path
                  className="stroke-white/5"
                  strokeWidth="3"
                  fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
                <path
                  className={`${ringColor} drop-shadow-md`}
                  strokeDasharray={`${safeScore}, 100`}
                  strokeWidth="3"
                  strokeLinecap="round"
                  fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className={`text-sm font-bold ${scoreColor}`}>{safeScore}</span>
                <span className="text-[8px] text-muted-foreground uppercase font-bold -mt-1">Match</span>
              </div>
            </div>
          )}
          
          <div className={`flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity ${hideMatchScore ? 'mt-0' : 'mt-4'}`}>
            {onPrepareApplication && (
              <Button 
                size="sm"
                onClick={onPrepareApplication}
                title="Prepare Application Internally"
              >
                Prepare App
              </Button>
            )}
            {externalUrl && (
              <a 
                href={externalUrl} 
                target="_blank" 
                rel="noreferrer"
                className="p-2 rounded-full hover:bg-white/10 text-muted-foreground hover:text-white transition-colors"
                title="Open External URL"
              >
                <ExternalLink className="w-5 h-5" />
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
