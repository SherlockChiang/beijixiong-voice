const state = {
  config: null,
  busy: false,
  progressTimer: null,
  progressStartedAt: 0,
};

const $ = (id) => document.getElementById(id);

function preferredTheme() {
  const saved = localStorage.getItem("beijixiong-theme");
  if (saved === "light" || saved === "dark") {
    return saved;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("themeIcon").textContent = theme === "dark" ? "☀" : "☾";
  $("themeToggle").setAttribute(
    "aria-label",
    theme === "dark" ? "切换日间模式" : "切换夜间模式",
  );
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme || preferredTheme();
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem("beijixiong-theme", next);
  applyTheme(next);
}

function setStatus(text, kind = "neutral") {
  const el = $("status");
  el.textContent = text;
  el.dataset.kind = kind;
}

function setBusy(value) {
  state.busy = value;
  $("previewBtn").disabled = value;
  $("generateBtn").disabled = value;
}

function payload() {
  return {
    text: $("text").value,
    voice: $("voice").value,
    seed: Number($("seed").value),
    textTemp: Number($("textTemp").value),
    waveformTemp: Number($("waveformTemp").value),
    speedPitch: Number($("speedPitch").value),
    maxChars: Number($("maxChars").value),
    outputName: $("outputName").value,
  };
}

async function requestJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

async function loadConfig() {
  const response = await fetch("/api/config");
  state.config = await response.json();

  const voice = $("voice");
  Object.entries(state.config.voices).forEach(([name, item]) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = `${name} · ${item.speaker}`;
    voice.appendChild(option);
  });
  voice.value = state.config.defaultVoice;

  $("seed").value = state.config.defaultSeed;
  $("textTemp").value = state.config.defaultTextTemp;
  $("waveformTemp").value = state.config.defaultWaveformTemp;
  $("speedPitch").value =
    state.config.voices[voice.value]?.speed_pitch || state.config.defaultSpeedPitch;
  $("maxChars").value = state.config.defaultMaxChars;
  syncRanges();
  await loadAudios();
}

function setProgress(value, label) {
  const percent = Math.max(0, Math.min(100, Math.round(value)));
  $("progressFill").style.width = `${percent}%`;
  $("progressValue").textContent = `${percent}%`;
  $("progressLabel").textContent = label;
}

function startProgress() {
  $("progressWrap").hidden = false;
  state.progressStartedAt = Date.now();
  setProgress(6, "提交任务");
  clearInterval(state.progressTimer);
  state.progressTimer = setInterval(() => {
    const elapsed = (Date.now() - state.progressStartedAt) / 1000;
    const estimate = 92 - 86 * Math.exp(-elapsed / 38);
    const label =
      elapsed < 8
        ? "加载模型"
        : elapsed < 25
          ? "生成语义 tokens"
          : "合成波形";
    setProgress(estimate, label);
  }, 600);
}

function finishProgress() {
  clearInterval(state.progressTimer);
  state.progressTimer = null;
  setProgress(100, "生成完成");
}

function failProgress() {
  clearInterval(state.progressTimer);
  state.progressTimer = null;
  setProgress(100, "生成失败");
}

function syncRanges() {
  $("textTempValue").textContent = $("textTemp").value;
  $("waveformTempValue").textContent = $("waveformTemp").value;
  $("speedPitchValue").textContent = `${$("speedPitch").value}x`;
}

function syncVoiceDefaults() {
  const voice = $("voice").value;
  const preset = state.config?.voices?.[voice];
  if (preset?.speed_pitch) {
    $("speedPitch").value = preset.speed_pitch;
    syncRanges();
  }
}

function formatSize(bytes) {
  if (bytes > 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function formatTime(value) {
  return new Date(value * 1000).toLocaleString();
}

function renderAudios(items) {
  const list = $("audioList");
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = '<div class="empty">暂无生成音频</div>';
    return;
  }

  items.forEach((item) => {
    const row = document.createElement("article");
    row.className = "audio-item";
    const duration = item.duration ? `${item.duration}s` : "--";
    row.innerHTML = `
      <div class="audio-meta">
        <strong>${item.file}</strong>
        <span>${duration} · ${formatSize(item.size)} · ${formatTime(item.mtime)}</span>
      </div>
      <audio controls src="${item.url}&t=${Date.now()}"></audio>
      <div class="audio-actions">
        <button class="mini" type="button" data-action="rename" data-file="${item.file}">重命名</button>
        <button class="mini danger" type="button" data-action="delete" data-file="${item.file}">删除</button>
      </div>
    `;
    list.appendChild(row);
  });
}

async function loadAudios() {
  const response = await fetch("/api/audios");
  const data = await response.json();
  renderAudios(data.audios || []);
}

async function preview() {
  setBusy(true);
  setStatus("Previewing...");
  try {
    const data = await requestJson("/api/preview", payload());
    $("prompt").textContent = data.prompt;
    setStatus("Prompt ready", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function generate() {
  setBusy(true);
  setStatus("Generating audio...");
  startProgress();
  $("audio").hidden = true;
  try {
    const data = await requestJson("/api/generate", payload());
    $("prompt").textContent = data.prompt;
    $("audio").src = `${data.audio.url}&t=${Date.now()}`;
    $("audio").hidden = false;
    await loadAudios();
    finishProgress();
    setStatus(`Done: ${data.audio.file}`, "ok");
  } catch (error) {
    failProgress();
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function copyPrompt() {
  await navigator.clipboard.writeText($("prompt").textContent);
  setStatus("Prompt copied", "ok");
}

async function handleAudioAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }

  const file = button.dataset.file;
  if (button.dataset.action === "rename") {
    const current = file.replace(/\.wav$/i, "");
    const name = window.prompt("新文件名", current);
    if (!name) {
      return;
    }
    try {
      await requestJson("/api/rename-audio", { file, name });
      await loadAudios();
      setStatus("Renamed", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  if (button.dataset.action === "delete") {
    if (!window.confirm(`删除 ${file}?`)) {
      return;
    }
    try {
      await requestJson("/api/delete-audio", { file });
      await loadAudios();
      setStatus("Deleted", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }
}

$("previewBtn").addEventListener("click", preview);
$("generateBtn").addEventListener("click", generate);
$("copyBtn").addEventListener("click", copyPrompt);
$("refreshBtn").addEventListener("click", loadAudios);
$("audioList").addEventListener("click", handleAudioAction);
$("themeToggle").addEventListener("click", toggleTheme);
$("voice").addEventListener("change", syncVoiceDefaults);
$("textTemp").addEventListener("input", syncRanges);
$("waveformTemp").addEventListener("input", syncRanges);
$("speedPitch").addEventListener("input", syncRanges);

applyTheme(preferredTheme());

loadConfig()
  .then(() => setStatus("Ready"))
  .catch((error) => setStatus(error.message, "error"));
