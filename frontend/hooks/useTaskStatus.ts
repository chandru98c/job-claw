import { useState, useEffect } from "react";
import { useAppState } from "@/components/providers";
import { api } from "@/lib/api";

export interface SystemStatus {
  core_online: boolean;
  worker_status: "idle" | "busy" | "offline" | "unknown";
  active_tasks: number;
  redis_connected?: boolean;
  db_connected?: boolean;
  total_engines?: number;
  workers_online?: number;
  discovery_running_tasks?: number;
  active_engines?: number;
  inactive_engines?: number;
  discovery_queued_tasks?: number;
}

const FALLBACK_STATUS: SystemStatus = {
  core_online: false,
  worker_status: "unknown",
  active_tasks: 0,
  redis_connected: false,
  db_connected: false,
  total_engines: 0,
  workers_online: 0,
  discovery_running_tasks: 0,
};

export function useTaskStatus() {
  const { apiMode } = useAppState();
  const [status, setStatus] = useState<SystemStatus>(FALLBACK_STATUS);

  useEffect(() => {
    let isMounted = true;

    const fetchStatus = async () => {
      try {
        const data = await api.get<SystemStatus>("/system/status");
        if (isMounted) {
          setStatus(data);
        }
      } catch {
        if (isMounted) {
          setStatus(FALLBACK_STATUS);
        }
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [apiMode]);

  return status;
}
