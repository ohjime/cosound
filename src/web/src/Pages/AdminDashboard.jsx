import { useState, useEffect } from 'react';

const DJANGO_API_URL = "http://10.29.148.151:8000/api";
const SUPABASE_URL = "https://bjieozmcptbxgbvzpfyc.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJqaWVvem1jcHRieGdidnpwZnljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI1NTQ1NzYsImV4cCI6MjA3ODEzMDU3Nn0.Oq6ZL3L3epSTiGF_dtZ5IykfJEQAsGCipsL8BRHoBrk";

export default function AdminDashboard() {
  const [devices, setDevices] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({
    totalDevices: 0,
    connectedDevices: 0,
    disconnectedDevices: 0,
    gracePeriodDevices: 0,
    totalSessions: 0,
    activeSessions: 0
  });
  const [charts, setCharts] = useState({
    statusChart: null,
    durationsChart: null
  });

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      setError(null);

      // Fetch devices from Supabase
      const devicesRes = await fetch(
        `${SUPABASE_URL}/rest/v1/test_bt_devices?select=*`,
        {
          headers: {
            'apikey': SUPABASE_ANON_KEY,
            'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
          }
        }
      );

      if (devicesRes.ok) {
        const devicesData = await devicesRes.json();
        setDevices(Array.isArray(devicesData) ? devicesData : []);
        
        // Calculate stats
        const connected = devicesData.filter(d => d.status === 'connected').length;
        const disconnected = devicesData.filter(d => d.status === 'disconnected').length;
        const gracePeriod = devicesData.filter(d => d.status === 'grace_period').length;
        
        setStats(prev => ({
          ...prev,
          totalDevices: devicesData.length,
          connectedDevices: connected,
          disconnectedDevices: disconnected,
          gracePeriodDevices: gracePeriod
        }));
      }

      // Fetch sessions from Supabase (last 7 days)
      const sevenDaysAgo = new Date();
      sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
      
      const sessionsRes = await fetch(
        `${SUPABASE_URL}/rest/v1/test_bt_sessions?select=*&connected_at=gte.${sevenDaysAgo.toISOString()}&order=connected_at.desc`,
        {
          headers: {
            'apikey': SUPABASE_ANON_KEY,
            'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
          }
        }
      );

      if (sessionsRes.ok) {
        const sessionsData = await sessionsRes.json();
        setSessions(Array.isArray(sessionsData) ? sessionsData : []);
        
        const active = sessionsData.filter(s => s.status === 'active').length;
        setStats(prev => ({
          ...prev,
          totalSessions: sessionsData.length,
          activeSessions: active
        }));
      }

      // Fetch matplotlib charts from Django
      const chartsRes = await fetch(`${DJANGO_API_URL}/analytics/charts?limit=10`);
      if (chartsRes.ok) {
        const chartsData = await chartsRes.json();
        if (chartsData.success && chartsData.charts) {
          setCharts({
            statusChart: chartsData.charts.status_pie,
            durationsChart: chartsData.charts.session_durations
          });
        }
      }

      setLoading(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      setError(error.message);
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
        <div className="text-xl">Loading dashboard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
        <div className="text-center">
          <div className="text-red-500 text-xl mb-4">⚠️ Error</div>
          <div className="text-gray-400">{error}</div>
          <button 
            onClick={() => fetchData()}
            className="mt-4 px-6 py-2 bg-blue-600 rounded-lg hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2">Bluetooth Presence Dashboard</h1>
          <p className="text-gray-400">Real-time device monitoring and analytics</p>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            title="Total Devices"
            value={stats.totalDevices}
            icon="📱"
            color="bg-blue-600"
          />
          <StatCard
            title="Connected"
            value={stats.connectedDevices}
            icon="✅"
            color="bg-green-600"
          />
          <StatCard
            title="Grace Period"
            value={stats.gracePeriodDevices}
            icon="⏳"
            color="bg-yellow-600"
          />
          <StatCard
            title="Active Sessions"
            value={stats.activeSessions}
            icon="🔄"
            color="bg-purple-600"
          />
        </div>

        {/* Charts Row - Real Matplotlib Images from Django */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Device Status Pie Chart */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-2xl font-bold mb-4">🥧 Device Status (Matplotlib)</h2>
            {charts.statusChart ? (
              <img 
                src={charts.statusChart} 
                alt="Device Status Chart" 
                className="w-full rounded"
              />
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-400">
                Loading chart from Django...
              </div>
            )}
          </div>

          {/* Session Durations Chart */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-2xl font-bold mb-4">⏱️ Recent Session Durations</h2>
            {charts.durationsChart ? (
              <img 
                src={charts.durationsChart} 
                alt="Session Durations Chart" 
                className="w-full rounded"
              />
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-400">
                Loading chart from Django...
              </div>
            )}
          </div>
        </div>

        {/* Devices Table */}
        <div className="bg-gray-800 rounded-lg p-6 mb-8">
          <h2 className="text-2xl font-bold mb-4">Registered Devices</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left py-3 px-4">Device Name</th>
                  <th className="text-left py-3 px-4">MAC Address</th>
                  <th className="text-left py-3 px-4">Status</th>
                  <th className="text-left py-3 px-4">Last Seen</th>
                  <th className="text-left py-3 px-4">RSSI</th>
                </tr>
              </thead>
              <tbody>
                {devices.length > 0 ? (
                  devices.map(device => (
                    <tr key={device.id} className="border-b border-gray-700 hover:bg-gray-700/50 transition">
                      <td className="py-3 px-4">{device.device_name}</td>
                      <td className="py-3 px-4 font-mono text-sm">{device.device_mac}</td>
                      <td className="py-3 px-4">
                        <StatusBadge status={device.status} />
                      </td>
                      <td className="py-3 px-4 text-sm">
                        {device.last_seen ? new Date(device.last_seen).toLocaleString() : 'Never'}
                      </td>
                      <td className="py-3 px-4">{device.rssi ? `${device.rssi} dBm` : '-'}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="5" className="py-8 text-center text-gray-400">
                      <div className="mb-2">📡 No devices registered yet</div>
                      <div className="text-sm">Devices will appear here when scanner detects them</div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Sessions */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-2xl font-bold mb-4">Recent Sessions (Last 7 Days)</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left py-3 px-4">Device MAC</th>
                  <th className="text-left py-3 px-4">Device Name</th>
                  <th className="text-left py-3 px-4">Connected At</th>
                  <th className="text-left py-3 px-4">Disconnected At</th>
                  <th className="text-left py-3 px-4">Duration</th>
                  <th className="text-left py-3 px-4">Status</th>
                </tr>
              </thead>
              <tbody>
                {sessions.length > 0 ? (
                  sessions.slice(0, 10).map(session => {
                    const connectedAt = new Date(session.connected_at);
                    const disconnectedAt = session.disconnected_at ? new Date(session.disconnected_at) : null;
                    const duration = disconnectedAt 
                      ? Math.round((disconnectedAt - connectedAt) / 60000) 
                      : Math.round((new Date() - connectedAt) / 60000);

                    return (
                      <tr key={session.id} className="border-b border-gray-700 hover:bg-gray-700/50 transition">
                        <td className="py-3 px-4 font-mono text-sm">{session.device_mac}</td>
                        <td className="py-3 px-4">{session.device_name || 'Unknown'}</td>
                        <td className="py-3 px-4 text-sm">{connectedAt.toLocaleString()}</td>
                        <td className="py-3 px-4 text-sm">
                          {disconnectedAt ? disconnectedAt.toLocaleString() : '-'}
                        </td>
                        <td className="py-3 px-4">{duration} min</td>
                        <td className="py-3 px-4">
                          <SessionStatusBadge status={session.status} />
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan="6" className="py-8 text-center text-gray-400">
                      <div className="mb-2">📝 No sessions recorded yet</div>
                      <div className="text-sm">Sessions will appear here when devices connect</div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ title, value, icon, color }) {
  return (
    <div className={`${color} rounded-lg p-6 shadow-lg`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-white text-opacity-80 text-sm mb-1">{title}</p>
          <p className="text-3xl font-bold text-white">{value}</p>
        </div>
        <div className="text-4xl">{icon}</div>
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const styles = {
    connected: 'bg-green-600 text-white',
    disconnected: 'bg-red-600 text-white',
    grace_period: 'bg-yellow-600 text-white'
  };

  return (
    <span className={`${styles[status] || 'bg-gray-600 text-white'} px-3 py-1 rounded-full text-xs font-semibold`}>
      {status.replace('_', ' ').toUpperCase()}
    </span>
  );
}

function SessionStatusBadge({ status }) {
  const styles = {
    active: 'bg-green-600 text-white',
    ended: 'bg-gray-600 text-white'
  };

  return (
    <span className={`${styles[status] || 'bg-gray-600 text-white'} px-3 py-1 rounded-full text-xs font-semibold`}>
      {status.toUpperCase()}
    </span>
  );
}
