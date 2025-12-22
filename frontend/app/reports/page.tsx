"use client";

import { useState, useEffect } from "react";
import { Printer, FileText, ArrowLeft } from "lucide-react";
import { AgCharts } from "ag-charts-react";

type ReportType = "daily" | "weekly" | "monthly" | "yearly";

interface ProductionDetail {
  log_id: number;
  machine_name: string;
  shift_id: number;
  shift_name: string;
  start_datetime: string;
  end_datetime: string;
  duration_seconds: number;
  duration_minutes: number;
  pieces_completed: number;
  note: string | null;
}

interface ProductionSummary {
  date?: string;
  year?: number;
  month?: number;
  report_type: string;
  machines: {
    [key: string]: {
      machine_name?: string;
      total_rolls: number;
      total_pieces: number;
      total_cycles: number;
      total_duration_min: number;
    };
  };
  daily_data?: Array<any>;
  monthly_data?: Array<any>;
}

interface ProductionImage {
  filename: string;
  path: string;
  size_bytes: number;
  modified_time: string;
}

interface ShiftSummary {
  shift_id: number;
  shift_name: string;
  count: number;
}

export default function ReportPage() {
  const [reportType, setReportType] = useState<ReportType>("daily");
  const [selectedDate, setSelectedDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );
  const [selectedYear, setSelectedYear] = useState<number>(new Date().getFullYear());
  const [selectedMonth, setSelectedMonth] = useState<number>(new Date().getMonth() + 1);
  const [selectedWeekStart, setSelectedWeekStart] = useState<string>(
    getWeekStart(new Date()).toISOString().split("T")[0]
  );

  const [detailsA, setDetailsA] = useState<ProductionDetail[]>([]);
  const [detailsB, setDetailsB] = useState<ProductionDetail[]>([]);
  const [summary, setSummary] = useState<ProductionSummary | null>(null);
  const [images, setImages] = useState<ProductionImage[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentTime, setCurrentTime] = useState<string>('');

  // Chart options state
  const [dailyChartOptions, setDailyChartOptions] = useState<any>(null);
  const [weeklyChartOptions, setWeeklyChartOptions] = useState<any>(null);
  const [monthlyChartOptions, setMonthlyChartOptions] = useState<any>(null);
  const [yearlyChartOptions, setYearlyChartOptions] = useState<any>(null);

  function getWeekStart(date: Date): Date {
    const d = new Date(date);
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1);
    return new Date(d.setDate(diff));
  }

  function getWeekEnd(weekStart: string): string {
    const start = new Date(weekStart);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    return end.toISOString().split("T")[0];
  }

  // Get API URL - use current hostname with port 8061
  const getApiUrl = () => {
    if (typeof window !== 'undefined') {
      return `http://${window.location.hostname}:8061`;
    }
    return 'http://localhost:8061';
  };

  const fetchDailyDetails = async (date: string) => {
    try {
      const resA = await fetch(`${getApiUrl()}/api/production/details?date=${date}&machine=A`);
      const resB = await fetch(`${getApiUrl()}/api/production/details?date=${date}&machine=B`);

      if (resA.ok) {
        const dataA = await resA.json();
        setDetailsA(dataA.logs || []);
      }
      if (resB.ok) {
        const dataB = await resB.json();
        setDetailsB(dataB.logs || []);
      }
    } catch (error) {
      console.error("Failed to fetch details:", error);
    }
  };

  const fetchWeeklyData = async () => {
    const allDetailsA: ProductionDetail[] = [];
    const allDetailsB: ProductionDetail[] = [];

    for (let i = 0; i < 7; i++) {
      const currentDate = new Date(selectedWeekStart);
      currentDate.setDate(currentDate.getDate() + i);
      const dateStr = currentDate.toISOString().split("T")[0];

      try {
        const resA = await fetch(`${getApiUrl()}/api/production/details?date=${dateStr}&machine=A`);
        const resB = await fetch(`${getApiUrl()}/api/production/details?date=${dateStr}&machine=B`);

        if (resA.ok) {
          const dataA = await resA.json();
          allDetailsA.push(...(dataA.logs || []));
        }
        if (resB.ok) {
          const dataB = await resB.json();
          allDetailsB.push(...(dataB.logs || []));
        }
      } catch (error) {
        console.error(`Failed to fetch data for ${dateStr}:`, error);
      }
    }

    setDetailsA(allDetailsA);
    setDetailsB(allDetailsB);
  };

  const getShiftSummary = (details: ProductionDetail[]): ShiftSummary[] => {
    const shiftMap: { [key: number]: ShiftSummary } = {};

    details.filter(d => d.end_datetime !== null).forEach(log => {
      if (!shiftMap[log.shift_id]) {
        shiftMap[log.shift_id] = {
          shift_id: log.shift_id,
          shift_name: log.shift_name,
          count: 0
        };
      }
      shiftMap[log.shift_id].count++;
    });

    return Object.values(shiftMap).sort((a, b) => a.shift_id - b.shift_id);
  };

  const fetchReport = async () => {
    setLoading(true);
    try {
      if (reportType === "daily") {
        await fetchDailyDetails(selectedDate);

        const imgRes = await fetch(`${getApiUrl()}/api/production/images?date=${selectedDate}`);
        if (imgRes.ok) {
          const imgData = await imgRes.json();
          setImages(imgData.images || []);
        }
      } else if (reportType === "weekly") {
        await fetchWeeklyData();
        setImages([]);
      } else if (reportType === "monthly") {
        const url = `${getApiUrl()}/api/production/summary/monthly?year=${selectedYear}&month=${selectedMonth}`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          setSummary(data);
        }
        setImages([]);
      } else if (reportType === "yearly") {
        const url = `${getApiUrl()}/api/production/summary/yearly?year=${selectedYear}`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          setSummary(data);
        }
        setImages([]);
      }
    } catch (error) {
      console.error("Failed to fetch report:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Set current time on client-side only to avoid hydration mismatch
    setCurrentTime(new Date().toLocaleString('th-TH'));
  }, []);

  useEffect(() => {
    fetchReport();
  }, [reportType, selectedDate, selectedYear, selectedMonth, selectedWeekStart]);

  // Build chart data/options when data changes
  useEffect(() => {
    // Daily: build bar chart showing rolls per shift
    if (reportType === "daily") {
      // Aggregate rolls by shift
      const shiftMap: Record<string, { shift: string; A: number; B: number }> = {};

      // Process Machine A data
      detailsA.forEach((log) => {
        if (log.end_datetime) {
          if (!shiftMap[log.shift_name]) {
            shiftMap[log.shift_name] = { shift: log.shift_name, A: 0, B: 0 };
          }
          shiftMap[log.shift_name].A += 1;
        }
      });

      // Process Machine B data
      detailsB.forEach((log) => {
        if (log.end_datetime) {
          if (!shiftMap[log.shift_name]) {
            shiftMap[log.shift_name] = { shift: log.shift_name, A: 0, B: 0 };
          }
          shiftMap[log.shift_name].B += 1;
        }
      });

      const data = Object.values(shiftMap);

      if (data.length > 0) {
        setDailyChartOptions({
          // title: { text: "Daily Chart (Shift)" },
          data,
          axes: [
            {
              type: "category",
              position: "bottom",
              title: { text: "Shift" }
            },
            {
              type: "number",
              position: "left",
              title: { text: "Rolls" }
            }
          ],
          series: [
            {
              type: "bar",
              xKey: "shift",
              yKey: "A",
              yName: "Machine A",
              fill: "#1d4ed8",
              stroke: "#1d4ed8"
            },
            {
              type: "bar",
              xKey: "shift",
              yKey: "B",
              yName: "Machine B",
              fill: "#16a34a",
              stroke: "#16a34a"
            }
          ],
          legend: { position: "bottom" }
        });
      } else {
        setDailyChartOptions(null);
      }
    } else {
      setDailyChartOptions(null);
    }

    // Weekly: build daily chart for 7 days
    if (reportType === "weekly") {
      // Aggregate daily rolls from details arrays
      const dayMap: Record<string, { A: number; B: number }> = {};
      for (let i = 0; i < 7; i++) {
        const d = new Date(selectedWeekStart);
        d.setDate(d.getDate() + i);
        const ds = d.toISOString().split("T")[0];
        dayMap[ds] = dayMap[ds] || { A: 0, B: 0 };
      }
      detailsA.forEach((log) => {
        const date = log.start_datetime.split(" ")[0];
        if (dayMap[date]) {
          if (log.end_datetime) dayMap[date].A += 1;
        }
      });
      detailsB.forEach((log) => {
        const date = log.start_datetime.split(" ")[0];
        if (dayMap[date]) {
          if (log.end_datetime) dayMap[date].B += 1;
        }
      });

      const data = Object.keys(dayMap).map((date) => ({
        date: new Date(date),
        A: dayMap[date].A,
        B: dayMap[date].B,
        Total: dayMap[date].A + dayMap[date].B,
      }));

      setWeeklyChartOptions({
        // title: { text: "Weekly Chart (Daily Rolls)" },
        data,
        axes: [
          { type: "time", position: "bottom", title: { text: "Date" }, label: { format: "%d/%m" } },
          { type: "number", position: "left", title: { text: "Rolls" } }
        ],
        series: [
          { type: "bar", xKey: "date", yKey: "A", yName: "Machine A", fill: "#1d4ed8", stroke: "#1d4ed8" },
          { type: "bar", xKey: "date", yKey: "B", yName: "Machine B", fill: "#16a34a", stroke: "#16a34a" },
          { type: "bar", xKey: "date", yKey: "Total", yName: "Total", fill: "#ea580c", stroke: "#ea580c" }
        ],
        legend: { position: "bottom" }
      });
    } else {
      setWeeklyChartOptions(null);
    }

    // Monthly: use summary.daily_data (each day in month)
    if (reportType === "monthly" && summary?.daily_data?.length) {
      const data = summary.daily_data.map((day: any) => ({
        date: new Date(day.date),
        A: day.machines?.A?.rolls || 0,
        B: day.machines?.B?.rolls || 0,
        Total: (day.machines?.A?.rolls || 0) + (day.machines?.B?.rolls || 0),
      }));
      setMonthlyChartOptions({
        // title: { text: "Monthly Chart (Daily Rolls)" },
        data,
        axes: [
          { type: "time", position: "bottom", title: { text: "Date" }, label: { format: "%d/%m" } },
          { type: "number", position: "left", title: { text: "Rolls" } }
        ],
        series: [
          { type: "bar", xKey: "date", yKey: "A", yName: "Machine A", fill: "#1d4ed8", stroke: "#1d4ed8" },
          { type: "bar", xKey: "date", yKey: "B", yName: "Machine B", fill: "#16a34a", stroke: "#16a34a" },
          { type: "bar", xKey: "date", yKey: "Total", yName: "Total", fill: "#ea580c", stroke: "#ea580c" }
        ],
        legend: { position: "bottom" }
      });
    } else {
      setMonthlyChartOptions(null);
    }

    // Yearly: use summary.monthly_data (each month in year)
    if (reportType === "yearly" && summary?.monthly_data?.length) {
      const data = summary.monthly_data.map((m: any) => ({
        month: new Date(selectedYear, m.month - 1, 1),
        A: m.machines?.A?.rolls || 0,
        B: m.machines?.B?.rolls || 0,
        Total: (m.machines?.A?.rolls || 0) + (m.machines?.B?.rolls || 0),
      }));
      setYearlyChartOptions({
        // title: { text: "Yearly Chart (Monthly Rolls)" },
        data,
        axes: [
          { type: "time", position: "bottom", title: { text: "Month" }, label: { format: "%b" } },
          { type: "number", position: "left", title: { text: "Rolls" } }
        ],
        series: [
          { type: "bar", xKey: "month", yKey: "A", yName: "Machine A", fill: "#1d4ed8", stroke: "#1d4ed8" },
          { type: "bar", xKey: "month", yKey: "B", yName: "Machine B", fill: "#16a34a", stroke: "#16a34a" },
          { type: "bar", xKey: "month", yKey: "Total", yName: "Total", fill: "#ea580c", stroke: "#ea580c" }
        ],
        legend: { position: "bottom" }
      });
    } else {
      setYearlyChartOptions(null);
    }
  }, [reportType, summary, detailsA, detailsB, selectedWeekStart, selectedYear, selectedDate]);

  const handlePrint = () => {
    window.print();
  };

  const getReportTitle = () => {
    if (reportType === "daily") {
      return `Daily Bm9 wrapped Report - ${selectedDate}`;
    } else if (reportType === "weekly") {
      const weekEnd = getWeekEnd(selectedWeekStart);
      return `Weekly Bm9 wrapped Report - ${selectedWeekStart} to ${weekEnd}`;
    } else if (reportType === "monthly") {
      const monthName = new Date(selectedYear, selectedMonth - 1).toLocaleString('th-TH', { month: 'long' });
      return `Monthly Bm9 wrapped Report - ${monthName} ${selectedYear}`;
    } else {
      return `Yearly Bm9 wrapped Report - ${selectedYear}`;
    }
  };

  const getTotalRolls = (details: ProductionDetail[]) => {
    return details.filter(d => d.end_datetime !== null).length;
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <header className="mb-8 flex items-center justify-between print:mb-4">
          <div className="flex items-center gap-3">
            <a href="/"
              className="bg-gray-200 p-2 rounded-lg text-gray-700 hover:bg-gray-300 transition print:hidden"
            >
              <ArrowLeft size={24} />
            </a>
            <div className="bg-green-600 p-3 rounded-lg text-white">
              <FileText size={32} />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Bm9 wrapped Reports</h1>
              <p className="text-gray-500">Roll Wrapped Summary</p>
            </div>
          </div>

          <button
            onClick={handlePrint}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition print:hidden"
          >
            <Printer size={20} />
            Print
          </button>
        </header>

        {/* Controls */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6 print:hidden">
          <div className="grid md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-bold text-gray-900 mb-2">
                Report Type
              </label>
              <select
                value={reportType}
                onChange={(e) => setReportType(e.target.value as ReportType)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-semibold text-gray-900"
              >
                <option value="daily">รายวัน (Daily)</option>
                <option value="weekly">รายสัปดาห์ (Weekly)</option>
                <option value="monthly">รายเดือน (Monthly)</option>
                <option value="yearly">รายปี (Yearly)</option>
              </select>
            </div>

            {reportType === "daily" && (
              <div>
                <label className="block text-sm font-bold text-gray-900 mb-2">
                  วันที่ (Date)
                </label>
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-semibold text-gray-900"
                />
              </div>
            )}

            {reportType === "weekly" && (
              <div>
                <label className="block text-sm font-bold text-gray-900 mb-2">
                  สัปดาห์เริ่มต้น (Week Start)
                </label>
                <input
                  type="date"
                  value={selectedWeekStart}
                  onChange={(e) => setSelectedWeekStart(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-semibold text-gray-900"
                />
              </div>
            )}

            {reportType === "monthly" && (
              <>
                <div>
                  <label className="block text-sm font-bold text-gray-900 mb-2">
                    ปี (Year)
                  </label>
                  <input
                    type="number"
                    value={selectedYear}
                    onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-semibold text-gray-900"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-gray-900 mb-2">
                    เดือน (Month)
                  </label>
                  <select
                    value={selectedMonth}
                    onChange={(e) => setSelectedMonth(parseInt(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-semibold text-gray-900"
                  >
                    {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                      <option key={m} value={m}>
                        {new Date(2000, m - 1).toLocaleString('th-TH', { month: 'long' })}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            )}

            {reportType === "yearly" && (
              <div>
                <label className="block text-sm font-bold text-gray-900 mb-2">
                  ปี (Year)
                </label>
                <input
                  type="number"
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-semibold text-gray-900"
                />
              </div>
            )}
          </div>
        </div>

        {/* Report Content */}
        {loading ? (
          <div className="text-center py-20 text-gray-500">Loading report...</div>
        ) : (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm p-6 print:shadow-none">
              <h2 className="text-2xl font-bold text-gray-900 mb-2">{getReportTitle()}</h2>
              <p className="text-gray-700 font-medium">Generated on {currentTime || 'Loading...'}</p>
            </div>

            {/* Daily/Weekly Report - Shift Summary */}
            {(reportType === "daily" || reportType === "weekly") && (
              <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="grid md:grid-cols-2 gap-6 p-6">
                  {/* Machine A */}
                  <div>
                    <h3 className="text-xl font-bold text-gray-900 mb-4">Machine A</h3>
                    <div className="bg-blue-50 p-4 rounded-lg mb-4">
                      <div className="text-sm font-semibold text-gray-900">Total Rolls</div>
                      <div className="text-3xl font-bold text-blue-600">{getTotalRolls(detailsA)}</div>
                    </div>
                    <div className="space-y-2">
                      <h4 className="font-bold text-gray-900">Shift Summary</h4>
                      {getShiftSummary(detailsA).length > 0 ? (
                        getShiftSummary(detailsA).map((shift) => (
                          <div key={shift.shift_id} className="flex justify-between items-center p-3 bg-gray-50 rounded">
                            <span className="font-bold text-gray-900">{shift.shift_name}</span>
                            <span className="text-lg font-bold text-blue-600">{shift.count} rolls</span>
                          </div>
                        ))
                      ) : (
                        <div className="text-center py-4 text-gray-500">No data</div>
                      )}
                    </div>
                  </div>

                  {/* Machine B */}
                  <div>
                    <h3 className="text-xl font-bold text-gray-900 mb-4">Machine B</h3>
                    <div className="bg-green-50 p-4 rounded-lg mb-4">
                      <div className="text-sm font-semibold text-gray-900">Total Rolls</div>
                      <div className="text-3xl font-bold text-green-600">{getTotalRolls(detailsB)}</div>
                    </div>
                    <div className="space-y-2">
                      <h4 className="font-bold text-gray-900">Shift Summary</h4>
                      {getShiftSummary(detailsB).length > 0 ? (
                        getShiftSummary(detailsB).map((shift) => (
                          <div key={shift.shift_id} className="flex justify-between items-center p-3 bg-gray-50 rounded">
                            <span className="font-bold text-gray-900">{shift.shift_name}</span>
                            <span className="text-lg font-bold text-green-600">{shift.count} rolls</span>
                          </div>

                        ))
                      ) : (
                        <div className="text-center py-4 text-gray-500">No data</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Monthly Report */}
            {reportType === "monthly" && summary && (
              <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">Monthly Summary</h3>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-bold text-gray-900 uppercase">Date</th>
                          <th className="px-4 py-3 text-center text-xs font-bold text-gray-900 uppercase">Machine A</th>
                          <th className="px-4 py-3 text-center text-xs font-bold text-gray-900 uppercase">Machine B</th>
                          <th className="px-4 py-3 text-center text-xs font-bold text-gray-900 uppercase">Total</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {summary.daily_data && summary.daily_data.length > 0 ? (
                          summary.daily_data.map((day: any) => {
                            const rollsA = day.machines?.A?.rolls || 0;
                            const rollsB = day.machines?.B?.rolls || 0;
                            return (
                              <tr key={day.date} className="hover:bg-gray-50">
                                <td className="px-4 py-3 text-sm font-medium text-gray-900">
                                  {new Date(day.date).toLocaleDateString('th-TH')}
                                </td>
                                <td className="px-4 py-3 text-sm text-center text-gray-900">{rollsA}</td>
                                <td className="px-4 py-3 text-sm text-center text-gray-900">{rollsB}</td>
                                <td className="px-4 py-3 text-sm text-center font-semibold text-gray-900">
                                  {rollsA + rollsB}
                                </td>
                              </tr>
                            );
                          })
                        ) : (
                          <tr>
                            <td colSpan={4} className="px-4 py-8 text-center text-gray-500">No data</td>
                          </tr>
                        )}
                        {summary.daily_data && summary.daily_data.length > 0 && (
                          <tr className="bg-gray-100 font-bold">
                            <td className="px-4 py-3 text-sm text-gray-900">Total</td>
                            <td className="px-4 py-3 text-sm text-center text-gray-900">
                              {summary.machines?.A?.total_rolls || 0}
                            </td>
                            <td className="px-4 py-3 text-sm text-center text-gray-900">
                              {summary.machines?.B?.total_rolls || 0}
                            </td>
                            <td className="px-4 py-3 text-sm text-center text-gray-900">
                              {(summary.machines?.A?.total_rolls || 0) + (summary.machines?.B?.total_rolls || 0)}
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* Yearly Report */}
            {reportType === "yearly" && summary && (
              <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">Yearly Summary</h3>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-bold text-gray-900 uppercase">Month</th>
                          <th className="px-4 py-3 text-center text-xs font-bold text-gray-900 uppercase">Machine A</th>
                          <th className="px-4 py-3 text-center text-xs font-bold text-gray-900 uppercase">Machine B</th>
                          <th className="px-4 py-3 text-center text-xs font-bold text-gray-900 uppercase">Total</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {summary.monthly_data && summary.monthly_data.length > 0 ? (
                          summary.monthly_data.map((monthData: any) => {
                            const rollsA = monthData.machines?.A?.rolls || 0;
                            const rollsB = monthData.machines?.B?.rolls || 0;
                            const monthName = new Date(selectedYear, monthData.month - 1).toLocaleString('th-TH', { month: 'long' });
                            return (
                              <tr key={monthData.month} className="hover:bg-gray-50">
                                <td className="px-4 py-3 text-sm font-medium text-gray-900">{monthName}</td>
                                <td className="px-4 py-3 text-sm text-center text-gray-900">{rollsA}</td>
                                <td className="px-4 py-3 text-sm text-center text-gray-900">{rollsB}</td>
                                <td className="px-4 py-3 text-sm text-center font-semibold text-gray-900">
                                  {rollsA + rollsB}
                                </td>
                              </tr>
                            );
                          })
                        ) : (
                          <tr>
                            <td colSpan={4} className="px-4 py-8 text-center text-gray-500">No data</td>
                          </tr>
                        )}
                        {summary.monthly_data && summary.monthly_data.length > 0 && (
                          <tr className="bg-gray-100 font-bold">
                            <td className="px-4 py-3 text-sm text-gray-900">Total</td>
                            <td className="px-4 py-3 text-sm text-center text-gray-900">
                              {summary.machines?.A?.total_rolls || 0}
                            </td>
                            <td className="px-4 py-3 text-sm text-center text-gray-900">
                              {summary.machines?.B?.total_rolls || 0}
                            </td>
                            <td className="px-4 py-3 text-sm text-center text-gray-900">
                              {(summary.machines?.A?.total_rolls || 0) + (summary.machines?.B?.total_rolls || 0)}
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* Daily Report chart */}
            {(reportType === "daily") && dailyChartOptions && (
              <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="p-6">
                  <h4 className="text-lg font-bold text-gray-900 mb-2">Daily Production by Shift</h4>
                  <AgCharts options={dailyChartOptions} />
                </div>
              </div>
            )}

            {/* Weekly Report chart */}
            {(reportType === "weekly") && weeklyChartOptions && (
              <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="p-6 border-t">
                  <h4 className="text-lg font-bold text-gray-900 mb-2">Weekly Chart (Daily Rolls)</h4>
                  <AgCharts options={weeklyChartOptions} />
                </div>
              </div>
            )}

            {/* Monthly Report chart */}
            {(reportType === "monthly") && monthlyChartOptions && (
              <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="p-6 border-t">
                  <h4 className="text-lg font-bold text-gray-900 mb-2">Monthly Chart (Daily Rolls)</h4>
                  <AgCharts options={monthlyChartOptions} />
                </div>
              </div>
            )}

            {/* Yearly Report chart */}
            {(reportType === "yearly") && yearlyChartOptions && (
              <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="p-6 border-t">
                  <h4 className="text-lg font-bold text-gray-900 mb-2">Yearly Chart (Monthly Rolls)</h4>
                  <AgCharts options={yearlyChartOptions} />
                </div>
              </div>
            )}

            {/* Production Images */}
            {reportType === "daily" && images.length > 0 && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                {/* <h3 className="text-xl font-bold text-gray-900 mb-4">Production Images</h3> */}
                <div className="grid md:grid-cols-4 gap-4">
                  {/* {images.map((img, idx) => (
                    <div key={idx} className="border border-gray-200 rounded-lg p-3">
                      <img
                        src={`${getApiUrl()}/static/${img.path.replace(/\\/g, '/')}`}
                        alt={img.filename}
                        className="w-full h-32 object-cover rounded mb-2"
                        onError={(e) => {
                          (e.target as HTMLImageElement).src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100" height="100"%3E%3Crect fill="%23ddd" width="100" height="100"/%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" dy=".3em" fill="%23999"%3ENo Image%3C/text%3E%3C/svg%3E';
                        }}
                      />
                      <div className="text-xs text-gray-600 truncate">{img.filename}</div>
                      <div className="text-xs text-gray-400">
                        {new Date(img.modified_time).toLocaleTimeString('th-TH')}
                      </div>
                    </div>
                  ))} */}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <style jsx global>{`
        @media print {
          body {
            print-color-adjust: exact;
            -webkit-print-color-adjust: exact;
          }
          .print\\:hidden {
            display: none !important;
          }
          .print\\:shadow-none {
            box-shadow: none !important;
          }
          .print\\:mb-4 {
            margin-bottom: 1rem !important;
          }
          table {
            page-break-inside: auto;
          }
          tr {
            page-break-inside: avoid;
            page-break-after: auto;
          }
        }
      `}</style>
    </main >
  );
}
