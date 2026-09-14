import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

export type TaskStatus = 
  | 'idle' 
  | 'QUEUED' 
  | 'RUNNING' 
  | 'RETRYING' 
  | 'SUCCEEDED' 
  | 'FAILED' 
  | 'ERROR'
  | 'COMPLETED'
  | 'CANCELLED';

export interface TaskState {
  status: TaskStatus;
  payload: any;
  error: string | null;
  isActive: boolean;
}

export function useTaskStream(taskId: string | null) {
  const [state, setState] = useState<TaskState>({
    status: 'idle',
    payload: null,
    error: null,
    isActive: false,
  });

  useEffect(() => {
    if (!taskId) {
      setState({
        status: 'idle',
        payload: null,
        error: null,
        isActive: false,
      });
      return;
    }

    setState(prev => ({ ...prev, isActive: true, error: null }));
    
    // Connect to the SSE endpoint discovered during audit
    const eventSource = new EventSource(`${api.baseUrl}/sse/tasks/${taskId}/events/stream`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        setState(prev => {
          const nextState = { ...prev, payload: data.payload || prev.payload };
          
          if (data.event_type) {
            nextState.status = data.event_type;
          }
          
          // Determine if we should close the stream based on terminal states
          const terminalStates = ['SUCCEEDED', 'FAILED', 'ERROR', 'CANCELLED', 'COMPLETED'];
          if (terminalStates.includes(nextState.status) || data.status === 'DONE') {
            nextState.isActive = false;
            eventSource.close();
          }
          
          return nextState;
        });
      } catch (err) {
        console.error("Failed to parse SSE event", err);
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE connection error", error);
      // Let EventSource auto-reconnect, but flag if we need to.
      // If we want to strictly close on error:
      // eventSource.close();
      // setState(prev => ({ ...prev, error: "Connection lost", isActive: false }));
    };

    return () => {
      eventSource.close();
      setState(prev => ({ ...prev, isActive: false }));
    };
  }, [taskId]);

  return state;
}
