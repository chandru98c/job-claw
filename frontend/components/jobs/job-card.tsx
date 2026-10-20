import React from "react";
import { Building2, MapPin, Clock, ExternalLink, Briefcase, GraduationCap, Banknote, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";

interface JobCardProps {
  id?: string;
  title: string;
  company: string;
  location: string;
  source: string;
  matchScore: number | null;
  timeAgo: string;
  type?: string;
  hideMatchScore?: boolean;
  matchReasons?: string[] | null;
  salaryMin?: number | null;
  salaryMax?: number | null;
  salaryCurrency?: string | null;
  educationLevel?: string | null;
  roleCategory?: string | null;
  experienceLevel?: string | null;
  corridor?: string | null;
  city?: string | null;
  postedAt?: string | null;
  discoveredAt?: string | null;
  onPrepareApplication?: () => void;
  externalUrl?: string;
}

const ROLE_LABELS: Record<string, { label: string; color: string }> = {
  software_engineer: { label: "Software Engineer", color: "bg-blue-500/10 text-blue-400 border-blue-500/20" },
  frontend: { label: "Frontend", color: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20" },
  backend: { label: "Backend", color: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20" },
  fullstack: { label: "Full Stack", color: "bg-violet-500/10 text-violet-400 border-violet-500/20" },
  data_ai: { label: "Data & AI", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
  devops_cloud: { label: "DevOps & Cloud", color: "bg-amber-500/10 text-amber-400 border-amber-500/20" },
  qa_testing: { label: "QA & Testing", color: "bg-teal-500/10 text-teal-400 border-teal-500/20" },
  mobile: { label: "Mobile", color: "bg-pink-500/10 text-pink-400 border-pink-500/20" },
  product: { label: "Product", color: "bg-purple-500/10 text-purple-400 border-purple-500/20" },
};

const EXP_LABELS: Record<string, { label: string; color: string }> = {
  fresher: { label: "🌱 Fresher (0 Yrs)", color: "bg-lime-500/15 text-[#c8f542] border-[#c8f542]/30 font-semibold" },
  junior: { label: "Junior (1-3 Yrs)", color: "bg-sky-500/10 text-sky-400 border-sky-500/20" },
  mid: { label: "Mid-Level (3-5 Yrs)", color: "bg-purple-500/10 text-purple-400 border-purple-500/20" },
  senior: { label: "Senior (5+ Yrs)", color: "bg-rose-500/10 text-rose-400 border-rose-500/20" },
};

function formatSalary(min: number | null | undefined, max: number | null | undefined, currency: string | null | undefined): string | null {
  if (!min && !max) return null;
  const curr = currency || (min && min >= 100000 ? "INR" : "USD");

  if (curr === "INR") {
    const formatLakh = (val: number) => {
      const lpa = val / 100000;
      return lpa % 1 === 0 ? `${lpa}` : `${lpa.toFixed(1)}`;
    };
    if (min && max) {
      return `₹${formatLakh(min)} - ${formatLakh(max)} LPA`;
    } else if (min) {
      return `₹${formatLakh(min)}+ LPA`;
    } else if (max) {
      return `Up to ₹${formatLakh(max)} LPA`;
    }
  } else if (curr === "USD") {
    const formatK = (val: number) => {
      if (val >= 1000) return `${Math.round(val / 1000)}k`;
      return `${val}`;
    };
    if (min && max) {
      return `$${formatK(min)} - $${formatK(max)}`;
    } else if (min) {
      return `$${formatK(min)}+`;
    } else if (max) {
      return `Up to $${formatK(max)}`;
    }
  }
  return null;
}

function getSourceBadge(source: string, url?: string) {
  const lowerUrl = (url || "").toLowerCase();
  const lowerSource = (source || "").toLowerCase();
  if (lowerUrl.includes("zohorecruit") || lowerSource.includes("zohorecruit")) {
    return { name: "Zoho Recruit", color: "text-amber-400 bg-amber-400/10 border-amber-400/20" };
  }
  if (lowerUrl.includes("greenhouse.io")) {
    return { name: "Greenhouse", color: "text-emerald-400 bg-emerald-400/10 border-emerald-400/20" };
  }
  if (lowerUrl.includes("ashbyhq.com")) {
    return { name: "Ashby", color: "text-purple-400 bg-purple-400/10 border-purple-400/20" };
  }
  if (lowerUrl.includes("lever.co")) {
    return { name: "Lever", color: "text-blue-400 bg-blue-400/10 border-blue-400/20" };
  }
  if (lowerUrl.includes("workable.com")) {
    return { name: "Workable", color: "text-teal-400 bg-teal-400/10 border-teal-400/20" };
  }
  if (lowerUrl.includes("naukri.com")) {
    return { name: "Naukri", color: "text-sky-400 bg-sky-400/10 border-sky-400/20" };
  }
  if (lowerUrl.includes("recruitee.com") || lowerSource.includes("recruitee")) {
    return { name: "Recruitee", color: "text-indigo-400 bg-indigo-400/10 border-indigo-400/20" };
  }
  if (lowerUrl.includes("breezy.hr") || lowerSource.includes("breezy")) {
    return { name: "Breezy HR", color: "text-cyan-400 bg-cyan-400/10 border-cyan-400/20" };
  }
  if (lowerUrl.includes("teamtailor.com") || lowerSource.includes("teamtailor")) {
    return { name: "Teamtailor", color: "text-rose-400 bg-rose-400/10 border-rose-400/20" };
  }
  if (lowerUrl.includes("personio") || lowerSource.includes("personio")) {
    return { name: "Personio", color: "text-fuchsia-400 bg-fuchsia-400/10 border-fuchsia-400/20" };
  }
  if (lowerUrl.includes("bamboohr") || lowerSource.includes("bamboohr")) {
    return { name: "BambooHR", color: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20" };
  }
  if (lowerUrl.includes("keka") || lowerSource.includes("keka")) {
    return { name: "Keka HR", color: "text-orange-400 bg-orange-400/10 border-orange-400/20" };
  }
  if (lowerUrl.includes("darwinbox") || lowerSource.includes("darwinbox")) {
    return { name: "Darwinbox", color: "text-violet-400 bg-violet-400/10 border-violet-400/20" };
  }
  return { name: source || "Direct ATS", color: "text-zinc-400 bg-white/[0.04] border-white/10" };
}

function getCorridorBadge(corridor?: string | null, location?: string | null) {
  if (corridor) {
    const c = corridor.toLowerCase();
    if (c.includes("omr") || c.includes("siruseri") || c.includes("taramani") || c.includes("tidel")) {
      return { name: "OMR Corridor", color: "text-amber-300 bg-amber-400/10 border-amber-400/30 font-semibold" };
    }
    if (c.includes("guindy") || c.includes("mepz") || c.includes("olympia") || c.includes("tambaram")) {
      return { name: "Guindy Hub", color: "text-emerald-300 bg-emerald-400/10 border-emerald-400/30 font-semibold" };
    }
    if (c.includes("dlf") || c.includes("porur") || c.includes("manapakkam")) {
      return { name: "DLF Porur", color: "text-cyan-300 bg-cyan-400/10 border-cyan-400/30 font-semibold" };
    }
    if (c.includes("coimbatore") && c.includes("tidel")) {
      return { name: "Coimbatore TIDEL", color: "text-teal-300 bg-teal-400/10 border-teal-400/30 font-semibold" };
    }
    if (c.includes("whitefield")) {
      return { name: "Whitefield", color: "text-purple-300 bg-purple-400/10 border-purple-400/30 font-semibold" };
    }
    if (c.includes("electronic city") || c.includes("e-city")) {
      return { name: "Electronic City", color: "text-purple-300 bg-purple-400/10 border-purple-400/30 font-semibold" };
    }
    if (c.includes("hitec") || c.includes("gachibowli") || c.includes("madhapur")) {
      return { name: "HITEC City", color: "text-blue-300 bg-blue-400/10 border-blue-400/30 font-semibold" };
    }
    if (c.includes("hosur")) {
      return { name: "Hosur Corridor", color: "text-orange-300 bg-orange-400/10 border-orange-400/30 font-semibold" };
    }
    if (c.includes("remote")) {
      return { name: "Remote", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20 font-semibold" };
    }
    return null;
  }
  
  if (location && location.toLowerCase().includes("remote")) {
    return { name: "Remote", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20 font-semibold" };
  }
  
  return null;
}

export function JobCard({
  id,
  title,
  company,
  location,
  source,
  matchScore,
  timeAgo,
  type = "Full-time",
  hideMatchScore = false,
  matchReasons = null,
  salaryMin,
  salaryMax,
  salaryCurrency,
  educationLevel,
  roleCategory,
  experienceLevel,
  corridor,
  city,
  postedAt,
  discoveredAt,
  onPrepareApplication,
  externalUrl,
}: JobCardProps) {
  const safeScore = matchScore || 0;
  const scoreColor = safeScore >= 90 ? "text-primary" : safeScore >= 75 ? "text-yellow-400" : "text-muted-foreground";
  const ringColor = safeScore >= 90 ? "stroke-primary" : safeScore >= 75 ? "stroke-yellow-500" : "stroke-zinc-500";
  const glowColor = safeScore >= 90 ? "shadow-[0_0_15px_rgba(200,245,66,0.15)]" : "";

  const salaryText = formatSalary(salaryMin, salaryMax, salaryCurrency);
  const roleInfo = roleCategory ? ROLE_LABELS[roleCategory] : null;
  const expInfo = experienceLevel ? EXP_LABELS[experienceLevel] : null;
  const sourceInfo = getSourceBadge(source, externalUrl);
  const corridorInfo = getCorridorBadge(corridor, location);

  // Clean location string removing noise for display
  const cleanLoc = location ? location.trim() : "Remote / Unspecified";

  return (
    <div
      id={id ? `job-card-${id}` : undefined}
      className={`group relative bg-card/45 backdrop-blur-md border border-white/[0.08] hover:border-[#c8f542]/45 hover:bg-card/75 rounded-[22px] p-5 sm:p-5.5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_12px_36px_rgba(0,0,0,0.5)] ${glowColor}`}
    >
      <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
        {/* Company Monogram & Core Content */}
        <div className="flex items-start gap-3.5 flex-1 min-w-0 pr-1">
          {/* Company Avatar Monogram */}
          <div className="hidden sm:flex shrink-0 w-11 h-11 rounded-2xl bg-gradient-to-br from-zinc-800 to-zinc-900 border border-white/10 items-center justify-center font-bold text-white text-xs tracking-wider shadow-md group-hover:border-[#c8f542]/40 group-hover:text-[#c8f542] group-hover:shadow-[0_0_12px_rgba(200,245,66,0.15)] transition-all mt-0.5">
            {company ? company.substring(0, 2).toUpperCase() : "JC"}
          </div>

          <div className="flex-1 min-w-0">
            {/* Top meta tags */}
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className={`px-2.5 py-0.5 text-[11px] font-mono tracking-wider border rounded-full font-medium ${sourceInfo.color}`}>
                {sourceInfo.name}
              </span>

              {/* Micro-Corridor / Hub Badge */}
              {corridorInfo && (
                <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 text-[10px] rounded-full border shadow-sm ${corridorInfo.color}`}>
                  {corridorInfo.name}
                </span>
              )}

              {/* Time Badge */}
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-mono rounded-full border shadow-sm ${
                  postedAt
                    ? "bg-[#c8f542]/10 text-[#c8f542] border-[#c8f542]/30 font-semibold"
                    : "bg-white/[0.04] text-zinc-400 border-white/10"
                }`}
                title={postedAt ? `Direct Employer Post: ${new Date(postedAt).toLocaleDateString()}` : `Discovered: ${timeAgo}`}
              >
                <Clock className={`w-3 h-3 ${postedAt ? "text-[#c8f542]" : "text-zinc-500"}`} />
                {timeAgo}
              </span>

              {/* Degree Tag */}
              {educationLevel && (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 text-[11px] font-medium rounded-full border bg-white/[0.06] text-zinc-300 border-white/10">
                  <GraduationCap className="w-3 h-3 text-[#c8f542]" />
                  {educationLevel}
                </span>
              )}

              {/* Role Tag */}
              {roleInfo && (
                <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded-full border ${roleInfo.color}`}>
                  {roleInfo.label}
                </span>
              )}

              {/* Experience Tag */}
              {expInfo && (
                <span className={`inline-flex items-center px-2 py-0.5 text-[10px] rounded-full border ${expInfo.color}`}>
                  {expInfo.label}
                </span>
              )}
            </div>

            {/* Job Title */}
            <h3 className="text-lg font-bold text-zinc-100 group-hover:text-[#c8f542] transition-colors leading-snug mb-1">
              {title}
            </h3>

            {/* Company & Location & Compensation */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted-foreground mb-3">
              <div className="flex items-center gap-1.5">
                <Building2 className="w-4 h-4 text-zinc-400" />
                <span className="font-semibold text-zinc-200">{company}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <MapPin className="w-4 h-4 text-[#c8f542]" />
                <span className="text-zinc-300">{cleanLoc}</span>
                {corridor && !["remote", "unspecified", "chennai central", "bengaluru tech hub", "hyderabad tech hub"].includes(corridor.toLowerCase()) && !cleanLoc.toLowerCase().includes(corridor.toLowerCase()) && (
                  <span className="text-xs text-muted-foreground">({corridor})</span>
                )}
              </div>
              {salaryText && (
                <div className="inline-flex items-center gap-1 text-[#c8f542] font-semibold bg-[#c8f542]/10 border border-[#c8f542]/20 px-2 py-0.5 rounded-md text-xs font-mono">
                  <Banknote className="w-3.5 h-3.5" />
                  <span>{salaryText}</span>
                </div>
              )}
            </div>

            {/* Badges / Pill attributes */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 text-xs font-medium bg-zinc-800/60 text-zinc-300 px-2.5 py-0.5 rounded-full border border-border">
                <Briefcase className="w-3 h-3" />
                {type}
              </span>

              {matchReasons &&
                matchReasons.map((reason, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center text-[10px] font-mono text-[#c8f542] bg-[#c8f542]/10 px-2 py-0.5 rounded-full border border-[#c8f542]/20 uppercase"
                  >
                    {reason.replace("_MATCH", "")}
                  </span>
                ))}
            </div>
          </div>
        </div>

        {/* Right Content: Match Score & Action Buttons */}
        <div className="flex flex-row sm:flex-col items-center sm:items-end justify-between w-full sm:w-auto shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-white/[0.06]">
          {!hideMatchScore && (
            <div className="relative w-12 h-12 flex items-center justify-center">
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
                <span className={`text-xs font-bold ${scoreColor}`}>{safeScore}</span>
                <span className="text-[7px] text-muted-foreground uppercase font-bold -mt-0.5">Match</span>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center gap-2 mt-3">
            {onPrepareApplication && (
              <Button
                size="sm"
                variant="outline"
                onClick={onPrepareApplication}
                className="h-8 text-xs border-white/10 hover:border-[#c8f542]/50 hover:bg-[#c8f542]/10 hover:text-[#c8f542]"
                title="Prepare Application Internally"
              >
                <FileText className="w-3.5 h-3.5 mr-1 text-[#c8f542]" />
                Prepare Application
              </Button>
            )}

            {externalUrl && (
              <a
                href={externalUrl}
                target="_blank"
                rel="noreferrer"
                id={id ? `apply-btn-${id}` : undefined}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-semibold bg-[#c8f542] hover:bg-[#d8ff4e] text-black shadow-md transition-all hover:scale-105"
                title="Open Direct ATS Career Board"
              >
                Apply Direct
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
