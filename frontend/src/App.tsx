import React, { useState, useRef, useEffect } from "react";
import { 
  MessageCircle, 
  Trash2, 
  History, 
  Menu, 
  X, 
  LifeBuoy, 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  HelpCircle,
  Copy,
  Volume2
} from "lucide-react";
import { PromptInputBox } from "@/components/ui/PromptInputBox";
import { useChat } from "@/hooks/useChat";
import { useVoice } from "@/hooks/useVoice";
import { cn } from "@/lib/utils";

const App: React.FC = () => {
  const { messages, history, isLoading, sendMessage, sendVoice, clearHistory } = useChat();
  const { isRecording, startRecording, stopRecording } = useVoice();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (text: string) => {
    if (text.trim()) {
      await sendMessage(text);
    }
  };

  const handleVoiceSend = async () => {
    const audioBlob = await stopRecording();
    if (audioBlob) {
      await sendVoice(audioBlob);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const getRiskIcon = (level: string) => {
    switch (level) {
      case "safe": return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case "caution": return <AlertTriangle className="w-4 h-4 text-yellow-500" />;
      case "banned": return <XCircle className="w-4 h-4 text-red-500" />;
      default: return <HelpCircle className="w-4 h-4 text-purple-500" />;
    }
  };

  const getRiskBadgeClass = (level: string) => {
    switch (level) {
      case "safe": return "bg-green-500/10 text-green-500 border-green-500/20";
      case "caution": return "bg-yellow-500/10 text-yellow-500 border-yellow-500/20";
      case "banned": return "bg-red-500/10 text-red-500 border-red-500/20";
      default: return "bg-purple-500/10 text-purple-500 border-purple-500/20";
    }
  };

  const playResponseAudio = (audioHex: string) => {
    if (!audioHex) return;
    const bytes = new Uint8Array(audioHex.length / 2);
    for (let i = 0; i < audioHex.length; i += 2) {
      bytes[i / 2] = parseInt(audioHex.substr(i, 2), 16);
    }
    const blob = new Blob([bytes], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.play();
  };

  return (
    <div className="flex h-screen bg-[#0D0D0D] text-gray-200 overflow-hidden font-sans">
      {/* Sidebar */}
      <aside 
        className={cn(
          "fixed md:relative z-50 flex flex-col bg-[#000000] border-r border-[#262626] transition-all duration-300",
          sidebarOpen ? "w-[260px]" : "w-0 -ml-1 overflow-hidden"
        )}
      >
        <div className="flex flex-col h-full p-3">
          <button 
            className="flex items-center gap-2 w-full p-3 mb-2 rounded-lg hover:bg-[#262626] border border-[#262626] transition-colors"
            onClick={() => window.location.reload()}
          >
            <MessageCircle className="w-5 h-5 text-gray-400" />
            <span className="text-sm font-medium">New Chat</span>
          </button>

          <div className="flex-1 overflow-y-auto space-y-1 py-4">
            <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest px-3 mb-2">History</div>
            {history.map((item) => (
              <div 
                key={item.id} 
                className="group flex items-center justify-between p-3 rounded-lg hover:bg-[#262626] cursor-pointer transition-colors"
                onClick={() => handleSend(item.user_query)}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  <History className="w-4 h-4 text-gray-500 flex-shrink-0" />
                  <span className="text-xs truncate text-gray-400">{item.user_query}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-auto pt-4 border-t border-[#262626]">
            <button 
               onClick={clearHistory}
               className="flex items-center gap-3 w-full p-3 rounded-lg hover:bg-[#262626] text-red-400/80 hover:text-red-400 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              <span className="text-xs font-medium">Clear history</span>
            </button>
            <div className="flex items-center gap-3 w-full p-3 mt-1 rounded-lg text-gray-500 italic">
               <LifeBuoy className="w-4 h-4" />
               <span className="text-[10px]">NADA Aligned Assistant</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col relative overflow-hidden h-full">
        {/* Header */}
        <header className="flex items-center justify-between p-4 border-b border-[#262626] glass-effect">
          <div className="flex items-center gap-3">
             <div>
               <h1 className="text-sm font-bold bg-gradient-to-r from-orange-400 via-white to-green-400 bg-clip-text text-transparent">Clean Sport सहायक</h1>
               <p className="text-[10px] text-gray-500 tracking-wider">Anti-Doping Assistant for Rural Indian Athletes</p>
             </div>
          </div>
          <div className="hidden md:flex items-center gap-2 px-3 py-1 bg-[#1A1A1A] rounded-full border border-[#262626]">
             <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
             <span className="text-[10px] font-medium text-gray-400 uppercase tracking-tighter">Live Support</span>
          </div>
        </header>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto px-4 md:px-0 py-8 space-y-8 no-scrollbar">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full opacity-30 select-none pointer-events-none">
               <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mb-4 border border-white/10">
                  <MessageCircle className="w-8 h-8 text-white" />
               </div>
               <h2 className="text-xl font-bold text-white mb-2 tracking-tighter">Namaste, Khiladi!</h2>
               <p className="text-xs text-gray-400">Poochiye koi bhi sawaal doping aur supplements ke baare mein.</p>
            </div>
          ) : (
            <div className="max-w-2xl mx-auto space-y-12 pb-24">
              {messages.map((msg) => (
                <div key={msg.id} className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                  {/* User Question */}
                  <div className="flex flex-col items-end gap-2">
                    <div className="bg-[#1A1A1A] border border-[#333333] px-5 py-3 rounded-2xl rounded-tr-sm max-w-[85%] shadow-2xl">
                      <p className="text-sm text-gray-100 leading-relaxed font-medium tracking-tight whitespace-pre-wrap">{msg.user_query}</p>
                    </div>
                  </div>

                  {/* AI Response */}
                  <div className="flex flex-col items-start gap-4">
                    <div className="flex items-center gap-3 px-2">
                       <div className={cn("flex items-center gap-1.5 px-3 py-1 rounded-full border text-[10px] font-bold uppercase", getRiskBadgeClass(msg.risk_level))}>
                         {getRiskIcon(msg.risk_level)}
                         {msg.risk_level}
                       </div>
                       <span className="text-[10px] text-gray-600 font-mono tracking-tighter">{new Date(msg.timestamp).toLocaleTimeString()}</span>
                    </div>
                    
                    <div className="group relative w-full">
                       <div className="absolute -inset-0.5 bg-gradient-to-r from-gray-800 to-transparent rounded-3xl opacity-20 blur-sm -z-10" />
                       <div className="bg-[#000000] border border-[#262626] px-6 py-5 rounded-3xl rounded-tl-sm shadow-2xl w-full">
                          <p className="text-sm text-gray-300 leading-8 font-normal tracking-wide whitespace-pre-wrap selection:bg-orange-500/30">
                            {msg.ai_response}
                          </p>
                          <div className="flex items-center gap-4 mt-8 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                             <button 
                               onClick={() => copyToClipboard(msg.ai_response)}
                               className="p-2 rounded-lg bg-[#1A1A1A] hover:bg-[#262626] border border-[#262626] text-gray-500 hover:text-white transition-all transform hover:scale-105"
                             >
                               <Copy className="w-3.5 h-3.5" />
                             </button>
                             <button 
                               onClick={() => (msg as any).audio_hex && playResponseAudio((msg as any).audio_hex)}
                               className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1A1A1A] hover:bg-[#262626] border border-[#262626] text-gray-500 hover:text-white transition-all transform hover:scale-105"
                             >
                                <Volume2 className="w-3.5 h-3.5" />
                                <span className="text-[10px] font-bold tracking-tighter uppercase">Listen</span>
                             </button>
                          </div>
                       </div>
                    </div>
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="w-full absolute bottom-0 left-0 bg-gradient-to-t from-[#0D0D0D] via-[#0D0D0D]/90 to-transparent pt-32 pb-4 px-4 md:px-0">
           <div className="max-w-2xl mx-auto relative px-2 md:px-0">
             {isLoading && (
               <div className="absolute -top-12 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-[#1A1A1A] border border-[#333333] px-4 py-2 rounded-full shadow-2xl animate-pulse">
                  <div className="w-2 h-2 bg-orange-500 rounded-full animate-bounce" />
                  <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest">Thinking</span>
               </div>
             )}
             <PromptInputBox 
               onSend={handleSend} 
               isLoading={isLoading} 
               isRecording={isRecording}
               onStartRecording={startRecording}
               onStopRecording={handleVoiceSend}
               placeholder="Poochiye koi bhi sawaal..."
             />
             <p className="mt-4 text-center text-[9px] text-gray-600 font-medium tracking-tighter uppercase">
               Expert advice confirmed with NADA & WADA guidelines · Be Safe Khiladi
             </p>
           </div>
        </div>
      </main>

      <style>{`
        .glass-effect {
          background: rgba(13, 13, 13, 0.8);
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
        }
        .no-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .no-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
        @keyframes fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes slide-in {
           from { transform: translateY(10px); opacity: 0; }
           to { transform: translateY(0); opacity: 1; }
        }
        .animate-fade-in { animation: fade-in 0.5s ease-out; }
        .animate-slide-in { animation: slide-in 0.4s ease-out; }
      `}</style>
    </div>
  );
};

export default App;
