import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/storage_service.dart';
import '../services/discovery_service.dart';

enum ConnectionStatus { disconnected, connecting, connected, pairing }

class ConnectionProvider extends ChangeNotifier with WidgetsBindingObserver {
  ConnectionStatus _status = ConnectionStatus.disconnected;
  String? _ip;
  String? _pcName;
  String? _token;
  String? _error;
  List<DiscoveredPc> _discovered = [];
  bool _isScanning = false;
  Timer? _heartbeat;
  Map<String, dynamic> _systemStatus = {};

  ConnectionStatus get status    => _status;
  String?          get ip        => _ip;
  String?          get pcName    => _pcName;
  String?          get token     => _token;
  String?          get error     => _error;
  List<DiscoveredPc> get discovered => _discovered;
  bool             get isScanning  => _isScanning;
  bool             get isConnected => _status == ConnectionStatus.connected;
  Map<String, dynamic> get systemStatus => _systemStatus;
  bool             get autoConnectEnabled => _autoConnectEnabled;

  bool _autoConnectEnabled = true;

  // ── Init ──────────────────────────────────────────────────────
  Future<void> init() async {
    WidgetsBinding.instance.addObserver(this);

    final ip    = await StorageService.getIp();
    final token = await StorageService.getToken();
    final name  = await StorageService.getPcName();
    final autoConnect = await StorageService.getJson('settings:auto_connect');
    _autoConnectEnabled = (autoConnect as bool?) ?? true;

    if (ip != null && token != null) {
      _ip     = ip;
      _token  = token;
      _pcName = name;
      if (_autoConnectEnabled) {
        await _tryReconnect();
      }
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _status == ConnectionStatus.disconnected && _ip != null) {
      _tryReconnect();
    } else if (state == AppLifecycleState.paused) {
      // Keep heartbeat running in background
    }
  }

  Future<void> setAutoConnect(bool enabled) async {
    _autoConnectEnabled = enabled;
    await StorageService.saveJson('settings:auto_connect', enabled);
    notifyListeners();
  }

  Future<void> _tryReconnect() async {
    _setStatus(ConnectionStatus.connecting);
    final alive = await DiscoveryService.isReachable(_ip!);
    if (alive) {
      _setStatus(ConnectionStatus.connected);
      _startHeartbeat();
    } else {
      _setStatus(ConnectionStatus.disconnected);
      _error = 'Could not reach $_ip — make sure CYPHER is running on your PC';
    }
  }

  // ── Discovery ─────────────────────────────────────────────────
  Future<void> scan() async {
    _isScanning = true;
    _discovered = [];
    _error = null;
    notifyListeners();

    try {
      _discovered = await DiscoveryService.discover();
    } catch (e) {
      _error = 'Scan failed: $e';
    }

    _isScanning = false;
    notifyListeners();
  }

  Future<bool> connectTo(DiscoveredPc pc) async {
    _ip    = pc.ip;
    _error = null;
    _setStatus(ConnectionStatus.connecting);

    final alive = await DiscoveryService.isReachable(pc.ip);
    if (!alive) {
      _error = 'Could not reach ${pc.ip}';
      _setStatus(ConnectionStatus.disconnected);
      return false;
    }

    try {
      final data = await ApiService.getStatus(pc.ip);
      _pcName = data['pc_name'] as String? ?? pc.name;
    } catch (_) {
      _pcName = pc.name;
    }

    final isPaired = await StorageService.getIsPaired();
    if (!isPaired) {
      _setStatus(ConnectionStatus.pairing);
      return true; // caller should navigate to pairing screen
    }

    await StorageService.saveIp(pc.ip);
    _setStatus(ConnectionStatus.connected);
    _startHeartbeat();
    return true;
  }

  Future<bool> connectManually(String ip) async {
    return connectTo(DiscoveredPc(ip: ip, name: 'PC'));
  }

  // ── Pairing ───────────────────────────────────────────────────
  Future<bool> pair(String code, String deviceId, String deviceName) async {
    if (_ip == null) return false;
    _error = null;
    notifyListeners();

    try {
      final result = await ApiService.pairDevice(
        ip: _ip!,
        code: code,
        deviceId: deviceId,
        deviceName: deviceName,
      );

      _token = result['token'] as String?;
      if (_token == null) {
        _error = 'Pairing failed: no token received';
        return false;
      }

      await StorageService.saveToken(_token!);
      await StorageService.saveIp(_ip!);
      await StorageService.saveDeviceId(deviceId);
      await StorageService.saveDeviceName(deviceName);
      await StorageService.savePcName(_pcName ?? 'CYPHER PC');
      await StorageService.setIsPaired(true);

      _setStatus(ConnectionStatus.connected);
      _startHeartbeat();
      return true;
    } catch (e) {
      _error = e.toString();
      return false;
    }
  }

  // ── Heartbeat ─────────────────────────────────────────────────
  void _startHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(const Duration(seconds: 8), (_) async {
      if (_ip == null) return;
      final alive = await DiscoveryService.isReachable(_ip!);
      if (!alive && _status == ConnectionStatus.connected) {
        _setStatus(ConnectionStatus.disconnected);
        _error = 'Connection lost';
      } else if (alive && _status == ConnectionStatus.disconnected) {
        _setStatus(ConnectionStatus.connected);
        _error = null;
      }
    });
  }

  // ── Status Refresh ────────────────────────────────────────────
  Future<void> refreshStatus() async {
    if (_ip == null || !isConnected) return;
    try {
      _systemStatus = await ApiService.getSystemStats(_ip!);
      notifyListeners();
    } catch (_) {}
  }

  // ── Disconnect ────────────────────────────────────────────────
  Future<void> disconnect() async {
    _heartbeat?.cancel();
    _heartbeat = null;
    _setStatus(ConnectionStatus.disconnected);
    await StorageService.clearPairing();
    _ip     = null;
    _token  = null;
    _pcName = null;
    notifyListeners();
  }

  void _setStatus(ConnectionStatus s) {
    _status = s;
    notifyListeners();
  }

  @override
  void dispose() {
    _heartbeat?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
}
