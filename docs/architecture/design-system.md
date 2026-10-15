# CYPHER UI Design System

## Philosophy

Professional, minimal, functional. Like Vercel or Discord.
- No gimmicks
- No excessive animations
- Clear hierarchy
- Dark mode optimized

---

## Color Palette

### Backgrounds
Primary Background:    #0F0F10  (darkest, main bg)
Secondary Background:  #16161A  (cards, panels)
Tertiary Background:   #1E1E26  (hover states)

### Text
Primary Text:          #FFFFFF  (main text)
Secondary Text:        #A0A0A0  (muted text)
Tertiary Text:         #666666  (hints, disabled)

### Accents
Success/Primary:       #10B981  (green - actions)
Error:                 #FF6B6B  (red - danger)
Warning:               #FFD666  (amber - caution)
Info:                  #3B82F6  (blue - info)

### Borders
Default Border:        rgba(255, 255, 255, 0.1)
Hover Border:          rgba(255, 255, 255, 0.15)
Focus Border:          #10B981
Error Border:          #FF6B6B

---

## Typography

### Font Stack
-apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", sans-serif

### Sizes
H1 Page Title:         32px / 700 weight / 1.2 line-height
H2 Section:            24px / 600 weight / 1.3 line-height
H3 Subsection:         18px / 600 weight / 1.4 line-height
Body Text:             14px / 400 weight / 1.5 line-height
Caption:               12px / 400 weight / 1.4 line-height
Code/Mono:             13px / 400 weight / JetBrains Mono

---

## Components

### Button
Height:                40px
Padding:               0 16px
Border Radius:         8px
Font:                  14px / 600 weight
Background:            #10B981 (primary)
Text Color:            #FFFFFF
Hover:                 Slightly brighter green
Border:                None
Shadow:                None (or tiny on hover)

### Card
Background:            #16161A
Border:                1px solid rgba(255, 255, 255, 0.08)
Padding:               16px
Border Radius:         12px
Hover:                 Border opacity increases to 0.15
Shadow:                None

### Input Field
Height:                40px
Padding:               12px 16px
Border:                1px solid rgba(255, 255, 255, 0.1)
Border Radius:         8px
Background:            #0F0F10
Font:                  14px / 400 weight
Focus:                 Border becomes green, no glow effect

### Status Indicator
Size:                  8px circle
Connected:             #10B981 (green)
Connecting:            #FFD666 (amber)
Disconnected:          #666666 (gray)
Pulse:                 Optional subtle pulse (100ms)

---

## Spacing Grid
Base Unit:             8px
Tight:                 8px
Normal:                16px
Comfortable:           24px
Generous:              32px
Card Padding:          16px (2 units)
Button Padding:        16px horizontal
Section Margin:        24px (3 units)
Page Margin:           32px (4 units)

---

## Animations

### What to Remove
- ❌ Wave animations
- ❌ Pulsing icons
- ❌ Spinning loaders
- ❌ Multiple simultaneous animations

### What to Keep
Page Transitions:      200ms fade or slide
Button Hover:          100ms brightness
Loading Spinner:       1s smooth rotation
Modal Entrance:        200ms scale + fade
Toast Entrance:        150ms slide from bottom

---

## Dark Mode (Default)

All colors designed for dark background.
No light mode in V1.0.

---

## Screens

### Mobile: Home
[Status Bar - green if connected]
[HERO CARD]
Connected to PC
Desktop-PC
192.168.137.100
[4-CARD GRID]
Files     Controls
Clipboard Activity
[RECENT - 3 items max]
Downloaded: backup.zip
Synced: Clipboard
...

### Mobile: Files
[Header: Files + Refresh]
[Breadcrumb: Home > Documents]
[Search (optional)]
[File List]
📄 file.txt
1.2 MB  |  Today 14:30
📁 Folder
5 items
[Empty State]
No files in this folder

### PC: Dashboard
[SIDEBAR - 240px]
CYPHER
Navigation

Home
Files
Controls
Activity
Settings

Status: 🟢 Connected
[MAIN AREA]
[Shows selected page]
[Full width content]

---

## Interaction Patterns

### Success
Toast notification:
✓ File uploaded successfully
Auto-dismiss after 4 seconds

### Error
Toast notification:
✗ Failed to connect
Keep until user dismisses or timeout

### Confirmation
Dialog box:
Are you sure you want to shutdown?
[Cancel] [Shutdown]

---

## Accessibility

- Min contrast ratio: 4.5:1
- Touch targets: Min 40px
- No color-only indicators (use icons too)
- Clear focus states

---

## Responsive (Mobile)
Portrait:      320-768px width
Landscape:     768px+ width
Mobile-first approach
Stack content vertically by default
Use full width for cards