"use client";

import React, { useEffect, useState } from 'react';
import { BarChart3, RefreshCw } from 'lucide-react';

interface ShiftStats {
    1: number;
    2: number;
    3: number;
}

interface MachineStats {
    total: number;
    shifts: ShiftStats;
}

interface ProductionData {
    date: string;
    machines: {
        [key: string]: MachineStats;
    };
}

export default function ProductionStats() {
    const [stats, setStats] = useState<ProductionData | null>(null);
    const [loading, setLoading] = useState(true);

    // Get API URL - use current hostname with port 8061
    const getApiUrl = () => {
        if (typeof window !== 'undefined') {
            return `http://${window.location.hostname}:8061`;
        }
        return 'http://localhost:8061';
    };

    const fetchStats = async () => {
        try {
            const res = await fetch(`${getApiUrl()}/api/production/stats`);
            if (res.ok) {
                const data = await res.json();
                setStats(data);
            }
        } catch (error) {
            console.error("Failed to fetch production stats", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchStats();
        const interval = setInterval(fetchStats, 5000); // Refresh every 5 seconds
        return () => clearInterval(interval);
    }, []);

    if (loading && !stats) {
        return <div className="animate-pulse h-32 bg-gray-200 rounded-xl"></div>;
    }

    return (
        <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-6">
            <div className="flex justify-between items-center mb-4">
                <div className="flex items-center gap-2">
                    <BarChart3 className="text-blue-600" />
                    <h2 className="text-xl font-bold text-gray-800">Production Count</h2>
                </div>
                <span className="text-sm text-gray-500">
                    {stats?.date}
                </span>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50">
                        <tr>
                            <th className="px-4 py-3 rounded-tl-lg">Machine</th>
                            <th className="px-4 py-3 text-center">Shift 1 (08-16)</th>
                            <th className="px-4 py-3 text-center">Shift 2 (16-00)</th>
                            <th className="px-4 py-3 text-center">Shift 3 (00-08)</th>
                            <th className="px-4 py-3 text-right text-gray-900 font-medium rounded-tr-lg">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {['A', 'B'].map((mid) => {
                            const mStats = stats?.machines[mid];
                            return (
                                <tr key={mid} className="border-b hover:bg-gray-50">
                                    <td className="px-4 py-4 font-bold text-gray-900">Machine {mid}</td>
                                    <td className="px-4 py-4 text-center font-mono text-blue-600">
                                        {mStats?.shifts[1] || 0}
                                    </td>
                                    <td className="px-4 py-4 text-center font-mono text-purple-600">
                                        {mStats?.shifts[2] || 0}
                                    </td>
                                    <td className="px-4 py-4 text-center font-mono text-orange-600">
                                        {mStats?.shifts[3] || 0}
                                    </td>
                                    <td className="px-4 py-4 text-right font-medium text-gray-900 text-lg">
                                        {mStats?.total || 0}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
