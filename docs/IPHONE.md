# iPhone setup

You will build one Shortcut (three actions) and one NFC automation. Allow about five minutes.

Have the Mac nearby with nearsay installed. In a Mac terminal, run:

```bash
nearsay phone
```

It prints the **Host**, **User** and **Script** values used below.

---

## Part 1: The "nearsay" Shortcut

Open **Shortcuts** → **Shortcuts** tab → **+** (new shortcut). Rename it **nearsay** (tap the name at the top).

### Action 1: Dictate Text

Search the actions for **Dictate Text** and add it.

- **Language:** the language you will speak.
- **Stop Listening:** *After Pause* is quickest for one-sentence tasks. Choose *On Tap* if you want to speak longer, multi-sentence tasks; you then tap Done when finished.

This action produces a variable called **Dictated Text**.

### Action 2: Run Script Over SSH

Add **Run Script Over SSH**. Tap the arrow or *Show More* to see every field, then fill them in with the values from `nearsay phone`:

| Field | Value |
|---|---|
| Host | your Mac's name, such as `Andys-MacBook-Pro.local` (or its address) |
| Port | `22` |
| User | your Mac account's short name |
| Authentication | **SSH Key** |
| Input | **Dictated Text** (choose the variable from the bar above the keyboard) |
| Script | `tap` |

The *Script* field is not run as a command. It is read by nearsay as a sticker or project name (`tap` alone means "decide from what I said, otherwise use the default project"). The *Input* field carries your words.

**Send the key to the Mac.** With *Authentication* set to *SSH Key*, tap the key field and choose **Share Public Key**. Send it to the Mac by AirDrop, or copy it (Universal Clipboard pastes on the Mac if both devices use the same Apple Account). Then on the Mac:

```bash
nearsay add-key --from-clipboard          # if you copied it
# or, if you AirDropped a file:
nearsay add-key "$(cat ~/Downloads/<the file>)"
```

Only the **public** key leaves the phone; nearsay refuses a private key if one is pasted by mistake. The key it writes can only run nearsay's receiver.

### Action 3: Show Notification

Add **Show Notification**. Set its text to the **Shell Script Result** variable (the output of action 2), and the title to `Claude Code` if you like.

The result starts with **✓** on success (`✓ orkestra · starting: add tests…`) or **✗** with a plain-English reason (`✗ Nothing was heard, so no task was sent.`).

*Optional:* add **If** → *Shell Script Result* → *begins with* → `✗`, and inside it **Speak Text** with the result, so you hear problems without looking.

### Test the Shortcut

Tap ▶︎ in the Shortcut editor, say "In inbox, list the files here," and stop talking. A terminal should open on the Mac.

- If iOS asks whether Shortcuts may find and connect to devices on your local network, allow it. If you declined earlier: Settings → Privacy & Security → Local Network → Shortcuts → on.
- If anything fails, the notification says why; `nearsay doctor` on the Mac says how to fix it.

---

## Part 2: The NFC automation

1. Shortcuts → **Automation** tab → **+** (New Automation).
2. Choose **NFC**.
3. Tap **Scan**, hold the top edge of the iPhone against the sticker until it registers, and name it (for example *Claude sticker*).
4. Choose **Run Immediately** and turn **Notify When Run** off.
5. Tap **Next** and choose **nearsay**.

The phone must be unlocked for NFC automations to run. Touch the sticker with the **top edge** of the iPhone, where its NFC antenna is.

> **One thing to check on your iOS version.** When the automation starts *Dictate Text*, iOS should show its small listening panel. I could not confirm from Apple's documentation that every iOS version shows it for automations started by NFC. If yours shows a keyboard instead, tap the keyboard's microphone key to dictate (one extra tap), or replace *Dictate Text* with **Ask for Input** (type: Text) and dictate into it. The Mac side is identical either way.

---

## More than one sticker

Give a sticker a fixed project, for example a sticker on your monitor for *provalume*:

1. On the Mac: `nearsay sticker add lab provalume`
2. In Shortcuts, long-press **nearsay** → **Duplicate**. Rename the copy **nearsay (lab)** and change its *Script* field to `tap lab`.
3. Create another NFC automation for the new sticker that runs **nearsay (lab)**.

Saying a project out loud still wins ("In orkestra, …"), so any sticker can reach any project.

*Alternative without duplicates:* change the original Shortcut's Script field to `tap` followed by the **Shortcut Input** variable, and in the Shortcut's settings set *If there's no input* to *Continue*. Each automation can then use **Run Shortcut** → *nearsay* with a **Text** action containing `lab` as its input.

---

## Other ways to trigger the same Shortcut

The Shortcut works from anywhere, not just the sticker:

- **Siri:** say "nearsay."
- **Action Button** (iPhone 15 Pro and later): Settings → Action Button → Shortcut → nearsay.
- **Back Tap:** Settings → Accessibility → Touch → Back Tap → Double Tap → nearsay.
- **Control Center or Lock Screen:** add a Shortcut control and pick nearsay.

Some of these may open with a keyboard instead of listening; tap the microphone key.

**A "what's running?" Shortcut (optional).** Duplicate nearsay, delete the *Dictate Text* action, and set the Script field to `status`. Running it shows the last few taps and whether they started (`launched: orkestra: add tests…`).

---

## Away from home

At home, the `.local` name from `nearsay phone` finds your Mac on the Wi-Fi network. Elsewhere, the simplest secure option is **Tailscale**, a free private network between your own devices:

1. Install Tailscale on the Mac and the iPhone and sign in to the same account on both.
2. In the Shortcut's SSH action, set **Host** to the Mac's Tailscale address (`nearsay phone` prints it once Tailscale is running) or its Tailscale machine name.
3. Optionally restrict the key to your home network and Tailscale only:
   ```bash
   nearsay add-key --from-clipboard --allow-from 192.168.1.0/24 --allow-from 100.64.0.0/10
   ```
   (Use your own home network range; `ipconfig getifaddr en0` shows the Mac's address.)

Do **not** open port 22 on your home router to the internet.

The Mac must be awake. A MacBook with its lid open and screen unlocked is the normal case, since the sticker is on it.
