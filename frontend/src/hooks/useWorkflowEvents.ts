import { useEffect, useRef, useState } from 'react';
import { workflowApi, workflowEventsUrl } from '../lib/api';
import type { RunEvent } from '../types/workflow';

type ConnectionState = 'idle' | 'connecting' | 'live' | 'closed' | 'error';

export function useWorkflowEvents(runId: string | null, status: string | undefined, onTerminal: () => void) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>('idle');
  const onTerminalRef = useRef(onTerminal);

  useEffect(() => {
    onTerminalRef.current = onTerminal;
  }, [onTerminal]);

  useEffect(() => {
    if (!runId) {
      setEvents([]);
      setConnection('idle');
      return;
    }

    let active = true;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof window.setTimeout> | undefined;
    let reconnectAttempt = 0;
    let historyLoaded = false;
    let terminalSeen = false;
    setEvents([]);
    setConnection('connecting');

    const mergeEvents = (incoming: RunEvent[]) => {
      if (!active || !incoming.length) return;
      setEvents((current) => {
        const bySequence = new Map<number, RunEvent>();
        [...current, ...incoming].forEach((item) => bySequence.set(item.sequence, item));
        return [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
      });
    };

    const loadHistory = async () => {
      try {
        const history = await workflowApi.getEvents(runId);
        if (!active) return;
        mergeEvents(history.items);
        historyLoaded = true;
        // The initial history request can race with the run finishing.  Treat
        // a persisted terminal event as authoritative so we do not open a
        // socket that can only ever replay stale data (and so the parent gets
        // a chance to refresh the final run/draft immediately).
        const terminalEvent = history.items.find((item) =>
          ['run.completed', 'run.failed', 'run.cancelled'].includes(item.event_type),
        );
        if (terminalEvent) {
          terminalSeen = true;
          onTerminalRef.current();
        } else if (history.items.some((item) => ['run.paused', 'run.continued'].includes(item.event_type))) {
          onTerminalRef.current();
        }
      } catch {
        if (active) setConnection('error');
      }
    };

    const scheduleReconnect = () => {
      if (!active || terminalSeen || status === 'completed' || status === 'failed' || status === 'cancelled') return;
      if (reconnectTimer !== undefined) return;
      const delay = Math.min(1000 * (2 ** reconnectAttempt), 10000);
      reconnectAttempt += 1;
      setConnection('connecting');
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = undefined;
        void connect();
      }, delay);
    };

    const connect = async () => {
      if (!active) return;
      if (!historyLoaded) await loadHistory();

      if (!active) return;
      if (terminalSeen || status === 'completed' || status === 'failed' || status === 'cancelled') {
        setConnection('closed');
        return;
      }
      const nextSocket = new WebSocket(workflowEventsUrl(runId));
      socket = nextSocket;
      nextSocket.onopen = () => {
        if (!active || socket !== nextSocket) return;
        reconnectAttempt = 0;
        setConnection('live');
      };
      nextSocket.onmessage = (message) => {
        if (!active || socket !== nextSocket) return;
        let data: RunEvent | { type: string };
        try { data = JSON.parse(message.data) as RunEvent | { type: string }; } catch { return; }
        if (!('event_type' in data)) return;
        mergeEvents([data]);
        if (['run.completed', 'run.failed', 'run.cancelled'].includes(data.event_type)) {
          terminalSeen = true;
          onTerminalRef.current();
        } else if (['run.paused', 'run.continued'].includes(data.event_type)) {
          onTerminalRef.current();
        }
      };
      nextSocket.onerror = () => {
        if (active && socket === nextSocket) setConnection('error');
      };
      nextSocket.onclose = () => {
        if (!active || socket !== nextSocket) return;
        socket = null;
        setConnection('closed');
        scheduleReconnect();
      };
    };

    void connect();
    return () => {
      active = false;
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
      socket?.close();
      socket = null;
    };
  }, [runId, status]);

  return { events, connection };
}
