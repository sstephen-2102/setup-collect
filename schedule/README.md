# Scheduling the Collect workflow

The collector is designed to run **daily at 7:00 AM** so the Sunday discussion-post review always has a fresh 7-day window.

## Enable on this Mac (launchd)

```bash
cp "/Users/sanjayvarghese/Cursor Projects/Setup Collect/schedule/com.sanjay.techcollect.plist" \
   "$HOME/Library/LaunchAgents/com.sanjay.techcollect.plist"
launchctl load "$HOME/Library/LaunchAgents/com.sanjay.techcollect.plist"
launchctl start com.sanjay.techcollect
```

Unload later with:

```bash
launchctl unload "$HOME/Library/LaunchAgents/com.sanjay.techcollect.plist"
```

## Manual run

```bash
"/Users/sanjayvarghese/Cursor Projects/Setup Collect/run_collect.sh"
```

## Cron alternative

```
0 7 * * * /Users/sanjayvarghese/Cursor\ Projects/Setup\ Collect/run_collect.sh
```
