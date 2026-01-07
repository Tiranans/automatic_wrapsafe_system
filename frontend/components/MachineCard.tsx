"use client";

import React from 'react';
import { Play, Square, RotateCcw, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';

interface MachineCardProps {
  machineId: string;
  status: any;
  onControl: (machineId: string, command: string) => void;
}

export default function MachineCard({ machineId, status, onControl }: MachineCardProps) {
  const isAlarm = status?.alarm_active;
  const isError = status?.error;

  return (
    <div className={`bg-white rounded-xl shadow-lg overflow-hidden border-2 ${isAlarm ? 'border-red-500' : 'border-gray-200'}`}>
      {/* Header */}
      <div className="bg-gray-100 px-4 py-3 flex justify-between items-center">
        <h2 className="text-xl font-bold text-gray-800">Machine {machineId}</h2>
        <div className="flex items-center gap-2">
          {/* Auto/Manual Mode Badge */}
          {status?.mode && (
            <span className={`flex items-center gap-1 px-2 py-1 rounded-full text-sm font-bold ${status.mode.is_auto
              ? 'bg-blue-100 text-blue-700'
              : 'bg-yellow-100 text-yellow-700'
              }`}>
              <span className={`w-2 h-2 rounded-full ${status.mode.is_auto ? 'bg-blue-500' : 'bg-yellow-500'
                }`} />
              Mode: {status.mode.mode_name}
            </span>
          )}

          {isAlarm && (
            <span className="flex items-center gap-1 bg-red-100 text-red-700 px-2 py-1 rounded-full text-sm font-bold animate-pulse">
              <AlertTriangle size={16} /> PERSON DETECTED
            </span>
          )}
          {isError ? (
            <span className="flex items-center gap-1 bg-orange-100 text-orange-700 px-2 py-1 rounded-full text-sm font-bold">
              <XCircle size={16} /> ERROR
            </span>
          ) : (
            <span className="flex items-center gap-1 bg-green-100 text-green-700 px-2 py-1 rounded-full text-sm font-bold">
              <CheckCircle size={16} /> READY
            </span>
          )}
        </div>
      </div>

      {/* Video Feed */}
      <div className="relative aspect-video bg-black">
        {/* Use the API stream URL with dynamic hostname */}
        <img
          src={typeof window !== 'undefined' ? `http://${window.location.hostname}:8061/api/stream/${machineId}` : `/api/stream/${machineId}`}
          alt={`Stream ${machineId}`}
          className="w-full h-full object-contain"
          onError={(e) => {
            (e.target as HTMLImageElement).src = "https://placehold.co/640x480?text=No+Signal";
          }}
        />

        {/* Overlay Stats */}
        <div className="absolute top-2 left-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
          FPS: --
        </div>
      </div>

      {/* Status Details */}
      <div className="px-4 pb-4 text-sm text-gray-600 space-y-1">
        <div className="flex justify-between">
          <span>Last Stop:</span>
          <span className="font-mono">{status?.last_stop_ts ? new Date(status.last_stop_ts * 1000).toLocaleTimeString() : '-'}</span>
        </div>
      </div>
    </div>
  );
}
