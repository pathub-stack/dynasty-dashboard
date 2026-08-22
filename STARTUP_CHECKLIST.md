# VS Code Startup Checklist 🚀
### Dynasty Dashboard Project

Follow these steps every time you open VS Code to make sure you're in the right environment with Claude Code properly briefed.

---

## Step 1 — Open Your Project Folder
**File → Open Folder** → navigate to `dynasty-dashboard` on your Desktop

```
C:\Users\patri\Desktop\dynasty-dashboard
```

---

## Step 2 — Open the Terminal
**View → Terminal** or press `` Ctrl + ` ``

---

## Step 3 — Activate Virtual Environment
```bash
.\venv\Scripts\activate
```

✅ You should see `(venv)` at the start of your terminal line:
```
(venv) PS C:\Users\patri\Desktop\dynasty-dashboard>
```

> ⚠️ If you don't see `(venv)` — stop. Don't install anything. Re-run the command above.

---

## Step 4 — Confirm You're in the Right Folder
```bash
pwd
```

Should return:
```
C:\Users\patri\Desktop\dynasty-dashboard
```

If it doesn't, navigate there:
```bash
cd C:\Users\patri\Desktop\dynasty-dashboard
```

---

## Step 5 — Open Claude Code
Click the Claude Code icon in the VS Code sidebar, or:
**Ctrl + Shift + P** → type "Claude Code" → hit Enter

---

## Step 6 — Claude Code Auto-Reads CLAUDE.md ✅
No briefing paste needed. Claude Code automatically reads `CLAUDE.md`
at the start of every session. That file contains all project context,
learning instructions, and tells Claude Code to update `LEARNING_NOTES.md`
after each session.

---

## You're Ready to Code 🏈

---

## Syncing Learning Notes to Notion
After any session where Claude Code updated `LEARNING_NOTES.md`:
1. Open `LEARNING_NOTES.md`
2. Copy the full contents
3. Paste into Claude.ai chat
4. Claude.ai will sync it to your Notion page automatically
