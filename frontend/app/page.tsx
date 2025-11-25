"use client";

import { useEffect, useState } from "react";
import MachineCard from "@/components/MachineCard";
import ProductionStats from "@/components/ProductionStats";
import { Activity } from "lucide-react";

export default function Home() {
  const [status, setStatus] = useState<any>({});
  const [loading, setLoading] = useState(true);

  const fetchStatus = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/status");
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (error) {
      console.error("Failed to fetch status", error);
    } finally {
      setLoading(false);
    }
  };

  const handleControl = async (machineId: string, command: string) => {
    try {
      await fetch(`http://localhost:8000/api/control/${machineId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
      });
      // Refresh status immediately
      fetchStatus();
    } catch (error) {
      console.error("Control command failed", error);
      alert(`Failed to send ${command} to Machine ${machineId}`);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8 flex items-center gap-3">
          <div className="bg-blue-600 p-3 rounded-lg text-white">
            <Activity size={32} />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">BM9 WrapSafe System</h1>
            <p className="text-gray-500">Automatic Safety & Control Dashboard</p>
          </div>
        </header>

        {loading ? (
          <div className="text-center py-20 text-gray-500">Loading system status...</div>
        ) : (
          <div className="grid md:grid-cols-2 gap-8">
            <MachineCard
              machineId="A"
              status={status["A"]}
              onControl={handleControl}
            />
            <MachineCard
              machineId="B"
              status={status["B"]}
              onControl={handleControl}
            />
          </div>
        )}

        <div className="mt-8">
          <ProductionStats />
        </div>
      </div>
    </main>
  );
}
