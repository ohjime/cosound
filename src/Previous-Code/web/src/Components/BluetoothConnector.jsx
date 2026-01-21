import { useState, useEffect } from 'react';
import { Bluetooth, Check, X, RefreshCw } from 'lucide-react';
import { supabase } from '../lib/supabase';

// Python Bluetooth server URL (separate server on port 3001)
// Use window.location.hostname to work on network IPs
const BT_SERVER_URL = `http://${window.location.hostname}:3001`;

// Arduino Nano 33 BLE service UUID (customize based on your Arduino sketch)
const BLE_SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214'; // Generic example
const BLE_CHARACTERISTIC_UUID = '19b10001-e8f2-537e-4f6c-d104768a1214';

export function BluetoothConnector() {
  const [isSupported, setIsSupported] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isPairing, setIsPairing] = useState(false);
  const [deviceName, setDeviceName] = useState(null);
  const [deviceId, setDeviceId] = useState(null);
  const [error, setError] = useState(null);
  const [requiresTap, setRequiresTap] = useState(false);
  const [isAutoReconnecting, setIsAutoReconnecting] = useState(false);

  // Check if Web Bluetooth is supported and auto-reconnect to paired devices
  useEffect(() => {
    const checkSupport = async () => {
      // Check if bluetooth exists in navigator
      if (!('bluetooth' in navigator)) {
        setIsSupported(false);
        setError('Web Bluetooth API not available in this browser');
        return;
      }

      // Check if getAvailability exists (Chrome 78+)
      if (navigator.bluetooth.getAvailability) {
        try {
          const available = await navigator.bluetooth.getAvailability();
          if (!available) {
            setIsSupported(false);
            setError('Bluetooth adapter not found or disabled');
            return;
          }
        } catch (err) {
          console.warn('Could not check Bluetooth availability:', err);
        }
      }

      setIsSupported(true);

      // Try to auto-reconnect to paired device
      await attemptAutoReconnect();
    };

    checkSupport();
  }, []);

  /**
   * Attempt to auto-reconnect to previously paired device
   * Uses navigator.bluetooth.getDevices() to avoid showing pairing dialog
   */
  const attemptAutoReconnect = async () => {
    try {
      // Check if user is authenticated
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) {
        console.log('Not authenticated, skipping auto-reconnect');
        return;
      }

      // Get previously paired devices from browser (no dialog shown)
      if (!navigator.bluetooth.getDevices) {
        console.log('getDevices() not available, skipping auto-reconnect');
        return;
      }

      const devices = await navigator.bluetooth.getDevices();
      if (devices.length === 0) {
        console.log('No paired devices found');
        return;
      }

      console.log(`Found ${devices.length} paired device(s)`);

      // Check if we have an active auto-reconnect window (30 minutes)
      const autoReconnectUntil = localStorage.getItem('btAutoReconnectUntil');
      const storedDeviceId = localStorage.getItem('btDeviceId');

      if (!autoReconnectUntil || !storedDeviceId) {
        console.log('No auto-reconnect data found');
        return;
      }

      // Check if auto-reconnect window is still valid
      const reconnectExpiry = new Date(autoReconnectUntil);
      if (reconnectExpiry < new Date()) {
        console.log('Auto-reconnect window expired');
        localStorage.removeItem('btAutoReconnectUntil');
        return;
      }

      // Find the previously connected device
      const targetDevice = devices.find(d => d.id === storedDeviceId);

      if (!targetDevice) {
        console.log('Paired device not found in browser');
        return;
      }

      console.log(`Auto-reconnecting to ${targetDevice.name} (${Math.round((reconnectExpiry - new Date()) / 60000)} min left)`);
      setIsAutoReconnecting(true);

      // Connect without showing pairing dialog
      await connectToDevice(targetDevice);

      setIsAutoReconnecting(false);
    } catch (err) {
      console.error('Auto-reconnect failed:', err);
      setIsAutoReconnecting(false);
    }
  };

  /**
   * Connect to a specific Bluetooth device
   * Can be called with a device from requestDevice() or getDevices()
   */
  const connectToDevice = async (device) => {
    console.log('✅ Device selected:', device.name);
    setDeviceName(device.name);
    setDeviceId(device.id);

    // Connect to GATT server
    const server = await device.gatt.connect();
    console.log('✅ Connected to GATT server');

    // Get user info from Supabase
    const { data: { user } } = await supabase.auth.getUser();

    if (!user) {
      throw new Error('User not authenticated');
    }

    // Save to bluetooth_devices table (your existing table)
    const { error: pairError } = await supabase
      .from('bluetooth_devices')
      .upsert({
        user_id: user.id,
        device_id: device.id,
        device_name: device.name,
        last_seen: new Date().toISOString(),
        status: 'connected'
      }, {
        onConflict: 'user_id,device_id'
      })
      .select()
      .single();

    if (pairError) {
      console.error('Failed to save paired device:', pairError);
    } else {
      console.log('✅ Device saved to bluetooth_devices table');
    }

    // Store auto-reconnect timestamp in localStorage (30 minutes from now)
    const autoReconnectUntil = new Date();
    autoReconnectUntil.setMinutes(autoReconnectUntil.getMinutes() + 30);
    localStorage.setItem('btAutoReconnectUntil', autoReconnectUntil.toISOString());
    console.log('✅ Auto-reconnect window active for 30 minutes');

    // Listen for disconnection
    device.addEventListener('gattserverdisconnected', () => onDisconnected(device));

    setIsConnected(true);

    // Store device ID in localStorage
    localStorage.setItem('btDeviceId', device.id);
    localStorage.setItem('btDeviceName', device.name);
  };

  /**
   * Show pairing dialog and connect to new device
   */
  const handleConnect = async () => {
    setIsPairing(true);
    setError(null);

    try {
      console.log('🔵 Requesting Bluetooth device...');

      // Request device from user (shows pairing dialog)
      const device = await navigator.bluetooth.requestDevice({
        filters: [
          { namePrefix: 'SoundGuys' }, // Look for "SoundGuys Beacon"
          { namePrefix: 'Arduino' }, // Also accept devices starting with "Arduino"
          { services: [BLE_SERVICE_UUID] }
        ],
        optionalServices: [BLE_SERVICE_UUID]
      });

      await connectToDevice(device);
      setIsPairing(false);

    } catch (err) {
      console.error('❌ Bluetooth connection error:', err);
      setError(err.message);
      setIsPairing(false);
    }
  };

  /**
   * Handle device disconnection
   */
  const onDisconnected = async (device) => {
    console.log('🔌 Device disconnected:', device.name);
    setIsConnected(false);

    try {
      // Get user
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;

      // Update bluetooth_devices table: mark as disconnected
      await supabase
        .from('bluetooth_devices')
        .update({
          status: 'disconnected',
          last_seen: new Date().toISOString()
        })
        .eq('user_id', user.id)
        .eq('device_id', device.id);

      const autoReconnectUntil = localStorage.getItem('btAutoReconnectUntil');
      if (autoReconnectUntil) {
        const minutesLeft = Math.round((new Date(autoReconnectUntil) - new Date()) / 60000);
        console.log(`Disconnected at ${new Date().toLocaleTimeString()}`);
        console.log(`Auto-reconnect window active for ${minutesLeft} more minutes`);
      }

    } catch (err) {
      console.error('Failed to update device on disconnect:', err);
    }
  };

  /**
   * Check if device requires manual tap to reconnect (after 30-min window expires)
   */
  const checkReconnectStatus = async () => {
    const storedDeviceId = localStorage.getItem('btDeviceId');
    const autoReconnectUntil = localStorage.getItem('btAutoReconnectUntil');

    if (!storedDeviceId) {
      setRequiresTap(false);
      return;
    }

    // Check if auto-reconnect window has expired
    if (autoReconnectUntil) {
      const reconnectExpiry = new Date(autoReconnectUntil);
      if (reconnectExpiry < new Date()) {
        // Window expired - require manual tap to reconnect
        setRequiresTap(true);
        console.log('Auto-reconnect window expired, manual reconnect required');
      } else {
        setRequiresTap(false);
      }
    } else {
      // No auto-reconnect window - require manual tap
      setRequiresTap(true);
    }
  };

  /**
   * Reconnect to device (after 30-minute window expires)
   */
  const handleReconnect = async () => {
    const storedDeviceId = localStorage.getItem('btDeviceId');
    if (!storedDeviceId) {
      setError('No device to reconnect');
      return;
    }

    setIsPairing(true);
    setError(null);

    try {
      // Extend auto-reconnect window by another 30 minutes
      const autoReconnectUntil = new Date();
      autoReconnectUntil.setMinutes(autoReconnectUntil.getMinutes() + 30);
      localStorage.setItem('btAutoReconnectUntil', autoReconnectUntil.toISOString());

      // Try to auto-reconnect
      await attemptAutoReconnect();

      setRequiresTap(false);
      setIsPairing(false);
    } catch (err) {
      console.error('❌ Reconnection error:', err);
      setError(err.message);
      setIsPairing(false);
    }
  };

  /**
   * Disconnect and unpair device
   */
  const handleDisconnect = async () => {
    const storedDeviceId = localStorage.getItem('btDeviceId');
    if (!storedDeviceId) return;

    try {
      // Get user
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        // Mark device as disconnected in bluetooth_devices table
        await supabase
          .from('bluetooth_devices')
          .update({
            status: 'disconnected',
            last_seen: new Date().toISOString()
          })
          .eq('user_id', user.id)
          .eq('device_id', storedDeviceId);

        console.log('✅ Device marked as disconnected');
      }

      // Clear local storage (including auto-reconnect window)
      localStorage.removeItem('btDeviceId');
      localStorage.removeItem('btDeviceName');
      localStorage.removeItem('btAutoReconnectUntil');

      setIsConnected(false);
      setDeviceName(null);
      setDeviceId(null);
      setRequiresTap(false);

      console.log('✅ Device disconnected, auto-reconnect disabled');
    } catch (err) {
      console.error('❌ Disconnect error:', err);
      setError(err.message);
    }
  };

  // Check reconnect status on mount
  useEffect(() => {
    checkReconnectStatus();
    // Check every 30 seconds
    const interval = setInterval(checkReconnectStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  // Not supported
  if (!isSupported) {
    const isNetworkIP = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
    const currentUrl = window.location.origin;

    return (
      <div style={{
        background: 'rgba(239, 68, 68, 0.1)',
        border: '1px solid rgba(239, 68, 68, 0.3)',
        borderRadius: '16px',
        padding: '20px',
        marginBottom: '20px'
      }}>
        <X size={32} color="#ef4444" style={{ marginBottom: '10px', display: 'block', margin: '0 auto 10px' }} />
        <p style={{ color: '#ef4444', fontSize: '16px', fontWeight: '600', margin: '0 0 10px 0' }}>
          Bluetooth Not Available
        </p>

        {error && (
          <p style={{ color: '#ef4444', fontSize: '13px', margin: '0 0 12px 0', fontWeight: '500' }}>
            {error}
          </p>
        )}

        {isNetworkIP ? (
          <>
            <p style={{ color: '#6b7280', fontSize: '14px', margin: '0 0 12px 0' }}>
              Web Bluetooth requires HTTPS or localhost. You're on: <code style={{ color: '#ef4444' }}>{currentUrl}</code>
            </p>
            <p style={{ color: '#6b7280', fontSize: '13px', margin: '0 0 12px 0', textAlign: 'left' }}>
              <strong>Quick Fix (Chrome):</strong>
            </p>
            <ol style={{ color: '#6b7280', fontSize: '12px', textAlign: 'left', paddingLeft: '20px', margin: '0 0 12px 0' }}>
              <li>Go to: <code style={{ background: '#1f2937', padding: '2px 6px', borderRadius: '4px' }}>chrome://flags/#unsafely-treat-insecure-origin-as-secure</code></li>
              <li>Add: <code style={{ background: '#1f2937', padding: '2px 6px', borderRadius: '4px' }}>{currentUrl}</code></li>
              <li>Click "Enabled" and Relaunch Chrome</li>
            </ol>
            <p style={{ color: '#6b7280', fontSize: '12px', margin: 0 }}>
              Or use <code style={{ background: '#1f2937', padding: '2px 6px', borderRadius: '4px' }}>http://localhost:5173</code> instead
            </p>
          </>
        ) : (
          <>
            <p style={{ color: '#6b7280', fontSize: '14px', margin: '0 0 12px 0' }}>
              Please use Chrome, Edge, or Opera browser with Bluetooth support.
            </p>
            {error && error.includes('permission') && (
              <>
                <p style={{ color: '#6b7280', fontSize: '13px', margin: '12px 0', textAlign: 'left' }}>
                  <strong>Fix Bluetooth Permission:</strong>
                </p>
                <ol style={{ color: '#6b7280', fontSize: '12px', textAlign: 'left', paddingLeft: '20px', margin: '0' }}>
                  <li>Go to: <code style={{ background: '#1f2937', padding: '2px 6px', borderRadius: '4px' }}>chrome://settings/content/bluetooth</code></li>
                  <li>Remove this site from "Not allowed to use"</li>
                  <li>Refresh this page and try again</li>
                </ol>
              </>
            )}
          </>
        )}
      </div>
    );
  }

  // Connected state
  if (isConnected) {
    return (
      <div style={{
        background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(16, 185, 129, 0.1) 100%)',
        border: '1px solid rgba(34, 197, 94, 0.3)',
        borderRadius: '16px',
        padding: '20px',
        textAlign: 'center',
        marginBottom: '20px'
      }}>
        <Check size={32} color="#22c55e" style={{ marginBottom: '10px' }} />
        <p style={{ color: '#22c55e', fontSize: '16px', fontWeight: '600', margin: '0 0 8px 0' }}>
          Bluetooth Connected
        </p>
        <p style={{ color: '#6b7280', fontSize: '14px', margin: '0 0 16px 0' }}>
          {deviceName || 'Arduino Nano 33 BLE'}
        </p>
        <p style={{ color: '#6b7280', fontSize: '12px', margin: '0 0 16px 0' }}>
          Your presence is tracked. Use test buttons or NFC tags to vote.
        </p>
        <button
          onClick={handleDisconnect}
          style={{
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '8px',
            padding: '8px 16px',
            color: '#ef4444',
            fontSize: '14px',
            fontWeight: '500',
            cursor: 'pointer'
          }}
        >
          Disconnect
        </button>
      </div>
    );
  }

  // Requires tap to reconnect
  if (requiresTap) {
    return (
      <div style={{
        background: 'rgba(251, 191, 36, 0.1)',
        border: '1px solid rgba(251, 191, 36, 0.3)',
        borderRadius: '16px',
        padding: '20px',
        textAlign: 'center',
        marginBottom: '20px'
      }}>
        <RefreshCw size={32} color="#fbbf24" style={{ marginBottom: '10px' }} />
        <p style={{ color: '#fbbf24', fontSize: '16px', fontWeight: '600', margin: '0 0 8px 0' }}>
          Reconnection Required
        </p>
        <p style={{ color: '#6b7280', fontSize: '14px', margin: '0 0 16px 0' }}>
          Your device has been inactive for 30+ minutes. Tap to reconnect.
        </p>
        <button
          onClick={handleReconnect}
          disabled={isPairing}
          style={{
            background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
            border: 'none',
            borderRadius: '8px',
            padding: '12px 24px',
            color: 'white',
            fontSize: '14px',
            fontWeight: '600',
            cursor: isPairing ? 'not-allowed' : 'pointer',
            opacity: isPairing ? 0.6 : 1
          }}
        >
          {isPairing ? 'Reconnecting...' : 'Reconnect'}
        </button>
      </div>
    );
  }

  // Auto-reconnecting state
  if (isAutoReconnecting) {
    return (
      <div style={{
        background: 'rgba(59, 130, 246, 0.1)',
        border: '1px solid rgba(59, 130, 246, 0.3)',
        borderRadius: '16px',
        padding: '20px',
        textAlign: 'center',
        marginBottom: '20px'
      }}>
        <RefreshCw size={32} color="#3b82f6" style={{ marginBottom: '10px', animation: 'spin 1s linear infinite' }} />
        <p style={{ color: '#3b82f6', fontSize: '16px', fontWeight: '600', margin: '0 0 8px 0' }}>
          Auto-Reconnecting...
        </p>
        <p style={{ color: '#6b7280', fontSize: '14px', margin: '0' }}>
          Reconnecting to paired device
        </p>
      </div>
    );
  }

  // Not connected - show connect button
  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%)',
      border: '1px solid rgba(99, 102, 241, 0.3)',
      borderRadius: '16px',
      padding: '20px',
      textAlign: 'center',
      marginBottom: '20px'
    }}>
      <Bluetooth size={32} color="#6366f1" style={{ marginBottom: '10px' }} />
      <p style={{ color: '#1f2937', fontSize: '16px', fontWeight: '600', margin: '0 0 8px 0' }}>
        Connect Bluetooth Beacon
      </p>
      <p style={{ color: '#6b7280', fontSize: '14px', margin: '0 0 16px 0' }}>
        Pair your Arduino Nano 33 BLE to track your presence in the library
      </p>

      {error && (
        <p style={{ color: '#ef4444', fontSize: '12px', margin: '0 0 12px 0' }}>
          {error}
        </p>
      )}

      <button
        onClick={handleConnect}
        disabled={isPairing}
        style={{
          background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
          border: 'none',
          borderRadius: '8px',
          padding: '12px 24px',
          color: 'white',
          fontSize: '14px',
          fontWeight: '600',
          cursor: isPairing ? 'not-allowed' : 'pointer',
          opacity: isPairing ? 0.6 : 1,
          transition: 'all 0.3s ease'
        }}
      >
        {isPairing ? 'Connecting...' : 'Connect Device'}
      </button>
    </div>
  );
}
