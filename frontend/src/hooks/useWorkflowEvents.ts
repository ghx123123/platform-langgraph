import { useEffect, useState } from 'react';
import { workflowApi, workflowEventsUrl } from '../lib/api';
import type { RunEvent } from '../types/workflow';

type ConnectionState = 'idle' | 'connecting' | 'live' | 'closed' | 'error';

export function useWorkflowEvents(runId: string | null, status: string | undefined, onTerminal: () => void) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>('idle');

  useEffect(() => {
    if (!runId) {
      setEvents([]);
      setConnection('idle');
      return;
    }

    let active = true;
    let socket: WebSocket | null = null;
    setEvents([]);
    setConnection('connecting');

    const connect = async () => {
      try {
        const history = await workflowApi.getEvents(runId);
        if (!active) return;
        setEvents(history.items);
      } catch {
        if (active) setConnection('error');
      }

      if (!active) return;
      socket = new WebSocket(workflowEventsUrl(runId));
      socket.onopen = () => active && setConnection('live');
      socket.onmessage = (message) => {
        const data = JSON.parse(message.data) as RunEvent | { type: string };
        if (!('event_type' in data) || !active) return;
        setEvents((current) => {
          if (current.some((item) => item.sequence === data.sequence)) return current;
          return [...current, data].sort((a, b) => a.sequence - b.sequence);
        });
        // paused/continued 会改变会话记录（暂停待办、轮次上限），也需拉取最新 run
        if (['run.completed', 'run.failed', 'run.cancelled', 'run.paused', 'run.continued'].includes(data.event_type)) onTerminal();
      };
      socket.onerror = () => active && setConnection('error');
      socket.onclose = () => active && setConnection('closed');
    };

    void connect();
    return () => {
      active = false;
      socket?.close();
    };
  }, [runId, status, onTerminal]);

  return { events, connection };
}
