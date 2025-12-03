"""
Supabase service layer for Bluetooth Presence Detection.
Handles all database operations with test_bt_devices and test_bt_sessions tables.
"""

import logging
from datetime import datetime, timedelta
from django.conf import settings
from postgrest import SyncPostgrestClient
import os

logger = logging.getLogger(__name__)

class SupabaseService:
    """Service class for Supabase database operations."""

    def __init__(self):
        """Initialize Postgrest client directly without websockets."""
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")

        try:
            # Use Postgrest directly - no realtime/websockets needed
            base_url = settings.SUPABASE_URL.rstrip('/')
            rest_url = f"{base_url}/rest/v1"
            
            self.client = SyncPostgrestClient(
                base_url=rest_url,
                headers={
                    "apikey": settings.SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"
                }
            )
        except Exception as e:
            logger.error(f"Failed to initialize Postgrest client: {e}")
            raiser.error(f"Failed to initialize Supabase client: {e}")
            raise

    def register_device(self, user_id: str, device_mac: str, device_name: str = None):
        """
        Register or update a device for a user.
        If user already has a device, updates the MAC and name.
        If new user, creates new device record.

        Args:
            user_id: Supabase user ID
            device_mac: Bluetooth MAC address
            device_name: Optional device name

        Returns:
            dict: Device record with device_id, session_id, and action taken

        Raises:
            Exception: If database error
        """
        try:
            # Check if user already has a device registered
            existing = self.client.table('test_bt_devices')\
                .select('*')\
                .eq('user_id', user_id)\
                .execute()

            if existing.data:
                # User already has device - UPDATE it with new MAC/name
                device = existing.data[0]
                logger.info(f"User {user_id} already has device - updating MAC to {device_mac}")
                
                update_data = {
                    'device_mac': device_mac,
                    'device_name': device_name or device.get('device_name') or 'Unknown Device',
                    'status': 'connected',
                    'last_seen': datetime.utcnow().isoformat(),
                    'grace_period_ends_at': None,
                    'updated_at': datetime.utcnow().isoformat()
                }

                device_result = self.client.table('test_bt_devices')\
                    .update(update_data)\
                    .eq('id', device['id'])\
                    .execute()

                device_id = device['id']
                action = 'updated'
                logger.info(f"Device updated: {device_id} with new MAC {device_mac}")

            else:
                # Check if MAC address is already used by another user
                mac_check = self.client.table('test_bt_devices')\
                    .select('*')\
                    .eq('device_mac', device_mac)\
                    .execute()

                if mac_check.data:
                    logger.warning(f"MAC {device_mac} already registered to another user")
                    raise ValueError("This device MAC is already registered to another user")

                # Create NEW device record
                device_data = {
                    'user_id': user_id,
                    'device_mac': device_mac,
                    'device_name': device_name or 'Unknown Device',
                    'status': 'connected',
                    'last_seen': datetime.utcnow().isoformat(),
                    'grace_period_ends_at': None,
                    'rssi': None
                }

                device_result = self.client.table('test_bt_devices')\
                    .insert(device_data)\
                    .execute()

                if not device_result.data:
                    raise Exception("Failed to create device record")

                device_id = device_result.data[0]['id']
                action = 'created'
                logger.info(f"Device created: {device_id} for user {user_id}")

            # Create initial session
            session_id = self.create_session(user_id, device_mac, device_name)

            return {
                'device_id': device_id,
                'session_id': session_id,
                'action': action,
                'device': device_result.data[0] if device_result.data else existing.data[0]
            }

        except ValueError as e:
            raise e
        except Exception as e:
            logger.error(f"Error registering device: {e}")
            raise Exception(f"Failed to register device: {str(e)}")

    def create_session(self, user_id: str, device_mac: str, device_name: str = None):
        """
        Create a new active session for a user.

        Args:
            user_id: Supabase user ID
            device_mac: Bluetooth MAC address
            device_name: Optional device name

        Returns:
            str: Session ID
        """
        try:
            session_data = {
                'user_id': user_id,
                'device_mac': device_mac,
                'device_name': device_name,
                'connected_at': datetime.utcnow().isoformat(),
                'status': 'active'
            }

            result = self.client.table('test_bt_sessions')\
                .insert(session_data)\
                .execute()

            if not result.data:
                raise Exception("Failed to create session")

            session_id = result.data[0]['id']
            logger.info(f"Session created: {session_id} for user {user_id}")

            return session_id

        except Exception as e:
            logger.error(f"Error creating session: {e}")
            raise Exception(f"Failed to create session: {str(e)}")

    def check_in(self, user_id: str):
        """
        Check in a user (start new session for registered device).

        Args:
            user_id: Supabase user ID

        Returns:
            dict: Session info with session_id and device

        Raises:
            Exception: If device not registered or database error
        """
        try:
            # Get user's registered device
            device_result = self.client.table('test_bt_devices')\
                .select('*')\
                .eq('user_id', user_id)\
                .execute()

            if not device_result.data:
                logger.warning(f"No device registered for user {user_id}")
                raise ValueError("Device not registered. Please register first.")

            device = device_result.data[0]

            # Update device status
            update_data = {
                'status': 'connected',
                'last_seen': datetime.utcnow().isoformat(),
                'grace_period_ends_at': None,
                'updated_at': datetime.utcnow().isoformat()
            }

            self.client.table('test_bt_devices')\
                .update(update_data)\
                .eq('id', device['id'])\
                .execute()

            # Create new session
            session_id = self.create_session(
                user_id,
                device['device_mac'],
                device.get('device_name')
            )

            logger.info(f"User {user_id} checked in, session {session_id}")

            return {
                'session_id': session_id,
                'device': device
            }

        except ValueError as e:
            raise e
        except Exception as e:
            logger.error(f"Error during check-in: {e}")
            raise Exception(f"Failed to check in: {str(e)}")

    def update_device_detected(self, device_mac: str, rssi: int = None):
        """
        Update device last_seen timestamp when detected by scanner.

        Args:
            device_mac: Bluetooth MAC address
            rssi: Signal strength

        Returns:
            dict: Updated device and action taken
        """
        try:
            # Find device by MAC
            device_result = self.client.table('test_bt_devices')\
                .select('*')\
                .eq('device_mac', device_mac)\
                .execute()

            if not device_result.data:
                # Device not registered - ignore
                logger.debug(f"Unregistered device detected: {device_mac}")
                return {'action': 'ignored', 'reason': 'not_registered'}

            device = device_result.data[0]
            current_status = device['status']

            # Update last_seen and rssi
            update_data = {
                'last_seen': datetime.utcnow().isoformat(),
                'rssi': rssi,
                'updated_at': datetime.utcnow().isoformat()
            }

            # Handle status transitions
            action = 'updated'
            create_new_session = False

            if current_status == 'grace_period':
                # Device returned during grace period - restore connection
                update_data['status'] = 'connected'
                update_data['grace_period_ends_at'] = None
                action = 'restored'
                logger.info(f"Device {device_mac} restored from grace period")

            elif current_status == 'disconnected':
                # Device came back in range - reconnect and create new session
                update_data['status'] = 'connected'
                action = 'connected'
                create_new_session = True
                logger.info(f"Device {device_mac} reconnected")

            # Apply update
            self.client.table('test_bt_devices')\
                .update(update_data)\
                .eq('id', device['id'])\
                .execute()

            # Create new session if needed
            session_id = None
            if create_new_session:
                session_id = self.create_session(
                    device['user_id'],
                    device_mac,
                    device.get('device_name')
                )

            return {
                'action': action,
                'device': device,
                'previous_status': current_status,
                'session_id': session_id
            }

        except Exception as e:
            logger.error(f"Error updating device detection: {e}")
            return {'action': 'error', 'error': str(e)}

    def get_user_status(self, user_id: str):
        """
        Get user's device registration and connection status.

        Args:
            user_id: Supabase user ID

        Returns:
            dict: Status info with has_device, status, last_seen, etc.
        """
        try:
            device_result = self.client.table('test_bt_devices')\
                .select('*')\
                .eq('user_id', user_id)\
                .execute()

            if not device_result.data:
                return {
                    'has_device': False,
                    'status': None
                }

            device = device_result.data[0]

            return {
                'has_device': True,
                'device_mac': device['device_mac'],
                'device_name': device.get('device_name'),
                'status': device['status'],
                'last_seen': device.get('last_seen'),
                'grace_period_ends_at': device.get('grace_period_ends_at'),
                'rssi': device.get('rssi')
            }

        except Exception as e:
            logger.error(f"Error getting user status: {e}")
            raise Exception(f"Failed to get status: {str(e)}")

    def cleanup_expired_grace_periods(self):
        """
        Background task: Check for expired grace periods and end sessions.
        Called by APScheduler every 30 seconds.
        """
        try:
            now = datetime.utcnow()
            timeout_threshold = now - timedelta(seconds=settings.DETECTION_TIMEOUT_SECONDS)

            # 1. Find devices that need to enter grace period
            # (connected but not detected for > 30 seconds)
            devices_to_grace = self.client.table('test_bt_devices')\
                .select('*')\
                .eq('status', 'connected')\
                .lt('last_seen', timeout_threshold.isoformat())\
                .execute()

            for device in devices_to_grace.data:
                grace_end = now + timedelta(minutes=settings.GRACE_PERIOD_MINUTES)
                self.client.table('test_bt_devices')\
                    .update({
                        'status': 'grace_period',
                        'grace_period_ends_at': grace_end.isoformat(),
                        'updated_at': now.isoformat()
                    })\
                    .eq('id', device['id'])\
                    .execute()

                logger.info(f"Device {device['device_mac']} entered grace period")

            # 2. Find devices with expired grace periods
            expired_devices = self.client.table('test_bt_devices')\
                .select('*')\
                .eq('status', 'grace_period')\
                .lt('grace_period_ends_at', now.isoformat())\
                .execute()

            for device in expired_devices.data:
                # Update device status to disconnected
                self.client.table('test_bt_devices')\
                    .update({
                        'status': 'disconnected',
                        'grace_period_ends_at': None,
                        'updated_at': now.isoformat()
                    })\
                    .eq('id', device['id'])\
                    .execute()

                # End active session
                active_sessions = self.client.table('test_bt_sessions')\
                    .select('*')\
                    .eq('user_id', device['user_id'])\
                    .eq('status', 'active')\
                    .execute()

                for session in active_sessions.data:
                    connected_at = datetime.fromisoformat(session['connected_at'].replace('Z', '+00:00'))
                    duration_minutes = int((now - connected_at).total_seconds() / 60)

                    self.client.table('test_bt_sessions')\
                        .update({
                            'status': 'ended',
                            'disconnected_at': now.isoformat(),
                        })\
                        .eq('id', session['id'])\
                        .execute()

                    logger.info(f"Session {session['id']} ended after {duration_minutes} minutes")

                logger.info(f"Device {device['device_mac']} disconnected after grace period")

        except Exception as e:
            logger.error(f"Error in grace period cleanup: {e}")


# Singleton instance
_supabase_service = None


def get_supabase_service():
    """Get singleton Supabase service instance."""
    global _supabase_service
    if _supabase_service is None:
        _supabase_service = SupabaseService()
    return _supabase_service
