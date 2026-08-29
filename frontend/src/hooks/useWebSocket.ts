import { useEffect, useRef, useCallback, useState } from 'react';
import { useMessageStore } from '../stores/messageStore';
import type { WSMessage } from '../types';

const WS_URL = `ws://${window.location.host}`;

export function useWebSocket(agentId: string | null) {
  const socketRef = useRef<WebSocket | null>(null);
  const { addMessage } = useMessageStore();
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(() => {
    if (!agentId) return;

    // Close existing connection
    if (socketRef.current) {
      socketRef.current.close();
    }

    const ws = new WebSocket(`${WS_URL}/ws/${agentId}`);
    socketRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected as', agentId);
      setIsConnected(true);
    };

    ws.onclose = () => {
      console.log('[WS] Disconnected');
      setIsConnected(false);
    };

    ws.onerror = (error) => {
      console.error('[WS] Error:', error);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[WS] Message received:', data);
        if (data.msg_type) {
          addMessage(data);
        }
      } catch (e) {
        console.error('[WS] Failed to parse message:', e);
      }
    };

    return () => {
      ws.close();
    };
  }, [agentId, addMessage]);

  useEffect(() => {
    const cleanup = connect();
    return () => {
      cleanup?.();
    };
  }, [connect]);

  const sendMessage = useCallback((msg: Omit<WSMessage, 'type'>) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      console.error('[WS] Not connected');
      return;
    }

    socketRef.current.send(JSON.stringify({
      type: 'message',
      ...msg,
    }));
  }, []);

  const ping = useCallback(() => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;

    socketRef.current.send(JSON.stringify({
      type: 'ping',
    }));
  }, []);

  return {
    sendMessage,
    ping,
    isConnected,
  };
}
