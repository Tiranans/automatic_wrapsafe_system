"use client";

import { useEffect, useState } from "react";
import MachineCard from "@/components/MachineCard";
import ProductionStats from "@/components/ProductionStats";
import { Activity } from "lucide-react";

export default function Home() {
  const [status, setStatus] = useState<any>({});
  const [loading, setLoading] = useState(true);

  // Get API URL - use current hostname with port 8061
  const getApiUrl = () => {
    if (typeof window !== 'undefined') {
      return `http://${window.location.hostname}:8061`;
    }
    return 'http://localhost:8061';
  };

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${getApiUrl()}/api/status`);
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
      await fetch(`${getApiUrl()}/api/control/${machineId}`, {
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
        <header className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 p-3 rounded-lg text-white">
              <Activity size={32} />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">BM9 WrapSafe System</h1>
              <p className="text-gray-500">Automatic Safety & Control Dashboard</p>
            </div>
          </div>

          <a
            href="/reports"
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition flex items-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Production Reports
          </a>
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
