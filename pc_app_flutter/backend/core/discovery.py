try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

import socket
import threading
import time
import json
import logging
import uuid
import psutil

log = logging.getLogger("cypher")

class CypherDiscovery:
    def __init__(self, pc_name, port=5000):
        self.pc_name = pc_name
        self.port = port
        self.zeroconf = None
        self.info = None
        self.stop_event = threading.Event()
        self._lock = threading.Lock()

    def get_all_ips(self):
        """
        Returns all valid local IPv4 addresses.
        EXCLUDES 169.254.x.x (APIPA) and 127.0.0.1.
        PRIORITIZES USB tethering (192.168.42.x), hotspots (192.168.43.x, 192.168.137.x), and local LAN (10.x.x.x).
        """
        ips = []
        try:
            for _interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        # Filter out loopback and APIPA (dead-end) addresses
                        if ip.startswith("127.") or ip.startswith("169.254."):
                            continue

                        # Prioritize connection modes: USB tethering → hotspots → LAN
                        if ip.startswith("192.168.42."):  # USB tethering
                            ips.insert(0, ip)
                        elif ip.startswith("192.168.43.") or ip.startswith("192.168.137.") or ip.startswith("10."):
                            ips.insert(0, ip)
                        else:
                            ips.append(ip)
        except Exception as e:
            log.error(f"Error gathering IPs: {e}")

        # If no external IP found, include loopback as a last resort
        return ips if ips else ["127.0.0.1"]

    def _broadcast_udp(self):
        """High-frequency UDP Beacon (Robust implementation)."""
        log.info(f"[DISCOVERY] Starting UDP Beacon on port {self.port+1}")

        while not self.stop_event.is_set():
            udp_socket = None
            try:
                current_ips = self.get_all_ips()

                udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                udp_socket.settimeout(1.0)

                # Use a specific local IP to bind if possible, or bind to all
                try:
                    udp_socket.bind(('', 0))
                except OSError as exc:
                    # Binding is best-effort: an unbound socket still sends.
                    log.debug("Could not bind beacon socket: %s", exc)

                beacon_data = {
                    "type": "CYPHER_BEACON",
                    "pc_name": self.pc_name,
                    "port": self.port,
                    "id": str(uuid.getnode())
                }

                for ip in current_ips:
                    beacon_data["ip"] = ip
                    beacon = json.dumps(beacon_data).encode('utf-8')

                    # 1. Send to generic broadcast
                    try:
                        udp_socket.sendto(beacon, ('255.255.255.255', self.port + 1))
                    except OSError as exc:
                        # Many networks block 255.255.255.255; the subnet-specific
                        # broadcast below is the one that usually works.
                        log.debug("Generic broadcast send failed: %s", exc)

                    # 2. Send to subnet specific broadcast
                    try:
                        parts = ip.split('.')
                        if len(parts) == 4:
                            parts[-1] = '255'
                            subnet_broadcast = '.'.join(parts)
                            udp_socket.sendto(beacon, (subnet_broadcast, self.port + 1))
                    except (OSError, ValueError) as exc:
                        log.debug("Subnet broadcast send failed: %s", exc)

                # Sleep longer if no clients are active to save resources
                time.sleep(3)
            except Exception as e:
                log.error(f"Discovery Loop error: {e}")
                time.sleep(5)
            finally:
                if udp_socket:
                    udp_socket.close()

    def start(self):
        log.info(f"Starting discovery for '{self.pc_name}'...")
        try:
            if HAS_ZEROCONF:
                try:
                    self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
                    self._register_zeroconf()
                except Exception as ze:
                    log.error(f"Zeroconf init failed: {ze}")
            else:
                log.warning("Zeroconf not installed, skipping mDNS.")

            threading.Thread(target=self._broadcast_udp, daemon=True).start()
            threading.Thread(target=self._listen_for_probes, daemon=True).start()
        except Exception as e:
            log.error(f"Discovery startup failed: {e}")

    def _listen_for_probes(self):
        """Listen for 'Are you there?' probes from the mobile app."""
        try:
            probe_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Bind to all interfaces on probe port
            probe_sock.bind(('', self.port + 2))
            probe_sock.settimeout(2.0)

            while not self.stop_event.is_set():
                try:
                    data, addr = probe_sock.recvfrom(1024)
                    if b"CYPHER_PROBE" in data:
                        ips = self.get_all_ips()
                        response = json.dumps({
                            "type": "CYPHER_PROBE_RESPONSE",
                            "pc_name": self.pc_name,
                            "port": self.port,
                            "ip": ips[0] if ips else "127.0.0.1"
                        }).encode('utf-8')
                        probe_sock.sendto(response, addr)
                except TimeoutError:
                    continue
                except OSError as exc:
                    log.debug("Probe socket error: %s", exc)
        except Exception as e:
            log.error(f"Probe listener failed: {e}")

    def _register_zeroconf(self):
        if not HAS_ZEROCONF or not self.zeroconf: return
        try:
            all_ips = self.get_all_ips()
            # Don't register if only loopback
            if not all_ips or all_ips == ["127.0.0.1"]: return

            unique_id = str(uuid.uuid4())[:8]
            self.info = ServiceInfo(
                "_cypher._tcp.local.",
                f"{self.pc_name}-{unique_id}._cypher._tcp.local.",
                addresses=[socket.inet_aton(ip) for ip in all_ips],
                port=self.port,
                properties={'pc_name': self.pc_name},
                server=f"{socket.gethostname()}.local.",
            )
            self.zeroconf.register_service(self.info)
            log.info(f"Registered Zeroconf service for IPs: {all_ips}")
        except Exception as e:
            log.error(f"mDNS registration failed: {e}")

    def update_name(self, new_name):
        self.pc_name = new_name
        if self.zeroconf and self.info:
            try:
                self.zeroconf.unregister_service(self.info)
                self._register_zeroconf()
            except Exception as exc:
                # The advertised name is now stale but discovery still works via
                # the UDP beacon. Not worth killing the service over.
                log.warning("Could not re-register mDNS after name change: %s", exc)

    def stop(self):
        self.stop_event.set()
        if self.zeroconf:
            self.zeroconf.close()

# --- GLOBAL HELPERS ---
_discovery_instance = None

def start_discovery_thread(pc_name, port=5000):
    global _discovery_instance
    if _discovery_instance is None:
        _discovery_instance = CypherDiscovery(pc_name, port)
        _discovery_instance.start()
    return _discovery_instance

def get_discovery_instance():
    return _discovery_instance
