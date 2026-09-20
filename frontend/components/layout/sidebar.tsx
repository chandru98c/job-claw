"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Compass, Database, Activity, Bot, ChevronDown, ChevronUp } from "lucide-react";
import { useTaskStatus } from "@/hooks/useTaskStatus";

function workerLabel(status: string, activeTasks: number) {
  if (status === "busy") return `Busy (${activeTasks})`;
  if (status === "idle") return "Idle";
  if (status === "offline") return "Offline";
  return "Unknown";
}

function statusDotClass(status: string) {
  if (status === "busy") return "bg-amber-500 animate-pulse";
  if (status === "idle") return "bg-primary";
  if (status === "offline") return "bg-destructive";
  return "bg-zinc-500";
}

export function Sidebar() {
  const pathname = usePathname();
  const status = useTaskStatus();
  const [isStatusExpanded, setIsStatusExpanded] = useState(false);

  const links = [
    { href: "/", label: "Discover", icon: Compass },
    { href: "/saved-searches", label: "Saved Searches", icon: Database },
    { href: "/recommendations", label: "Recommendations", icon: Activity },
    { href: "/sources", label: "Source Registry", icon: Database },
    { href: "/engines", label: "Pipeline & Engines", icon: Activity },
    { href: "/agent", label: "Auto-Apply Agent", icon: Bot },
  ];

  return (
    <div className="w-56 border-r border-white/[0.05] bg-card/40 backdrop-blur-sm hidden md:flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex-1 py-4 px-3 space-y-1 min-h-0 overflow-y-auto">
        {links.map((link) => {
          const isActive = pathname === link.href;
          const Icon = link.icon;

          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-full text-sm font-medium transition-colors ${
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-card/50"
              }`}
            >
              <Icon className={`w-5 h-5 shrink-0 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
              <span className="truncate">{link.label}</span>
            </Link>
          );
        })}
      </div>

      <div className="p-3 border-t border-white/[0.05] shrink-0">
        <div className="bg-card/30 border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => setIsStatusExpanded((v) => !v)}
            className="w-full p-2.5 flex items-start justify-between gap-3 hover:bg-card/50 transition-colors text-left"
            aria-expanded={isStatusExpanded}
          >
            <div className="min-w-0">
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">System Status</div>
              <div className="text-sm text-foreground leading-5 truncate">Core: {status.core_online ? "Online" : "Offline"}</div>
              <div className="text-sm text-muted-foreground leading-5 truncate">Worker: {workerLabel(status.worker_status, status.active_tasks)}</div>
            </div>
            {isStatusExpanded ? (
              <ChevronUp className="w-4 h-4 text-muted-foreground mt-1 shrink-0" />
            ) : (
              <ChevronDown className="w-4 h-4 text-muted-foreground mt-1 shrink-0" />
            )}
          </button>

          {isStatusExpanded && (
            <div className="px-3 pb-3 pt-2 border-t border-border space-y-3 bg-black/20">
              <StatusRow label="Core" value={status.core_online ? "Online" : "Offline"} dotClass={status.core_online ? "bg-primary" : "bg-destructive"} />

              <div>
                <StatusRow
                  label="Worker"
                  value={workerLabel(status.worker_status, status.active_tasks)}
                  dotClass={statusDotClass(status.worker_status)}
                />
                <div className="text-xs text-muted-foreground mt-1 pl-3">Active tasks: {status.active_tasks ?? 0}</div>
                <div className="text-xs text-muted-foreground mt-0.5 pl-3">Workers online: {status.workers_online ?? 0}</div>
              </div>

              <StatusRow
                label="Redis"
                value={status.redis_connected ? "Connected" : "Disconnected"}
                dotClass={status.redis_connected ? "bg-primary" : "bg-destructive"}
              />

              <StatusRow
                label="Database"
                value={status.db_connected ? "Connected" : "Disconnected"}
                dotClass={status.db_connected ? "bg-primary" : "bg-destructive"}
              />

              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">Discovery</div>
                <div className="text-sm text-muted-foreground break-words">
                  {status.total_engines ?? 0} engines ({status.active_engines ?? 0} active / {status.inactive_engines ?? 0} inactive)
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  Running: {status.discovery_running_tasks ?? 0} · Queued: {status.discovery_queued_tasks ?? 0}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusRow({ label, value, dotClass }: { label: string; value: string; dotClass: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground mb-1">{label}</div>
      <div className="text-sm text-foreground flex items-center gap-2 min-w-0">
        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`} />
        <span className="truncate">{value}</span>
      </div>
    </div>
  );
}
