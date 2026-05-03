import { VoiceClient } from "@/components/voice-client";

function App() {
  return (
    <div className="dark min-h-screen bg-background text-foreground flex flex-col items-center justify-center px-4 py-12">
      <header className="mb-10 text-center space-y-2">
        <h1 className="text-4xl font-bold tracking-tight">Vaaksetu</h1>
        <p className="text-muted-foreground">Real-time voice AI call assistant</p>
      </header>

      <VoiceClient />
    </div>
  );
}

export default App;
