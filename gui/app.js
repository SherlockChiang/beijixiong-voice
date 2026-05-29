const state = {
  config: null,
  busy: false,
  progressTimer: null,
  progressStartedAt: 0,
};

const MAX_UPLOAD_BYTES = 64 * 1024 * 1024;
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
  $("promptBtn").disabled = value;
  $("generateBtn").disabled = value;
}

function payload() {
  return {
    text: $("text").value,
    character: $("character").value,
    emotion: $("emotion").value,
    speed: Number($("speed").value),
    speedPitch: Number($("speedPitch").value),
    maxPauseMs: Number($("maxPauseMs").value),
    silenceThresholdDb: Number($("silenceThresholdDb").value),
    outputName: $("outputName").value,
    accent: true,
    accentIntensity: Number($("accentIntensity").value),
    prompt: $("prompt").value,
  };
}

async function requestJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const contentType = response.headers.get("Content-Type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : { error: await response.text() };
  if (!response.ok || data.error) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

async function loadConfig() {
  const response = await fetch("/api/config");
  state.config = await response.json();

  populateCharacterDropdown();
  updateEmotionDropdown();

  $("speed").value = state.config.defaultSpeed;
  $("speedPitch").value = state.config.defaultSpeedPitch;
  $("maxPauseMs").value = state.config.defaultMaxPauseMs;
  $("silenceThresholdDb").value = state.config.defaultSilenceThresholdDb;
  syncRanges();
  updateReferencePreview();
  await loadAudios();
}

function populateCharacterDropdown() {
  const sel = $("character");
  const current = sel.value;
  sel.innerHTML = "";
  (state.config.characters || []).forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    sel.appendChild(option);
  });
  if (state.config.characters.includes(current)) {
    sel.value = current;
  } else if (state.config.characters.length) {
    sel.value = state.config.characters[0];
  }
}

function updateEmotionDropdown() {
  const sel = $("emotion");
  const current = sel.value;
  const char = $("character").value;
  const emotions = state.config.map?.[char] || {};
  const emotionNames = Object.keys(emotions);

  sel.innerHTML = "";
  emotionNames.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    sel.appendChild(option);
  });

  if (emotionNames.includes(current)) {
    sel.value = current;
  } else if (emotionNames.length) {
    sel.value = emotionNames[0];
  }
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
    const estimate = 92 - 86 * Math.exp(-elapsed / 30);
    const label =
      elapsed < 6
        ? "加载模型"
        : elapsed < 15
          ? "提取参考特征"
          : "生成音频";
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

const ACCENT_LABELS = { 1: "轻柔", 2: "均衡", 3: "强烈", 4: "混沌" };

function syncRanges() {
  $("speedValue").textContent = `${$("speed").value}x`;
  $("speedPitchValue").textContent = `${$("speedPitch").value}x`;
  $("maxPauseValue").textContent = $("maxPauseMs").value === "0" ? "关闭" : `${$("maxPauseMs").value} ms`;
  $("silenceThresholdValue").textContent = `${$("silenceThresholdDb").value} dB`;
  $("accentIntensityValue").textContent = ACCENT_LABELS[$("accentIntensity").value] || "均衡";
}

function updateReferencePreview() {
  const char = $("character").value;
  const emotion = $("emotion").value;
  const entry = state.config?.map?.[char]?.[emotion];

  if (entry) {
    const fileName = entry.file ? entry.file.split(/[/\\]/).pop() : "--";
    $("refFileLabel").textContent = `${char} / ${emotion} — ${fileName}`;
    $("refTextLabel").textContent = entry.ref_text || "(无参考文本，可选)";
    $("refAudio").src = `/api/references/audio?file=${encodeURIComponent(fileName)}`;
    $("refAudio").hidden = false;
  } else {
    $("refFileLabel").textContent = "--";
    $("refTextLabel").textContent = "--";
    $("refAudio").hidden = true;
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

async function buildPrompt() {
  setBusy(true);
  setStatus("生成口音 Prompt...");
  try {
    const data = await requestJson("/api/prompt", payload());
    $("prompt").value = data.prompt;
    setStatus(`Prompt 已生成，实际语速 ${Number(data.effectiveSpeed || 1).toFixed(2)}x`, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function generate() {
  setBusy(true);
  setStatus("生成中...");
  startProgress();
  $("audio").hidden = true;
  try {
    if (!$("prompt").value.trim()) {
      throw new Error("请先生成或填写口音 Prompt。");
    }
    const data = await requestJson("/api/generate", payload());
    $("prompt").value = data.prompt;
    $("audio").src = `${data.audio.url}&t=${Date.now()}`;
    $("audio").hidden = false;
    await loadAudios();
    finishProgress();
    setStatus(`完成: ${data.audio.file}`, "ok");
  } catch (error) {
    failProgress();
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function copyPrompt() {
  await navigator.clipboard.writeText($("prompt").value);
  setStatus("已复制", "ok");
}

async function uploadReference() {
  const character = $("uploadCharacter").value.trim();
  const emotion = $("uploadEmotion").value.trim();
  const refText = $("uploadRefText").value.trim();
  const fileInput = $("uploadFile");

  if (!character) {
    setStatus("请填写角色名", "error");
    return;
  }
  if (!emotion) {
    setStatus("请填写情绪名", "error");
    return;
  }
  if (!fileInput.files.length) {
    setStatus("请选择音频文件", "error");
    return;
  }

  setBusy(true);
  setStatus("上传中...");
  try {
    const file = fileInput.files[0];
    if (file.size > MAX_UPLOAD_BYTES) {
      throw new Error("参考音频不能超过 64 MB。");
    }
    const ext = file.name.split(".").pop() || "wav";
    const arrayBuffer = await file.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    const audioData = btoa(binary);

    const result = await requestJson("/api/references/upload", {
      character,
      emotion,
      ref_text: refText,
      ext,
      audio_data: audioData,
    });

    state.config.characters = result.characters;
    state.config.map = result.map;
    populateCharacterDropdown();
    $("character").value = character;
    updateEmotionDropdown();
    $("emotion").value = emotion;
    updateReferencePreview();
    setStatus("上传成功", "ok");

    $("uploadCharacter").value = "";
    $("uploadEmotion").value = "";
    $("uploadRefText").value = "";
    fileInput.value = "";
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function deleteCurrentReference() {
  const char = $("character").value;
  const emotion = $("emotion").value;
  if (!char || !emotion) {
    setStatus("没有可删除的参考", "error");
    return;
  }
  if (!window.confirm(`删除 ${char}_${emotion} 的参考音频？`)) {
    return;
  }
  try {
    const result = await requestJson("/api/references/delete", { file: `${char}_${emotion}` });
    state.config.characters = result.characters;
    state.config.map = result.map;
    populateCharacterDropdown();
    updateEmotionDropdown();
    updateReferencePreview();
    setStatus("已删除", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function deleteCurrentCharacter() {
  const char = $("character").value;
  if (!char) {
    setStatus("没有可删除的角色", "error");
    return;
  }
  const emotions = state.config.map?.[char] || {};
  const count = Object.keys(emotions).length;
  if (!window.confirm(`删除角色「${char}」的全部 ${count} 个参考音频？`)) {
    return;
  }
  try {
    let result;
    for (const emotion of Object.keys(emotions)) {
      result = await requestJson("/api/references/delete", { file: `${char}_${emotion}` });
    }
    if (result) {
      state.config.characters = result.characters;
      state.config.map = result.map;
      populateCharacterDropdown();
      updateEmotionDropdown();
      updateReferencePreview();
    }
    setStatus(`已删除角色「${char}」`, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

function parseFilename(filename) {
  const stem = filename.replace(/\.[^.]+$/, "");
  const idx = stem.indexOf("_");
  if (idx <= 0) return null;
  return {
    character: stem.substring(0, idx),
    emotion: stem.substring(idx + 1),
  };
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
      setStatus("已重命名", "ok");
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
      setStatus("已删除", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }
}

$("promptBtn").addEventListener("click", buildPrompt);
$("generateBtn").addEventListener("click", generate);
$("copyBtn").addEventListener("click", copyPrompt);
$("refreshBtn").addEventListener("click", loadAudios);
$("audioList").addEventListener("click", handleAudioAction);
$("themeToggle").addEventListener("click", toggleTheme);
$("uploadBtn").addEventListener("click", uploadReference);
$("deleteCharacterBtn").addEventListener("click", deleteCurrentCharacter);
$("deleteEmotionBtn").addEventListener("click", deleteCurrentReference);
$("uploadFile").addEventListener("change", () => {
  const fileInput = $("uploadFile");
  if (!fileInput.files.length) return;
  const parsed = parseFilename(fileInput.files[0].name);
  if (parsed) {
    if (!$("uploadCharacter").value) $("uploadCharacter").value = parsed.character;
    if (!$("uploadEmotion").value) $("uploadEmotion").value = parsed.emotion;
  }
});
$("character").addEventListener("change", () => {
  updateEmotionDropdown();
  updateReferencePreview();
});
$("emotion").addEventListener("change", updateReferencePreview);
$("speed").addEventListener("input", syncRanges);
$("speedPitch").addEventListener("input", syncRanges);
$("maxPauseMs").addEventListener("input", syncRanges);
$("silenceThresholdDb").addEventListener("input", syncRanges);
$("accentIntensity").addEventListener("input", syncRanges);

applyTheme(preferredTheme());

loadConfig()
  .then(() => setStatus("Ready"))
  .catch((error) => setStatus(error.message, "error"));
