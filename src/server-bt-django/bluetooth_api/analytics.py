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
from typing import Dict, List, Tuple
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


def generate_weekly_session_chart(days: int = 7) -> str:
    """
    Generate a bar chart of sessions per day using matplotlib
    
    Args:
        days: Number of days to include in chart
        
    Returns:
        Base64 encoded PNG image
    """
    # Get sessions from last N days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    sessions_result = get_sessions_in_range(start_date, end_date)
    sessions = sessions_result.data if sessions_result and sessions_result.data else []
    
    # Initialize daily counts
    daily_counts = np.zeros(days)
    date_labels = []
    
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_labels.append(date.strftime('%m/%d'))
    
    # Count sessions per day
    for session in sessions:
        connected_at = datetime.fromisoformat(session['connected_at'].replace('Z', '+00:00'))
        days_diff = (connected_at.date() - start_date.date()).days
        if 0 <= days_diff < days:
            daily_counts[days_diff] += 1
    
    # Create the plot
    plt.figure(figsize=(10, 6))
    plt.bar(range(days), daily_counts, color='#8B5CF6', alpha=0.8)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Number of Sessions', fontsize=12)
    plt.title(f'Daily Sessions (Last {days} Days)', fontsize=14, fontweight='bold')
    plt.xticks(range(days), date_labels, rotation=45)
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    
    # Convert to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    plt.close()
    
    return f"data:image/png;base64,{image_base64}"


def generate_rssi_distribution_chart() -> str:
    """
    Generate a histogram of RSSI values using matplotlib
    
    Returns:
        Base64 encoded PNG image
    """
    devices = get_all_devices()
    
    if not devices or not devices.data:
        # Return empty chart
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, 'No RSSI data available', 
                ha='center', va='center', fontsize=14)
        plt.axis('off')
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{image_base64}"
    
    # Extract RSSI values
    rssi_values = [d['rssi'] for d in devices.data if d.get('rssi') is not None]
    
    if not rssi_values:
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, 'No RSSI data available', 
                ha='center', va='center', fontsize=14)
        plt.axis('off')
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{image_base64}"
    
    rssi_array = np.array(rssi_values)
    
    # Create histogram
    plt.figure(figsize=(10, 6))
    plt.hist(rssi_array, bins=20, color='#00C49F', alpha=0.8, edgecolor='black')
    plt.xlabel('RSSI (dBm)', fontsize=12)
    plt.ylabel('Frequency', fontsize=12)
    plt.title('RSSI Distribution', fontsize=14, fontweight='bold')
    plt.grid(axis='y', alpha=0.3)
    
    # Add statistics to plot
    mean_rssi = np.mean(rssi_array)
    std_rssi = np.std(rssi_array)
    plt.axvline(mean_rssi, color='red', linestyle='--', linewidth=2, 
                label=f'Mean: {mean_rssi:.1f} dBm')
    plt.legend()
    plt.tight_layout()
    
    # Convert to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    plt.close()
    
    return f"data:image/png;base64,{image_base64}"


def generate_session_duration_chart(limit: int = 20) -> str:
    """
    Generate a horizontal bar chart of session durations grouped by device
    
    Args:
        limit: Number of recent sessions to include
        
    Returns:
        Base64 encoded PNG image
    """
    # Get recent sessions
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
    
    # Group sessions by device and calculate total duration per device
    device_durations = {}
    device_session_counts = {}
    current_time = datetime.now()
    
    for session in sessions:
        device_name = session.get('device_name', 'Unknown Device')
        
        # Parse connected_at timestamp
        connected_str = session['connected_at']
        if 'Z' in connected_str:
            connected_at = datetime.fromisoformat(connected_str.replace('Z', '+00:00'))
        elif '+' in connected_str or connected_str.endswith('00:00'):
            connected_at = datetime.fromisoformat(connected_str)
        else:
            # No timezone, treat as UTC
            connected_at = datetime.fromisoformat(connected_str)
        
        # Remove timezone for calculation
        if connected_at.tzinfo:
            connected_at = connected_at.replace(tzinfo=None)
        
        if session.get('disconnected_at'):
            # Ended session
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
        else:
            # Active session - calculate current duration
            duration_minutes = (current_time - connected_at).total_seconds() / 60
        
        if device_name not in device_durations:
            device_durations[device_name] = 0
            device_session_counts[device_name] = 0
        
        device_durations[device_name] += duration_minutes
        device_session_counts[device_name] += 1
    
    # Sort by total duration
    sorted_devices = sorted(device_durations.items(), key=lambda x: x[1], reverse=True)
    
    if not sorted_devices:
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, 'No duration data available', 
                ha='center', va='center', fontsize=14, color='#666')
        plt.axis('off')
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, facecolor='white')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close()
        return f"data:image/png;base64,{image_base64}"
    
    devices = [d[0][:20] for d in sorted_devices]  # Truncate long names
    durations = [d[1] for d in sorted_devices]
    
    # Convert to hours if durations are large
    if max(durations) > 120:
        durations = [d / 60 for d in durations]
        duration_label = 'Duration (hours)'
    else:
        duration_label = 'Duration (minutes)'
    
    # Create gradient colors based on duration
    max_duration = max(durations)
    colors = []
    for duration in durations:
        ratio = duration / max_duration if max_duration > 0 else 0
        if ratio > 0.7:
            colors.append('#00C49F')  # Green for long sessions
        elif ratio > 0.4:
            colors.append('#FFBB28')  # Yellow for medium sessions
        else:
            colors.append('#8B5CF6')  # Purple for short sessions
    
    # Create horizontal bar chart
    fig, ax = plt.subplots(figsize=(10, max(6, len(devices) * 0.5)))
    y_pos = np.arange(len(devices))
    
    bars = ax.barh(y_pos, durations, color=colors, alpha=0.85, edgecolor='white', linewidth=2)
    
    # Customize the plot
    ax.set_yticks(y_pos)
    ax.set_yticklabels(devices, fontsize=11)
    ax.set_xlabel(duration_label, fontsize=12, fontweight='bold')
    ax.set_title('Total Session Duration by Device', fontsize=14, fontweight='bold', pad=20)
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_facecolor('#f8f9fa')
    
    # Add value labels on bars
    for i, (bar, duration) in enumerate(zip(bars, durations)):
        width = bar.get_width()
        sessions_count = device_session_counts[sorted_devices[i][0]]
        label_text = f'{duration:.1f} ({sessions_count} sessions)'
        ax.text(width + max(durations) * 0.02, bar.get_y() + bar.get_height()/2,
                label_text, ha='left', va='center', fontsize=9, fontweight='bold')
    
    # Add a legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#00C49F', label='Long Duration'),
        Patch(facecolor='#FFBB28', label='Medium Duration'),
        Patch(facecolor='#8B5CF6', label='Short Duration')
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
