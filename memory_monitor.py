import psutil
import time
import os

def get_process_memory(pid):
    """Get memory usage in MB for a specific process"""
    try:
        process = psutil.Process(pid)
        return process.memory_info().rss / 1024 / 1024
    except psutil.NoSuchProcess:
        return None

def find_python_processes():
    """Find all Python processes with their command lines"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'python.exe' or proc.info['name'] == 'python':
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'cmdline': cmdline,
                    'memory_mb': get_process_memory(proc.info['pid'])
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes

def monitor_specific_process(name_filter, duration_seconds=30):
    """Monitor memory of processes matching a name filter"""
    print(f"\n=== Monitoring processes containing: {name_filter} ===")
    print(f"Duration: {duration_seconds} seconds")
    print("Time (s) | PID | Memory (MB) | Command")
    print("-" * 80)
    
    start_time = time.time()
    peak_memory = {}
    
    while time.time() - start_time < duration_seconds:
        current_time = time.time() - start_time
        processes = find_python_processes()
        
        for proc in processes:
            if name_filter.lower() in proc['cmdline'].lower():
                pid = proc['pid']
                memory = proc['memory_mb']
                
                if memory:
                    if pid not in peak_memory or memory > peak_memory[pid]:
                        peak_memory[pid] = memory
                    
                    print(f"{current_time:8.1f} | {pid:4d} | {memory:10.1f} | {proc['cmdline'][:50]}")
        
        time.sleep(1)
    
    print("\n=== Peak Memory Summary ===")
    for pid, peak in peak_memory.items():
        print(f"PID {pid}: {peak:.1f} MB (peak)")
    
    return peak_memory

def list_all_python_processes():
    """List all Python processes with memory usage"""
    print("\n=== All Python Processes ===")
    print("PID | Memory (MB) | Command")
    print("-" * 80)
    
    processes = find_python_processes()
    for proc in processes:
        print(f"{proc['pid']:4d} | {proc['memory_mb']:10.1f} | {proc['cmdline'][:60]}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "list":
            list_all_python_processes()
        elif command == "monitor":
            name_filter = sys.argv[2] if len(sys.argv) > 2 else "manage.py"
            duration = int(sys.argv[3]) if len(sys.argv) > 3 else 30
            monitor_specific_process(name_filter, duration)
        else:
            print("Usage:")
            print("  python memory_monitor.py list                    # List all Python processes")
            print("  python memory_monitor.py monitor <filter> <secs> # Monitor specific processes")
    else:
        list_all_python_processes()
