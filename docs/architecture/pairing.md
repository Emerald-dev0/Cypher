# Pairing System - Complete Specification

## Overview

CYPHER uses a 6-digit pairing code for initial connection.
After pairing, all requests use auth tokens.

---

## Pairing Code Generation

### Requirements
- 6 random digits (100,000 to 999,999)
- Regenerated on every server start
- Valid for one successful pairing
- Displayed prominently on PC

### Implementation (Python)
```python
import random

PAIRING_CODE = str(random.randint(100000, 999999))
```

### Display on PC
Show in large text (32px+) on dashboard home screen:
YOUR PAIRING CODE
123456

---

## Pairing Request Flow

### Step 1: Mobile Sends Pairing Request
POST /pair_device
Headers: Content-Type: application/json
Body:
{
"pairing_code": "123456",
"device_id": "android_abc123",
"device_name": "My Phone"
}

**device_id:** Unique identifier for this phone
- Generate once on first app launch
- Store in SharedPreferences
- Format: `android_[UUID]` or `android_[UNIQUE_ID]`

**device_name:** User-friendly name
- Default: Device model name
- User can customize in settings

### Step 2: Backend Validates

```python
if str(client_code) == PAIRING_CODE:
    # Code correct, generate token
    auth_token = secrets.token_hex(16)  # 32-char hex string
    
    # Store paired device
    paired_devices[device_id] = {
        "device_name": device_name,
        "token": auth_token,
        "paired_at": datetime.now(),
        "last_seen": datetime.now()
    }
    
    # Persist to file
    save_paired_devices()
    
    # Return success
    return {
        "success": true,
        "token": auth_token
    }
else:
    return {
        "success": false,
        "error": "Invalid pairing code"
    }
```

### Step 3: Mobile Stores Token

```dart
// SharedPreferences
await prefs.setString('auth_token', response.token);
await prefs.setString('device_id', device_id);
await prefs.setBool('is_paired', true);
await prefs.setString('pc_ip_address', ip_address);
```

---

## Token Usage (After Pairing)

### Every Request Includes Token
GET /system-stats
Headers:
Content-Type: application/json
X-Auth-Token: abc123xyz...

### Backend Validation

```python
@app.before_request
def verify_token():
    token = request.headers.get('X-Auth-Token')
    
    if token not in valid_tokens:
        return {
            "success": false,
            "error": "Unauthorized"
        }, 401
```

---

## Token Security

### Generation
- Use `secrets.token_hex(16)` (cryptographically secure)
- Never use `random` for tokens

### Storage
- **Backend:** paired_devices.json (protected file)
- **Mobile:** SharedPreferences (encrypted on modern Android)
- Never log tokens

### Expiry
- No automatic expiry (valid indefinitely)
- Manual revocation via /unpair endpoint

### What NOT to Do
- ❌ Never show token to user
- ❌ Never use same token for multiple devices
- ❌ Never hardcode tokens
- ❌ Never transmit over non-HTTPS (local network OK)

---

## Re-Pairing (User Wants New Token)

### Option 1: Manual Unpair + Repair
Phone: Settings → Unpair Device
→ Deletes token from SharedPreferences
→ Shows pairing screen
→ User enters new pairing code
→ New token generated

### Option 2: Auto-Repair (Invalid Token)
Phone makes request with old token
Backend returns 401 Unauthorized
Mobile app:
→ Detects 401
→ Shows "PC unpaired, please pair again"
→ Shows pairing screen
→ User enters new code

---

## Multiple Devices (Pairing Multiple Phones)

### Allowed
- Multiple phones can pair with same PC
- Each gets unique token
- Each appears in PC device list

### Device List
GET /paired-devices
Returns:
[
{
"device_id": "android_abc123",
"device_name": "My Phone",
"paired_at": "2026-06-01 10:00:00"
},
{
"device_id": "android_xyz789",
"device_name": "Work Phone",
"paired_at": "2026-06-01 10:30:00"
}
]

---

## Un-Pairing

### From Mobile
Mobile Settings → Unpair
→ Sends DELETE /unpair with token
→ Backend removes from paired_devices
→ Mobile deletes token from SharedPreferences

### From PC
PC Dashboard → Device List → Select device → "Unpair"
→ Backend removes device
→ Next time mobile tries to connect, gets 401
→ Mobile shows "Please pair again"

---

## First Launch Detection

On mobile first launch:

```dart
Future<void> checkIfPaired() async {
  final token = prefs.getString('auth_token');
  
  if (token == null) {
    // First launch, show onboarding
    Navigator.pushNamedAndRemoveUntil(
      context, 
      '/onboarding', 
      (route) => false
    );
  } else {
    // Already paired, go to home
    Navigator.pushNamedAndRemoveUntil(
      context, 
      '/home', 
      (route) => false
    );
  }
}
```

---

## Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "Invalid pairing code" | Code doesn't match | Check PC, try again |
| "Device already paired" | Device paired twice | Use existing token |
| "Unauthorized" | Token invalid/expired | Go to settings, unpair & repair |
| "Connection refused" | PC not running | Start PC app |
| "Timeout" | No response from PC | Check WiFi connection |

---

## Testing Checklist

- [ ] Pairing works first time
- [ ] Token persists after app restart
- [ ] Multiple devices can pair simultaneously
- [ ] Invalid code rejected with clear error
- [ ] Unpairing works and requires re-pairing
- [ ] Invalid token returns 401
- [ ] Device appears in PC device list within 5 seconds