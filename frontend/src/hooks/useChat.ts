import { useState, useCallback, useEffect } from 'react';

export interface Message {
  id: number;
  user_query: string;
  ai_response: string;
  language: string;
  risk_level: 'safe' | 'caution' | 'banned' | 'unknown';
  timestamp: string;
}

export const useChat = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [history, setHistory] = useState<Message[]>([]);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch('/history');
      const data = await res.json();
      setHistory(data.history || []);
    } catch (err) {
      console.error("Failed to fetch history:", err);
    }
  }, []);

  const sendMessage = useCallback(async (query: string) => {
    if (!query.trim()) return;

    setIsLoading(true);
    // Optimistically add user query (temp message)
    const tempId = Date.now();
    
    try {
      const res = await fetch('/verify-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });
      
      const data = await res.json();
      
      const newMessage: Message = {
        id: tempId,
        user_query: data.user_query,
        ai_response: data.ai_response,
        language: data.language,
        risk_level: data.risk_level,
        timestamp: new Date().toISOString(),
      };
      
      setMessages(prev => [...prev, newMessage]);
      fetchHistory(); // Refresh sidebar history
      return data;
    } catch (err) {
      console.error("Send message error:", err);
    } finally {
      setIsLoading(false);
    }
  }, [fetchHistory]);

  const sendVoice = useCallback(async (audioBlob: Blob) => {
    setIsLoading(true);
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');

    try {
      const res = await fetch('/verify', {
        method: 'POST',
        body: formData,
      });
      
      const data = await res.json();
      
      const newMessage: Message = {
        id: Date.now(),
        user_query: data.user_query,
        ai_response: data.ai_response,
        language: data.language,
        risk_level: data.risk_level,
        timestamp: new Date().toISOString(),
      };
      
      setMessages(prev => [...prev, newMessage]);
      fetchHistory();
      return data;
    } catch (err) {
      console.error("Voice message error:", err);
    } finally {
      setIsLoading(false);
    }
  }, [fetchHistory]);

  const clearHistory = useCallback(async () => {
    try {
      await fetch('/history', { method: 'DELETE' });
      setHistory([]);
      setMessages([]);
    } catch (err) {
      console.error("Clear history error:", err);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  return { messages, history, isLoading, sendMessage, sendVoice, fetchHistory, clearHistory };
};
