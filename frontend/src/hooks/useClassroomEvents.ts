import { useEffect, useRef, useState } from "react";
import { classroomApi, classroomEventsUrl } from "../lib/api";
import type { ClassroomEvent } from "../types/workflow";

export type ClassroomConnection =
  "idle" | "connecting" | "live" | "closed" | "error";

/** History-first classroom stream with sequence/event de-duplication and reconnect.
 *
 * `stream` controls whether live WebSocket reconnection is enabled. Set it to
 * false for completed/stopped rounds: they will load the persisted snapshot once
 * and never enter the retry loop, preventing runaway snapshot loads.
 */
export function useClassroomEvents(
  runId: string | null,
  roundId: string | null,
  stream = true,
) {
  const [events, setEvents] = useState<ClassroomEvent[]>([]);
  const [connection, setConnection] = useState<ClassroomConnection>("idle");
  const [lastSequence, setLastSequence] = useState(0);
  const [announcedRoundId, setAnnouncedRoundId] = useState<string | null>(null);
  const retryRef = useRef<number | undefined>();

  useEffect(() => {
    if (!runId || !roundId) {
      setEvents([]);
      setLastSequence(0);
      setAnnouncedRoundId(null);
      setConnection("idle");
      return;
    }
    let active = true;
    let socket: WebSocket | null = null;
    let retry = 0;

    const merge = (items: ClassroomEvent[]) => {
      if (!active) return;
      const nextRound = items.find(
        (item) =>
          item.run_id === runId &&
          item.round_id !== roundId &&
          item.event_type === "classroom.round.started",
      );
      if (nextRound) setAnnouncedRoundId(nextRound.round_id);
      const relevant = items.filter(
        (item) =>
          item.run_id === runId &&
          item.round_id === roundId &&
          Number.isFinite(item.sequence),
      );
      if (!relevant.length) return;
      setEvents((current) => {
        // Server sequence is the authoritative ordering/recovery cursor.
        // event_id remains an identity guard for malformed/replayed payloads.
        const bySequence = new Map(
          current.map((item) => [item.sequence, item]),
        );
        let changed = false;
        relevant.forEach((item) => {
          const existing = bySequence.get(item.sequence);
          if (!existing) {
            bySequence.set(item.sequence, item);
            changed = true;
          } else if (
            existing.event_id === item.event_id &&
            JSON.stringify(existing) !== JSON.stringify(item)
          ) {
            bySequence.set(item.sequence, item);
            changed = true;
          }
        });
        return changed
          ? [...bySequence.values()].sort((a, b) => a.sequence - b.sequence)
          : current;
      });
      setLastSequence((current) =>
        Math.max(current, ...relevant.map((item) => item.sequence)),
      );
    };

    const load = async () => {
      setConnection("connecting");
      try {
        const snapshot = await classroomApi.getSnapshot(runId, roundId);
        if (!active) return;
        merge(snapshot.events || []);
        setLastSequence(snapshot.last_sequence || 0);

        // Completed/stopped rounds do not stream: avoid the reconnect->snapshot loop.
        if (!stream) {
          setConnection("closed");
          return;
        }

        const ws = new WebSocket(classroomEventsUrl(runId));
        socket = ws;
        ws.onopen = () => {
          if (active && socket === ws) {
            retry = 0;
            setConnection("live");
          }
        };
        ws.onmessage = (message) => {
          if (!active || socket !== ws) return;
          try {
            const data = JSON.parse(message.data) as {
              type?: string;
              classroom_event?: ClassroomEvent;
            };
            if (data.classroom_event) merge([data.classroom_event]);
          } catch {
            /* ignore malformed trace */
          }
        };
        ws.onerror = () => {
          if (active && socket === ws) setConnection("error");
        };
        ws.onclose = () => {
          if (!active || socket !== ws) return;
          socket = null;
          setConnection("closed");
          const delay = Math.min(1000 * 2 ** retry++, 10000);
          retryRef.current = window.setTimeout(() => void load(), delay);
        };
      } catch {
        if (active) setConnection("error");
      }
    };
    void load();
    return () => {
      active = false;
      if (retryRef.current) window.clearTimeout(retryRef.current);
      socket?.close();
      socket = null;
    };
  }, [runId, roundId, stream]);
  return { events, connection, lastSequence, announcedRoundId };
}
