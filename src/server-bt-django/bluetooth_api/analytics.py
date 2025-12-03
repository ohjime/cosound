"""
Analytics module for Bluetooth device tracking
Uses numpy for data processing and matplotlib for visualization
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server-side rendering
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from io import BytesIO
import base64
from typing import Dict
from .services import get_all_devices, get_sessions_in_range


def calculate_device_statistics() -> Dict:
    """
    Calculate statistics using numpy for efficient computation
    
    Returns:
        Dictionary with various statistics about devices and sessions
    """
    devices = get_all_devices()
    
    if not devices or not devices.data:
        return {
            'total_devices': 0,
            'connected_count': 0,
            'disconnected_count': 0,
            'grace_period_count': 0,
            'average_rssi': None,
            'rssi_std': None,
            'status_distribution': {}
        }
    
    # Extract data for numpy processing
    statuses = [d['status'] for d in devices.data]
    rssi_values = [d['rssi'] for d in devices.data if d.get('rssi') is not None]
    
    # Calculate RSSI statistics using numpy
    rssi_array = np.array(rssi_values) if rssi_values else np.array([])
    
    stats = {
        'total_devices': len(devices.data),
        'connected_count': statuses.count('connected'),
        'disconnected_count': statuses.count('disconnected'),
        'grace_period_count': statuses.count('grace_period'),
        'average_rssi': float(np.mean(rssi_array)) if len(rssi_array) > 0 else None,
        'rssi_std': float(np.std(rssi_array)) if len(rssi_array) > 0 else None,
        'rssi_min': float(np.min(rssi_array)) if len(rssi_array) > 0 else None,
        'rssi_max': float(np.max(rssi_array)) if len(rssi_array) > 0 else None,
        'status_distribution': {
            'connected': statuses.count('connected'),
            'disconnected': statuses.count('disconnected'),
            'grace_period': statuses.count('grace_period')
        }
    }
    
    return stats


def generate_status_pie_chart() -> str:
    """
    Generate a pie chart of device status distribution
    
    Returns:
        Base64 encoded PNG image
    """
    devices = get_all_devices()
    
    if not devices or not devices.data:
        plt.figure(figsize=(8, 8))
        plt.text(0.5, 0.5, 'No device data available', 
                ha='center', va='center', fontsize=14)
        plt.axis('off')
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{image_base64}"
    
    statuses = [d['status'] for d in devices.data]
    status_counts = {
        'Connected': statuses.count('connected'),
        'Disconnected': statuses.count('disconnected'),
        'Grace Period': statuses.count('grace_period')
    }
    
    # Filter out zero values
    filtered_data = {k: v for k, v in status_counts.items() if v > 0}
    
    if not filtered_data:
        plt.figure(figsize=(8, 8))
        plt.text(0.5, 0.5, 'No status data available', 
                ha='center', va='center', fontsize=14)
        plt.axis('off')
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{image_base64}"
    
    colors = {
        'Connected': '#00C49F',
        'Disconnected': '#FF8042',
        'Grace Period': '#FFBB28'
    }
    
    labels = list(filtered_data.keys())
    sizes = list(filtered_data.values())
    chart_colors = [colors[label] for label in labels]
    
    # Create pie chart
    plt.figure(figsize=(8, 8))
    plt.pie(sizes, labels=labels, colors=chart_colors, autopct='%1.1f%%',
            startangle=90, textprops={'fontsize': 12})
    plt.title('Device Status Distribution', fontsize=14, fontweight='bold', pad=20)
    plt.axis('equal')
    
    # Convert to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    plt.close()
    
    return f"data:image/png;base64,{image_base64}"


def generate_session_durations_chart(limit: int = 10) -> str:
    """
    Generate a horizontal bar chart showing individual session durations
    
    Args:
        limit: Number of recent sessions to show
        
    Returns:
        Base64 encoded PNG image
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    sessions_result = get_sessions_in_range(start_date, end_date)
    sessions = sessions_result.data if sessions_result and sessions_result.data else []
    
    if not sessions:
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, 'No session data available', 
                ha='center', va='center', fontsize=14, color='#666')
        plt.axis('off')
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, facecolor='white')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{image_base64}"
    
    # Get recent sessions and calculate durations
    session_data = []
    current_time = datetime.now()
    
    for session in sessions[:limit]:
        device_name = session.get('device_name', 'Unknown')[:15]  # Truncate long names
        
        # Parse connected_at
        connected_str = session['connected_at']
        if 'Z' in connected_str:
            connected_at = datetime.fromisoformat(connected_str.replace('Z', '+00:00'))
        elif '+' in connected_str:
            connected_at = datetime.fromisoformat(connected_str)
        else:
            connected_at = datetime.fromisoformat(connected_str)
        
        if connected_at.tzinfo:
            connected_at = connected_at.replace(tzinfo=None)
        
        # Calculate duration
        if session.get('disconnected_at'):
            disconnected_str = session['disconnected_at']
            if 'Z' in disconnected_str:
                disconnected_at = datetime.fromisoformat(disconnected_str.replace('Z', '+00:00'))
            elif '+' in disconnected_str:
                disconnected_at = datetime.fromisoformat(disconnected_str)
            else:
                disconnected_at = datetime.fromisoformat(disconnected_str)
            
            if disconnected_at.tzinfo:
                disconnected_at = disconnected_at.replace(tzinfo=None)
            
            duration_minutes = (disconnected_at - connected_at).total_seconds() / 60
            status = 'Ended'
        else:
            duration_minutes = (current_time - connected_at).total_seconds() / 60
            status = 'Active'
        
        session_data.append({
            'device': device_name,
            'duration': duration_minutes,
            'status': status,
            'time': connected_at.strftime('%m/%d %H:%M')
        })
    
    if not session_data:
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, 'No session data available', 
                ha='center', va='center', fontsize=14, color='#666')
        plt.axis('off')
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, facecolor='white')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{image_base64}"
    
    # Prepare data for plotting
    labels = [f"{s['device']}\n{s['time']}" for s in session_data]
    durations = [s['duration'] for s in session_data]
    colors = ['#00C49F' if s['status'] == 'Active' else '#8B5CF6' for s in session_data]
    
    # Create horizontal bar chart
    fig, ax = plt.subplots(figsize=(10, max(6, len(session_data) * 0.6)))
    y_pos = np.arange(len(session_data))
    
    bars = ax.barh(y_pos, durations, color=colors, alpha=0.85, edgecolor='white', linewidth=2)
    
    # Customize
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel('Duration (minutes)', fontsize=12, fontweight='bold')
    ax.set_title(f'Recent Session Durations (Last {limit})', fontsize=14, fontweight='bold', pad=20)
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_facecolor('#f8f9fa')
    
    # Add value labels
    for i, (bar, duration) in enumerate(zip(bars, durations)):
        width = bar.get_width()
        ax.text(width + max(durations) * 0.02, bar.get_y() + bar.get_height()/2,
                f'{duration:.1f} min', ha='left', va='center', fontsize=9, fontweight='bold')
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#00C49F', label='Active Sessions'),
        Patch(facecolor='#8B5CF6', label='Ended Sessions')
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=10)
    
    plt.tight_layout()
    
    # Convert to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=120, bbox_inches='tight', facecolor='white')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    plt.close()
    
    return f"data:image/png;base64,{image_base64}"
