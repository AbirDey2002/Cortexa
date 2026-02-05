import ipaddress
import socket
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

BLOCKED_HOSTS = {
    "metadata.google.internal",
    "169.254.169.254",  # AWS/Azure/GCP metadata
    "metadata",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
}

class SecurityException(Exception):
    """Raised when a security violation is detected."""
    pass

def validate_url_for_ssrf(url: str) -> bool:
    """
    Validates a URL to prevent SSRF attacks.
    Checks against blocked hosts and private IP ranges.
    
    Args:
        url: The URL to validate.
        
    Returns:
        bool: True if valid.
        
    Raises:
        SecurityException: If the URL is potentially dangerous.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            # For data: URLs or other non-host URLs, we don't block by hostname
            if url.startswith("data:"):
                return True
            raise SecurityException("Invalid URL or missing hostname")

        hostname_lower = hostname.lower()
        
        # 1. Block known metadata and local hosts
        if hostname_lower in BLOCKED_HOSTS:
            logger.warning(f"SSRF Prevention: Blocked host detected: {hostname}")
            raise SecurityException(f"Access to host '{hostname}' is blocked for security reasons.")

        # 2. Block private IP ranges
        try:
            # Resolve hostname to IP
            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)
            
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                logger.warning(f"SSRF Prevention: Private/Internal IP detected: {ip} for host {hostname}")
                raise SecurityException(f"Access to private or internal IP addresses is not allowed.")
                
        except socket.gaierror:
            # Hostname couldn't be resolved, might be an invalid host or 
            # something like a service name in a local network.
            # We allow it to fail at the request level if it's truly invalid,
            # but we've already checked the main blocklist.
            pass
        except ValueError:
            # Invalid IP format from gethostbyname (unlikely)
            pass

        return True
    except SecurityException:
        raise
    except Exception as e:
        logger.error(f"Error validating URL for SSRF: {e}")
        # On validation error, fail closed for security
        raise SecurityException(f"URL validation failed.")
