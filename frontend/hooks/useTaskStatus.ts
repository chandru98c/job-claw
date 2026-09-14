import { useState, useEffect } from "react";
import { useAppState } from "@/components/providers";

export interface SystemStatus {
  core_online: boolean;
  worker_status: "idle" | "busy";
  active_tasks: number;
}

export function useTaskStatus() {
  const { apiMode } = useAppState();
  const [status, setStatus] = useState<SystemStatus>({
    core_online: false,
    worker_status: "idle",
    active_tasks: 0,
  });

  useEffect(() => {
    let isMounted = true;
    
    const fetchStatus = async () => {
      try {
        const baseUrl = "http://127.0.0.1:8000";
        const res = await fetch(`${baseUrl}/system/status`);
        if (!res.ok) throw new Error("Failed to fetch status");
        
        const data = await res.json();
        if (isMounted) {
          setStatus(data);
        }
      } catch (err) {
        if (isMounted) {
          setStatus({
            core_online: false,
            worker_status: "idle",
            active_tasks: 0,
          });
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
