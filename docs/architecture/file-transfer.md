# File Transfer Protocol - Complete Specification

## Overview

CYPHER supports bidirectional file transfer:
- **Download:** PC → Mobile (any file size)
- **Upload:** Mobile → PC (any file size)

Transfers use HTTP streaming (not chunked manually) for reliability.

---

## Download Flow (PC → Mobile)

### Request
GET /files/download?path=C:\Users\Downloads\video.mp4
Headers: X-Auth-Token: abc123xyz

### Backend Processing
1. Validate token
2. Check file exists and is a valid file on disk via os.path.isfile
3. Generate audit log action "File Downloaded" under activity tracking
4. Stream file contents out using standard streaming attachments
5. Automatically infer Content-Type from file extension

### Mobile Receiving
1. Listen to response stream
2. Receive bytes chunk by chunk
3. Calculate progress: (received_bytes / total_bytes) * 100
4. Save to phone storage
5. Calculate speed: bytes_per_second
6. Estimate time remaining: remaining_bytes / speed

### Progress UI
Download: video.mp4
[=========>        ] 45%
Speed: 2.3 MB/s
Time remaining: 2m 15s
[Pause] [Cancel]

### Error Handling

| Error | Response | Mobile Action |
|-------|----------|---------------|
| File not found | 500 / Error json | Show error message or log |
| Path invalid | 500 / Error json | Show error message or log |
| Connection lost | Network error | Show retry button |
| File locked | 500 / Error json | Show error message or log |

---

## Upload Flow (Mobile → PC)

### Request
POST /files/upload
Headers: X-Auth-Token: abc123xyz
Content-Type: multipart/form-data
Body:

file: [binary data]
destination: C:\Users\Downloads


### Backend Processing
1. Validate token
2. Resolve destination path from form parameters
3. Check for naming conflicts using get_unique_path counter (e.g. filename (1).ext)
4. Create temporary transfer tracker entry in active_transfers registry
5. Create staging file named: final_filename.part
6. Receive file stream and write contents to the .part file
7. On successful completion, rename .part file atomically to final name
8. Commit activity log entry "File Received" and notify via WebSocket logs

### Mobile Sending
1. File picker selects file
2. Show destination folder selector
3. Call GET /files/list to populate folders
4. User selects destination
5. Create request with multipart/form-data
6. Send with progress callback
7. Display progress bar
8. On completion, log action

### Progress UI
Uploading: backup.bak
[=========>        ] 45%
Speed: 1.8 MB/s
Time remaining: 3m 10s
[Pause] [Cancel]

---

## Batch Download (Multiple Files Queue)

### Request
Looping sequential GET requests handled directly by the client instance.
GET /files/download?path=C:\Users\Downloads\file1.txt
GET /files/download?path=C:\Users\Downloads\file2.png

### Backend Processing
1. Handle each file download request natively as an individual stream
2. Validate target path status independently per request
3. Stream file payload directly without packaging into an archive
4. Maintain original file structure without requiring user extraction

### Response
- Content-Type: [Inferred from extension]
- Content-Disposition: attachment; filename="filename.ext"

---

## Resume & Pause

### Pause
Mobile: Stop reading from stream
Server: Stream stops, connection remains open

### Resume
Dedicated alternate range seeking request:
GET /files/download/chunked?path=...
Range: bytes=1048576-

Server responds with 206 Partial Content, returning headers for Accept-Ranges: bytes and Content-Range, streaming file segments dynamically through a memory-efficient generator.

---

## File Size Limits

**For V1.0:**
- No hard limit on file size
- Streaming handles large files efficiently
- Memory usage stays low (streaming, not buffering)

**Recommendations:**
- Test with 1GB+ files
- Monitor mobile disk space before upload
- Show warning if file > 1GB

---

## Naming Conflicts

**Download:** No conflict (writing to separate client environment)

**Upload to existing file:**
- Option A: Overwrite (ask user)
- Option B: Auto-rename: filename (1).ext (Implemented automatically via incremental path utility)
- Option C: Reject (ask user to delete first)

**Recommendation:** Option B (auto-rename, show result)
Success: Uploaded as "backup (1).bak"

---

## Validation

### Paths (Security)

Allowed:
- C:\Users\[username]\Downloads
- C:\Users\[username]\Documents
- Explicit custom configured directory path structures

Blocked:
- c:\windows
- c:\program files
- c:\program files (x86)
- c:\users\default
- c:\boot
- c:\recovery

Check: Target strings must be resolved canonical paths validated using relative_to checks against configured directories to block directory traversal attempts.

### Files

- Max filename length: 260 characters (Windows limit)
- Invalid chars: < > : " / \ | ? *
- Reserved names: CON, PRN, AUX, NUL, COM1-9, LPT1-9

---

## Logging

Every file transfer is logged:

```json
{
  "action": "Received: backup.bak",
  "device": "Phone",
  "time": "14:30"
}