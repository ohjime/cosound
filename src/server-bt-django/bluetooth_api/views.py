"""
API views for Bluetooth Presence Detection backend.
"""

import logging
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .middleware import jwt_required, scanner_api_key_required
from .services import get_supabase_service
from . import analytics

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def health(request):
    """
    Health check endpoint.
    No authentication required.
    """
    return JsonResponse({
        'status': 'ok',
        'service': 'bluetooth-presence-django',
        'version': '1.0.0'
    })


@csrf_exempt
@require_http_methods(["POST"])
def register_device(request):
    """
    Register a new device for the authenticated user.
    First-time setup only.

    Headers:
        Authorization: Bearer {jwt_token} (optional for POC)

    Body:
        {
            "user_id": "uuid" (required if no JWT),
            "device_mac": "AA:BB:CC:DD:EE:FF",
            "device_name": "My Laptop" (optional)
        }

    Returns:
        {
            "success": true,
            "device_id": "uuid",
            "session_id": "uuid",
            "message": "Device registered and session started"
        }
    """
    try:
        # Parse request body
        body = json.loads(request.body.decode('utf-8'))
        device_mac = body.get('device_mac')
        device_name = body.get('device_name', 'Unknown Device')

        # Get user_id from JWT or request body (POC fallback)
        user_id = getattr(request, 'user_id', None) or body.get('user_id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'user_id is required (in body or JWT)'
            }, status=400)

        # Validate device_mac
        if not device_mac:
            return JsonResponse({
                'success': False,
                'error': 'device_mac is required'
            }, status=400)

        # Validate MAC address format (basic check)
        if (':' not in device_mac and '-' not in device_mac) or len(device_mac) != 17:
            return JsonResponse({
                'success': False,
                'error': 'Invalid MAC address format. Expected: AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF'
            }, status=400)

        # Normalize MAC to uppercase with colons
        device_mac = device_mac.upper().replace('-', ':')

        # Register device
        service = get_supabase_service()
        result = service.register_device(
            user_id=user_id,
            device_mac=device_mac,
            device_name=device_name
        )

        logger.info(f"Device registered for user {user_id}: {device_mac}")

        return JsonResponse({
            'success': True,
            'device_id': result['device_id'],
            'session_id': result['session_id'],
            'message': 'Device registered and session started'
        })

    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)

    except Exception as e:
        logger.error(f"Error in register_device: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def check_in(request):
    """
    Check in the authenticated user (start new session).
    For users who already have a registered device.

    Headers:
        Authorization: Bearer {jwt_token} (optional for POC)

    Body:
        {
            "user_id": "uuid" (required if no JWT)
        }

    Returns:
        {
            "success": true,
            "session_id": "uuid",
            "message": "Checked in, session started"
        }
    """
    try:
        # Parse request body
        body = json.loads(request.body.decode('utf-8')) if request.body else {}

        # Get user_id from JWT or request body (POC fallback)
        user_id = getattr(request, 'user_id', None) or body.get('user_id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'user_id is required (in body or JWT)'
            }, status=400)

        service = get_supabase_service()
        result = service.check_in(user_id=user_id)

        logger.info(f"User {user_id} checked in")

        return JsonResponse({
            'success': True,
            'session_id': result['session_id'],
            'device_mac': result['device']['device_mac'],
            'message': 'Checked in, session started'
        })

    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

    except Exception as e:
        logger.error(f"Error in check_in: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def device_detected(request):
    """
    Report device detection from Raspberry Pi scanner.
    Updates last_seen timestamp for registered devices.
    """
    try:
        # Parse request body
        body = json.loads(request.body.decode('utf-8'))
        device_mac = body.get('device_mac')
        device_name = body.get('device_name', 'Unknown')
        rssi = body.get('rssi')

        if not device_mac:
            return JsonResponse({
                'success': False,
                'error': 'device_mac is required'
            }, status=400)

        # Log detection
        logger.info(f"✅ DETECTED: {device_mac} ({device_name}) RSSI: {rssi}")

        # Update database for registered devices
        service = get_supabase_service()
        result = service.update_device_detected(device_mac=device_mac, rssi=rssi)

        return JsonResponse({
            'success': True,
            'action': result.get('action', 'unknown'),
            'previous_status': result.get('previous_status')
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)

    except Exception as e:
        logger.error(f"Error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def nfc_tap(request):
    """
    Called when user taps NFC tag and browser loads.
    Sets tap = true in device record to enable next session creation.

    Body:
        {
            "user_id": "uuid"
        }

    Returns:
        {
            "success": true,
            "message": "Tap registered, ready to detect device"
        }
    """
    try:
        body = json.loads(request.body)
        user_id = body.get('user_id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'user_id is required'
            }, status=400)

        service = get_supabase_service()
        
        # Find user's device
        device_result = service.client.table('test_bt_devices')\
            .select('*')\
            .eq('user_id', user_id)\
            .execute()

        if not device_result.data:
            return JsonResponse({
                'success': False,
                'error': 'Device not registered for this user'
            }, status=404)

        device = device_result.data[0]

        # Set tap = true
        from datetime import datetime
        service.client.table('test_bt_devices')\
            .update({
                'tap': True,
                'updated_at': datetime.utcnow().isoformat()
            })\
            .eq('id', device['id'])\
            .execute()

        logger.info(f"NFC tap registered for user {user_id}, device {device['device_mac']}")

        return JsonResponse({
            'success': True,
            'message': 'Tap registered, ready to detect device',
            'device_mac': device['device_mac']
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in nfc_tap: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def my_status(request):
    """
    Get current user's device registration and connection status.

    Headers:
        Authorization: Bearer {jwt_token} (optional for POC)

    Query Params:
        user_id: uuid (required if no JWT)

    Returns:
        {
            "success": true,
            "has_device": true,
            "device_mac": "AA:BB:CC:DD:EE:FF",
            "device_name": "My Laptop",
            "status": "connected|grace_period|disconnected",
            "last_seen": "2025-12-03T10:30:00Z",
            "grace_period_ends_at": "2025-12-03T10:45:00Z" (if in grace period),
            "tap": false
        }
    """
    try:
        # Get user_id from JWT or query params (POC fallback)
        user_id = getattr(request, 'user_id', None) or request.GET.get('user_id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'user_id is required (in query param or JWT)'
            }, status=400)

        service = get_supabase_service()
        status = service.get_user_status(user_id=user_id)

        return JsonResponse({
            'success': True,
            **status
        })

    except Exception as e:
        logger.error(f"Error in my_status: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def analytics_stats(request):
    """
    Get device and session statistics using numpy calculations.
    
    Returns:
        {
            "success": true,
            "stats": {
                "total_devices": 5,
                "connected_count": 2,
                "disconnected_count": 1,
                "grace_period_count": 2,
                "average_rssi": -65.5,
                "rssi_std": 12.3,
                "rssi_min": -85,
                "rssi_max": -45,
                "status_distribution": {...}
            }
        }
    """
    try:
        stats = analytics.calculate_device_statistics()
        
        return JsonResponse({
            'success': True,
            'stats': stats
        })
    
    except Exception as e:
        logger.error(f"Error in analytics_stats: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def analytics_charts(request):
    """
    Generate all analytics charts using matplotlib.
    Returns base64-encoded PNG images.
    
    Query Params:
        days: Number of days for weekly chart (default: 7)
        session_limit: Number of sessions for duration chart (default: 20)
    
    Returns:
        {
            "success": true,
            "charts": {
                "weekly_sessions": "data:image/png;base64,...",
                "rssi_distribution": "data:image/png;base64,...",
                "session_durations": "data:image/png;base64,...",
                "status_pie": "data:image/png;base64,..."
            }
        }
    """
    try:
        days = int(request.GET.get('days', 7))
        session_limit = int(request.GET.get('session_limit', 20))
        
        charts = {
            'weekly_sessions': analytics.generate_weekly_session_chart(days=days),
            'rssi_distribution': analytics.generate_rssi_distribution_chart(),
            'session_durations': analytics.generate_session_duration_chart(limit=session_limit),
            'status_pie': analytics.generate_status_pie_chart()
        }
        
        return JsonResponse({
            'success': True,
            'charts': charts
        })
    
    except Exception as e:
        logger.error(f"Error in analytics_charts: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def analytics_chart(request, chart_type):
    """
    Generate a single analytics chart using matplotlib.
    
    Path Params:
        chart_type: weekly|rssi|duration|status
        
    Query Params:
        days: For weekly chart (default: 7)
        limit: For duration chart (default: 20)
    
    Returns:
        {
            "success": true,
            "chart": "data:image/png;base64,..."
        }
    """
    try:
        if chart_type == 'weekly':
            days = int(request.GET.get('days', 7))
            chart = analytics.generate_weekly_session_chart(days=days)
        elif chart_type == 'rssi':
            chart = analytics.generate_rssi_distribution_chart()
        elif chart_type == 'duration':
            limit = int(request.GET.get('limit', 20))
            chart = analytics.generate_session_duration_chart(limit=limit)
        elif chart_type == 'status':
            chart = analytics.generate_status_pie_chart()
        else:
            return JsonResponse({
                'success': False,
                'error': f'Unknown chart type: {chart_type}. Valid types: weekly, rssi, duration, status'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'chart': chart,
            'type': chart_type
        })
    
    except Exception as e:
        logger.error(f"Error in analytics_chart: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)
