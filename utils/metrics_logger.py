"""
Metrics logging module for hosting and performance monitoring.
Tracks key metrics for understanding application usage, performance, and resource requirements.
"""
import logging
import time
import traceback
import psutil
import os
from pathlib import Path
from datetime import datetime
from functools import wraps

# Set up dedicated metrics logger
metrics_logger = logging.getLogger('metrics')
metrics_logger.setLevel(logging.INFO)

# Create metrics log file handler
metrics_log_path = Path.cwd() / 'metrics.log'
try:
    metrics_handler = logging.FileHandler(metrics_log_path, 'a')  # Append mode
    metrics_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    metrics_handler.setFormatter(metrics_formatter)
    metrics_logger.addHandler(metrics_handler)
except Exception as e:
    print(f"Warning: Failed to configure metrics logging: {e}")

# Also log to console for development
console_handler = logging.StreamHandler()
console_handler.setFormatter(metrics_formatter)
metrics_logger.addHandler(console_handler)


class MetricsCollector:
    """Collects and logs hosting metrics for the application."""
    
    @staticmethod
    def log_session_start():
        """Log when a new session starts."""
        try:
            process = psutil.Process(os.getpid())
            metrics_logger.info(
                f"SESSION_START | PID={os.getpid()} | "
                f"Memory={process.memory_info().rss / 1024 / 1024:.2f}MB | "
                f"CPU={psutil.cpu_percent()}%"
            )
        except Exception as e:
            metrics_logger.error(f"SESSION_START | Error: {e}")
    
    @staticmethod
    def log_page_navigation(page_name):
        """Log page navigation events."""
        metrics_logger.info(f"PAGE_NAVIGATION | Page={page_name}")
    
    @staticmethod
    def log_file_upload(file_name, file_size_bytes, file_type):
        """Log file upload metrics."""
        size_mb = file_size_bytes / 1024 / 1024
        metrics_logger.info(
            f"FILE_UPLOAD | FileName={file_name} | "
            f"Size={size_mb:.2f}MB | Type={file_type}"
        )
    
    @staticmethod
    def log_graph_operation(operation, triples_count, duration_ms):
        """Log RDF graph operations."""
        metrics_logger.info(
            f"GRAPH_OPERATION | Operation={operation} | "
            f"Triples={triples_count} | Duration={duration_ms:.2f}ms"
        )
    
    @staticmethod
    def log_error(error_type, error_message, context=""):
        """Log application errors."""
        metrics_logger.error(
            f"ERROR | Type={error_type} | "
            f"Message={error_message} | Context={context}"
        )
    
    @staticmethod
    def log_memory_usage():
        """Log current memory usage."""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            memory_percent = process.memory_percent()
            
            metrics_logger.info(
                f"MEMORY_USAGE | RSS={memory_mb:.2f}MB | "
                f"Percent={memory_percent:.2f}% | "
                f"VMS={memory_info.vms / 1024 / 1024:.2f}MB"
            )
        except Exception as e:
            metrics_logger.error(f"MEMORY_USAGE | Error: {e}")
    
    @staticmethod
    def log_cpu_usage():
        """Log current CPU usage."""
        try:
            process = psutil.Process(os.getpid())
            cpu_percent = process.cpu_percent(interval=0.1)
            cpu_times = process.cpu_times()
            
            metrics_logger.info(
                f"CPU_USAGE | Percent={cpu_percent:.2f}% | "
                f"UserTime={cpu_times.user:.2f}s | "
                f"SystemTime={cpu_times.system:.2f}s"
            )
        except Exception as e:
            metrics_logger.error(f"CPU_USAGE | Error: {e}")
    
    @staticmethod
    def log_performance_metric(operation_name, duration_ms, success=True, details=""):
        """Log performance metrics for specific operations."""
        status = "SUCCESS" if success else "FAILURE"
        metrics_logger.info(
            f"PERFORMANCE | Operation={operation_name} | "
            f"Duration={duration_ms:.2f}ms | Status={status} | "
            f"Details={details}"
        )
    
    @staticmethod
    def log_user_action(action, details=""):
        """Log user interactions and actions."""
        metrics_logger.info(f"USER_ACTION | Action={action} | Details={details}")
    
    @staticmethod
    def log_shacl_generation(num_shapes, num_properties, duration_ms):
        """Log SHACL generation metrics."""
        metrics_logger.info(
            f"SHACL_GENERATION | Shapes={num_shapes} | "
            f"Properties={num_properties} | Duration={duration_ms:.2f}ms"
        )
    
    @staticmethod
    def log_resource_snapshot():
        """Log comprehensive resource usage snapshot."""
        try:
            process = psutil.Process(os.getpid())
            cpu_percent = process.cpu_percent(interval=0.1)
            memory = process.memory_info()
            
            # System-wide stats
            system_memory = psutil.virtual_memory()
            system_cpu = psutil.cpu_percent(percpu=False)
            
            metrics_logger.info(
                f"RESOURCE_SNAPSHOT | "
                f"ProcessMemory={memory.rss / 1024 / 1024:.2f}MB | "
                f"ProcessCPU={cpu_percent:.2f}% | "
                f"SystemMemory={system_memory.percent}% | "
                f"SystemCPU={system_cpu}% | "
                f"AvailableMemory={system_memory.available / 1024 / 1024 / 1024:.2f}GB"
            )
        except Exception as e:
            metrics_logger.error(f"RESOURCE_SNAPSHOT | Error: {e}")


def measure_performance(operation_name):
    """Decorator to measure and log performance of functions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error_msg = ""
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_msg = str(e)
                MetricsCollector.log_error(
                    type(e).__name__,
                    error_msg,
                    f"Function: {operation_name}"
                )
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                MetricsCollector.log_performance_metric(
                    operation_name,
                    duration_ms,
                    success,
                    error_msg if not success else ""
                )
        
        return wrapper
    return decorator


# Export convenience function
def log_startup_metrics():
    """Log metrics when application starts."""
    try:
        import sys
        metrics_logger.info("=" * 80)
        metrics_logger.info(f"APPLICATION_STARTUP | Python={sys.version.split()[0]}")
        MetricsCollector.log_resource_snapshot()
    except Exception as e:
        metrics_logger.error(f"STARTUP_METRICS | Error: {e}")
