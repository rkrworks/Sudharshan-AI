const workflows = {
  tasks: {
    title: "Local task list",
    command: 'python3 sudharshan_cli.py tasks --db "$HOME/.local/share/sudharshan/tasks.db" list',
    description: "Reads tasks from a local SQLite database. Add tasks in plain text and export pending items to iCalendar."
  },
  vault: {
    title: "Markdown backlinks",
    command: 'python3 sudharshan_cli.py vault "$HOME/Notes"',
    description: "Indexes Markdown notes in the selected folder and reports their wikilinks and backlinks."
  },
  git: {
    title: "Repository status",
    command: "python3 sudharshan_cli.py git --repo . --suggest-commit",
    description: "Shows staged, unstaged and untracked changes. A conventional commit suggestion is optional."
  },
  symbols: {
    title: "Code symbol search",
    command: "python3 sudharshan_cli.py symbols LocalGitAssistant --root .",
    description: "Indexes supported local source files, then returns matching symbols and file locations."
  },
  redact: {
    title: "Text redaction",
    command: "cat notes.txt | python3 sudharshan_cli.py redact",
    description: "Reads text from stdin and masks recognized API keys, payment card numbers and private IP addresses."
  },
  "archive-inspect": {
    title: "Archive inspection",
    command: "python3 sudharshan_cli.py archive-inspect release.zip",
    description: "Lists ZIP or TAR members without extracting files into a destination."
  },
  "dedupe-report": {
    title: "Duplicate file report",
    command: 'python3 sudharshan_cli.py dedupe-report "$HOME/Downloads"',
    description: "Hashes files under a directory and reports identical content. It does not remove duplicates."
  },
  "disk-report": {
    title: "Cache recommendations",
    command: 'python3 sudharshan_cli.py disk-report "$HOME/Projects"',
    description: "Finds known build and language caches for review. It does not delete them."
  },
  "schedule-preview": {
    title: "Cron schedule preview",
    command: "python3 sudharshan_cli.py schedule-preview 'daily at 18:30' --command 'python3 backup.py'",
    description: "Converts one of the supported schedules into a cron line. It is not installed or executed."
  },
  "organize-preview": {
    title: "File organization preview",
    command: 'python3 sudharshan_cli.py organize-preview "$HOME/Downloads"',
    description: "Groups direct-child files by extension and prints proposed moves without changing the folder."
  }
};

const commandButtons = [...document.querySelectorAll("[data-workflow]")];
const commandTitle = document.getElementById("commandTitle");
const commandCode = document.getElementById("commandCode");
const commandDescription = document.getElementById("commandDescription");
const commandStatus = document.getElementById("commandStatus");

commandButtons.forEach(button => {
  button.addEventListener("click", () => {
    const workflow = workflows[button.dataset.workflow];
    if (!workflow) return;
    commandButtons.forEach(item => item.setAttribute("aria-pressed", String(item === button)));
    commandTitle.textContent = workflow.title;
    commandCode.textContent = workflow.command;
    commandDescription.textContent = workflow.description;
    commandStatus.textContent = "";
  });
});

document.getElementById("copyCommand")?.addEventListener("click", async () => {
  try {
    if (!navigator.clipboard?.writeText) throw new Error("Clipboard access is unavailable in this browser context.");
    await navigator.clipboard.writeText(commandCode.textContent);
    commandStatus.textContent = "Command copied.";
  } catch (error) {
    commandStatus.textContent = `${error.message} Select the command text to copy it manually.`;
  }
});

const themeToggle = document.getElementById("themeToggle");
themeToggle?.addEventListener("click", () => {
  const light = document.documentElement.dataset.theme !== "light";
  document.documentElement.dataset.theme = light ? "light" : "dark";
  themeToggle.textContent = light ? "Dark theme" : "Light theme";
  themeToggle.setAttribute("aria-label", `Switch to ${light ? "dark" : "light"} theme`);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", light ? "#f4f4f6" : "#0b0b0d");
});

const fileInput = document.getElementById("verifyFile");
const verifyResult = document.getElementById("verifyResult");
const maxFileSize = 128 * 1024 * 1024;
fileInput?.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) {
    verifyResult.textContent = "No file selected.";
    return;
  }
  if (file.size > maxFileSize) {
    verifyResult.textContent = "This file is larger than 128 MiB. Choose a smaller file to hash in the browser.";
    return;
  }
  if (!globalThis.crypto?.subtle) {
    verifyResult.textContent = "Web Crypto is unavailable. Open this page over HTTPS or localhost to hash a file.";
    return;
  }

  verifyResult.textContent = `Calculating SHA-256 for ${file.name} locally…`;
  try {
    const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    const hash = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
    verifyResult.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KiB\n${hash}`;
  } catch (error) {
    verifyResult.textContent = `Could not calculate the digest: ${error.message}`;
  }
});
