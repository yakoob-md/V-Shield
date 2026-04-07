import React, { useState, useRef, useEffect } from "react";
import { 
  MessageCircle, 
  Trash2, 
  History, 
  Menu, 
  LifeBuoy, 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  HelpCircle,
  Copy,
  Volume2,
  Plus
} from "lucide-react";
import { PromptInputBox } from "@/components/ui/PromptInputBox";
import { EtheralShadow } from "@/components/ui/etheral-shadow";
import { useChat } from "@/hooks/useChat";
import { useVoice } from "@/hooks/useVoice";
import { cn } from "@/lib/utils";

const App: React.FC = () => {
  const { 
    currentChatId, 
    chatSessions, 
    messages, 
    isLoading, 
    createChat, 
    loadChat, 
    sendMessage, 
    sendVoice, 
    deleteChat 
  } = useChat();
  
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
      case "safe": return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "caution": return "bg-amber-50 text-amber-700 border-amber-200";
      case "banned": return "bg-rose-50 text-rose-700 border-rose-200";
      default: return "bg-slate-50 text-slate-700 border-slate-200";
    }
  };


  return (
    <div className="flex h-screen bg-[#FFFFFF] text-slate-900 overflow-hidden font-sans relative">
      {/* Background Animation */}
      <EtheralShadow
        color="rgba(128, 128, 128, 0.1)"
        animation={{ scale: 100, speed: 90 }}
        noise={{ opacity: 0.5, scale: 1.2 }}
        sizing="fill"
        className="opacity-60"
      />

      {/* Sidebar */}
      <aside 
        className={cn(
          "fixed md:relative z-50 flex flex-col bg-slate-50/80 backdrop-blur-xl border-r border-slate-200 transition-all duration-300",
          sidebarOpen ? "w-[280px]" : "w-0 -ml-1 overflow-hidden"
        )}
      >
        <div className="flex flex-col h-full p-4">
          <button 
            className="flex items-center gap-3 w-full p-3 mb-6 rounded-xl bg-slate-200/50 hover:bg-slate-200 border border-slate-200 transition-all group shadow-sm"
            onClick={() => createChat()}
          >
            <Plus className="w-5 h-5 text-slate-500 group-hover:text-sky-700 transition-colors" />
            <span className="text-sm font-semibold text-slate-600 group-hover:text-sky-800">New Chat</span>
          </button>

          <div className="flex-1 overflow-y-auto space-y-1 pr-2 custom-scrollbar">
            <div className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] px-3 mb-4">Chat History</div>
            {chatSessions.map((session) => (
              <div 
                key={session.id} 
                className={cn(
                  "group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all border",
                  currentChatId === session.id 
                    ? "bg-sky-100/50 border-sky-200 shadow-sm" 
                    : "bg-transparent border-transparent hover:bg-slate-100"
                )}
                onClick={() => loadChat(session.id)}
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <MessageCircle className={cn("w-4 h-4 flex-shrink-0", currentChatId === session.id ? "text-sky-600" : "text-slate-400")} />
                  <span className={cn("text-xs truncate font-medium", currentChatId === session.id ? "text-sky-900" : "text-slate-500 group-hover:text-slate-700")}>
                    {session.title}
                  </span>
                </div>
                <button 
                  onClick={(e) => { e.stopPropagation(); deleteChat(session.id); }}
                  className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-500/20 rounded-lg text-gray-500 hover:text-red-400 transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>

          <div className="mt-auto pt-6 border-t border-slate-200">
            <div className="flex items-center gap-3 w-full p-4 rounded-2xl bg-slate-100/50 border border-slate-200">
               <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-sky-600 to-indigo-600 flex items-center justify-center p-[1px]">
                 <div className="w-full h-full rounded-full bg-white flex items-center justify-center">
                    <LifeBuoy className="w-4 h-4 text-sky-700/70" />
                 </div>
               </div>
               <div className="flex flex-col">
                 <span className="text-[10px] font-bold text-slate-800 uppercase tracking-wider">Athlete Shield</span>
                 <span className="text-[9px] text-slate-500">NADA Aligned v2.0</span>
               </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col relative overflow-hidden h-full z-10">
        {/* Header */}
        <header className="flex items-center justify-between p-5 border-b border-slate-200 bg-white/40 backdrop-blur-md">
          <div className="flex items-center gap-4">
             <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-colors md:hidden">
               <Menu className="w-5 h-5" />
             </button>
             <div>
               <h1 className="text-base font-black tracking-tighter bg-gradient-to-r from-sky-700 via-indigo-800 to-sky-900 bg-clip-text text-transparent uppercase">Clean Sport सहायक</h1>
               <div className="flex items-center gap-2 mt-0.5">
                  <div className="w-1.5 h-1.5 bg-sky-600 rounded-full animate-pulse shadow-[0_0_8px_rgba(2,132,199,0.3)]" />
                  <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Active Protection Layer</span>
               </div>
             </div>
          </div>
          <div className="flex items-center gap-4">
             <div className="hidden lg:flex flex-col items-end mr-4">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">Current Session</span>
                <span className="text-[11px] text-slate-700 font-medium truncate max-w-[200px]">
                  {chatSessions.find(s => s.id === currentChatId)?.title || "Select or start a chat"}
                </span>
             </div>
             <button className="p-2.5 rounded-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-400 hover:text-slate-600 transition-all shadow-sm">
                <History className="w-4 h-4" />
             </button>
          </div>
        </header>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto px-4 md:px-0 py-10 space-y-12 no-scrollbar scroll-smooth">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full opacity-60 select-none pointer-events-none animate-in fade-in duration-1000">
               <div className="w-24 h-24 bg-sky-50 rounded-[2rem] flex items-center justify-center mb-6 border border-sky-100 shadow-xl rotate-12 transition-transform hover:rotate-0">
                  <MessageCircle className="w-10 h-10 text-sky-600" />
               </div>
               <h2 className="text-3xl font-black text-slate-800 mb-3 tracking-tighter uppercase">Athlete Assistant</h2>
               <p className="text-xs text-slate-500 max-w-sm text-center leading-relaxed font-medium">
                 Poochiye koi bhi sawaal doping, supplements, ya medications ke baare mein. 
                 <span className="block mt-2 text-[10px] text-sky-700/80 uppercase font-black tracking-widest">WADA & NADA Verified Guidance.</span>
               </p>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-16 pb-32">
              {messages.map((msg, idx) => (
                <div key={msg.id || idx} className="animate-in fade-in slide-in-from-bottom-4 duration-700">
                  {msg.role === 'user' ? (
                    /* User Question */
                    <div className="flex flex-col items-end gap-3 translate-x-2">
                      <div className="bg-sky-50 border border-sky-100 px-6 py-4 rounded-[1.5rem] rounded-tr-[0.2rem] max-w-[85%] shadow-md">
                        <p className="text-sm text-slate-800 leading-relaxed font-medium tracking-tight whitespace-pre-wrap">{msg.content}</p>
                      </div>
                      <span className="text-[9px] text-slate-400 font-bold uppercase tracking-widest mr-2">You</span>
                    </div>
                  ) : (
                    /* AI Response */
                    <div className="flex flex-col items-start gap-5 -translate-x-2">
                      <div className="flex items-center gap-3 px-3">
                         <div className={cn("flex items-center gap-2 px-4 py-1.5 rounded-full border text-[10px] font-black uppercase tracking-tighter shadow-sm", getRiskBadgeClass(msg.risk_level))}>
                           {getRiskIcon(msg.risk_level)}
                           {msg.risk_level}
                         </div>
                         <span className="text-[10px] text-gray-700 font-mono font-bold">{new Date(msg.timestamp).toLocaleTimeString()}</span>
                      </div>
                      
                      <div className="group relative w-full">
                         <div className="absolute -inset-1 bg-gradient-to-r from-sky-600/10 via-transparent to-indigo-600/10 rounded-[2rem] opacity-0 group-hover:opacity-100 blur-md transition-opacity duration-500 -z-10" />
                         <div className="bg-white border border-slate-100 px-8 py-7 rounded-[2rem] rounded-tl-[0.2rem] shadow-lg w-full">
                            <p className="text-[15px] text-slate-800 leading-9 font-normal tracking-wide whitespace-pre-wrap selection:bg-sky-100">
                               {msg.content}
                            </p>
                            <div className="flex items-center gap-4 mt-10 opacity-0 group-hover:opacity-100 transition-all duration-300 transform translate-y-2 group-hover:translate-y-0">
                               <button 
                                 onClick={() => copyToClipboard(msg.content)}
                                 className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-50 hover:bg-slate-100 border border-slate-100 text-slate-500 hover:text-sky-700 transition-all transform active:scale-95 shadow-sm"
                               >
                                 <Copy className="w-3.5 h-3.5" />
                                 <span className="text-[10px] font-bold uppercase">Copy</span>
                               </button>
                               <button 
                                 className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-50 hover:bg-slate-100 border border-slate-100 text-slate-500 hover:text-sky-700 transition-all transform active:scale-95 shadow-sm"
                               >
                                  <Volume2 className="w-3.5 h-3.5" />
                                  <span className="text-[10px] font-bold uppercase">Play</span>
                               </button>
                            </div>
                         </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="w-full absolute bottom-0 left-0 bg-gradient-to-t from-white via-white/95 to-transparent pt-32 pb-6 px-4 md:px-0">
           <div className="max-w-3xl mx-auto relative px-2 md:px-0">
             {isLoading && (
               <div className="absolute -top-14 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-white/80 backdrop-blur-xl border border-slate-200/60 shadow-xl px-6 py-2.5 rounded-2xl animate-in fade-in slide-in-from-bottom-2 duration-300">
                  <div className="flex gap-1.5">
                    <div className="w-1.5 h-1.5 bg-sky-600 rounded-full animate-bounce [animation-delay:-0.3s]" />
                    <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                    <div className="w-1.5 h-1.5 bg-indigo-600 rounded-full animate-bounce" />
                  </div>
                  <span className="text-[10px] font-black text-slate-600 uppercase tracking-[0.2em] ml-1">Analyzing Data</span>
               </div>
             )}
             
             <PromptInputBox 
               onSend={handleSend} 
               isLoading={isLoading} 
               isRecording={isRecording}
               onStartRecording={startRecording}
               onStopRecording={handleVoiceSend}
               placeholder="Poochiye koi bhi sawaal (e.g., Is BCAA safe?)..."
             />
             
             <div className="mt-5 flex items-center justify-center gap-6 opacity-40">
               <div className="flex items-center gap-1.5">
                 <CheckCircle2 className="w-3 h-3 text-green-500" />
                 <span className="text-[9px] font-bold text-gray-400 uppercase tracking-tighter">WADA Code 2024</span>
               </div>
               <div className="flex items-center gap-1.5">
                 <CheckCircle2 className="w-3 h-3 text-orange-500" />
                 <span className="text-[9px] font-bold text-gray-400 uppercase tracking-tighter">NADA Verified</span>
               </div>
               <div className="flex items-center gap-1.5">
                 <XCircle className="w-3 h-3 text-red-500" />
                 <span className="text-[9px] font-bold text-gray-400 uppercase tracking-tighter">Anti-Doping Shield</span>
               </div>
             </div>
           </div>
        </div>
      </main>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(0, 0, 0, 0.05);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(0, 0, 0, 0.1);
        }
        .no-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .no-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
    </div>
  );
};

export default App;
