// 全局状态
let me = null;
let sessions = [];
let agents = [];
let skills = [];
let currentSessionId = null;
let sending = false;
let currentView = "new";
let currentAssistantTurn = null;
let groupCollapsed = {}; // agent_name -> bool

// DOM 缓存
const $list = document.getElementById("list");
const $msgs = document.getElementById("messages");
const $input = document.getElementById("input");
const $send = document.getElementById("send");
const $who = document.getElementById("who");
const $logout = document.getElementById("logout");
const $newMsgBtn = document.getElementById("new-msg-btn");
const $agentsBtn = document.getElementById("agents-btn");
const $newInput = document.getElementById("new-input");
const $newSend = document.getElementById("new-send");
const $newStop = document.getElementById("new-stop");
const $stop = document.getElementById("stop");
const $newAgentSelect = document.getElementById("new-agent-select");
const $agentsList = document.getElementById("agents-list");
const $agentFormPanel = document.getElementById("agent-form-panel");
const $agentFormTitle = document.getElementById("agent-form-title");
const $afName = document.getElementById("af-name");
const $afPrompt = document.getElementById("af-prompt");
const $afSkills = document.getElementById("af-skills");
const $afSave = document.getElementById("af-save");
const $afCancel = document.getElementById("af-cancel");
const $addAgentBtn = document.getElementById("add-agent-btn");

// 工具
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function renderMd(text) {
  return window.marked ? window.marked.parse(text) : text;
}

// 初始化
async function bootstrap() {
  const meRes = await fetch("/api/me", { credentials: "same-origin" });
  if (meRes.status === 401) {
    location.href = "/login.html";
    return;
  }
  me = await meRes.json();
  $who.textContent = me.username;
  await Promise.all([reloadAgents(), reloadSkills()]);
  await reloadSessions();
  showView("new");
}

// 视图切换
function showView(name) {
  currentView = name;
  document.getElementById("view-new").style.display = name === "new" ? "" : "none";
  document.getElementById("view-chat").style.display = name === "chat" ? "" : "none";
  document.getElementById("view-agents").style.display = name === "agents" ? "" : "none";

  $newMsgBtn.classList.toggle("primary", name !== "agents");
  $agentsBtn.classList.toggle("primary", name === "agents");

  if (name === "agents") renderAgents();
}

// 智能体与技能
async function reloadAgents() {
  const r = await fetch("/api/agents", { credentials: "same-origin" });
  agents = await r.json();
  populateAgentSelect();
}

async function reloadSkills() {
  const r = await fetch("/api/skills", { credentials: "same-origin" });
  skills = await r.json();
}

function populateAgentSelect() {
  $newAgentSelect.innerHTML = "";
  for (const a of agents) {
    const opt = document.createElement("option");
    opt.value = a.id;
    opt.textContent = a.name;
    $newAgentSelect.appendChild(opt);
  }
}

function getAgentName(id) {
  const a = agents.find((x) => x.id === id);
  return a ? a.name : "智能体";
}

// 会话
async function reloadSessions() {
  const res = await fetch("/api/sessions", { credentials: "same-origin" });
  sessions = await res.json();
  renderSidebar();
}

function renderSidebar() {
  $list.innerHTML = "";
  // 按 agent_name 分组
  const groups = {};
  for (const s of sessions) {
    const key = s.agent_name || "未分配";
    if (!groups[key]) groups[key] = [];
    groups[key].push(s);
  }
  for (const name of Object.keys(groups).sort()) {
    const group = el("div", "group" + (groupCollapsed[name] ? " collapsed" : ""));
    const header = el("div", "group-header", name);
    header.addEventListener("click", () => {
      groupCollapsed[name] = !groupCollapsed[name];
      group.classList.toggle("collapsed", groupCollapsed[name]);
    });
    group.appendChild(header);
    const itemsWrap = el("div", "group-items");
    for (const s of groups[name]) {
      const item = el("div", "item" + (s.id === currentSessionId ? " active" : ""));
      item.appendChild(el("span", "title", s.title));
      const del = el("span", "del", "✕");
      del.title = "删除会话";
      del.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm("删除这条会话?")) return;
        await fetch(`/api/sessions/${s.id}`, { method: "DELETE", credentials: "same-origin" });
        if (currentSessionId === s.id) { currentSessionId = null; showView("new"); }
        await reloadSessions();
      });
      item.appendChild(del);
      item.addEventListener("click", () => selectSession(s.id));
      itemsWrap.appendChild(item);
    }
    group.appendChild(itemsWrap);
    $list.appendChild(group);
  }
}

function clearMain() {
  $msgs.innerHTML = "";
  currentAssistantTurn = null;
}

async function selectSession(id) {
  currentSessionId = id;
  sending = false;
  $send.disabled = false;
  renderSidebar();
  showView("chat");
  clearMain();
  const res = await fetch(`/api/sessions/${id}/messages`, { credentials: "same-origin" });
  const events = await res.json();
  for (const evt of events) renderEvent(evt);
  $msgs.scrollTop = $msgs.scrollHeight;
}

// 渲染事件
function startAssistantTurn() {
  const sess = sessions.find((s) => s.id === currentSessionId);
  const agentName = sess ? getAgentName(sess.agent_id) : "智能体";
  const root = el("div", "msg assistant");
  const nameEl = el("div", "msg-name", agentName);
  root.appendChild(nameEl);
  const bubble = el("div", "bubble");
  root.appendChild(bubble);
  $msgs.appendChild(root);
  currentAssistantTurn = { root, bubble, text: "", tools: {} };
}

function ensureAssistantTurn() {
  if (!currentAssistantTurn) startAssistantTurn();
  return currentAssistantTurn;
}

function renderEvent(evt) {
  if (evt.type === "user_text") {
    const root = el("div", "msg user");
    const nameEl = el("div", "msg-name", me ? me.username : "用户");
    root.appendChild(nameEl);
    const bubble = el("div", "bubble", evt.text);
    root.appendChild(bubble);
    $msgs.appendChild(root);
    currentAssistantTurn = null;
    return;
  }
  if (evt.type === "assistant_text") {
    const t = ensureAssistantTurn();
    t.text += evt.text;
    t.bubble.innerHTML = renderMd(t.text);
    return;
  }
  if (evt.type === "assistant_thinking") {
    return;
  }
  if (evt.type === "tool_use") {
    const t = ensureAssistantTurn();
    const tool = el("div", "tool");
    tool.innerHTML = `<span class="tool-name">▶ ${evt.name}</span> ${escapeHtml(JSON.stringify(evt.input))}`;
    const resultEl = el("div", "tool");
    resultEl.style.display = "none";
    t.tools[evt.id] = { useEl: tool, resultEl };
    t.bubble.appendChild(tool);
    t.bubble.appendChild(resultEl);
    return;
  }
  if (evt.type === "tool_result") {
    const t = ensureAssistantTurn();
    const ref = t.tools[evt.tool_use_id];
    const content = typeof evt.content === "string" ? evt.content : JSON.stringify(evt.content);
    const target = ref ? ref.resultEl : el("div", "tool");
    target.style.display = "";
    target.textContent = (evt.is_error ? "✖ " : "✓ ") + content.slice(0, 2000);
    if (!ref) ensureAssistantTurn().bubble.appendChild(target);
    return;
  }
  if (evt.type === "result") {
    currentAssistantTurn = null;
    return;
  }
  if (evt.type === "error") {
    const t = ensureAssistantTurn();
    const errEl = el("div", "tool");
    errEl.style.color = "#cf222e";
    errEl.textContent = "错误: " + evt.message;
    t.bubble.appendChild(errEl);
    currentAssistantTurn = null;
    return;
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// 发送消息(通用)
async function doSend(text, agentId) {
  if (!text || sending) return;

  let sid = currentSessionId;
  if (!sid) {
    const r = await fetch("/api/sessions", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent_id: agentId ? parseInt(agentId) : null }), credentials: "same-origin",
    });
    const created = await r.json();
    sessions.unshift(created);
    sid = created.id;
    currentSessionId = sid;
    renderSidebar();
    showView("chat");
  }

  renderEvent({ type: "user_text", text });
  if ($input) $input.value = "";
  if ($newInput) $newInput.value = "";
  sending = true;
  if ($send) { $send.style.display = "none"; }
  if ($newSend) { $newSend.style.display = "none"; }
  if ($stop) { $stop.style.display = ""; }
  if ($newStop) { $newStop.style.display = ""; }

  try {
    const res = await fetch(`/api/sessions/${sid}/chat`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: text }), credentials: "same-origin",
    });
    if (!res.ok || !res.body) {
      renderEvent({ type: "error", message: `HTTP ${res.status}` });
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const events = buf.split("\n\n");
      buf = events.pop() ?? "";
      for (const block of events) {
        const line = block.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        try {
          renderEvent(JSON.parse(line.slice(6)));
          $msgs.scrollTop = $msgs.scrollHeight;
        } catch (_) { /* 忽略坏的事件 */ }
      }
    }
  } finally {
    sending = false;
    if ($send) { $send.style.display = ""; }
    if ($newSend) { $newSend.style.display = ""; }
    if ($stop) { $stop.style.display = "none"; }
    if ($newStop) { $newStop.style.display = "none"; }
    await reloadSessions();
  }
}

async function doStop() {
  if (!currentSessionId || !sending) return;
  await fetch(`/api/sessions/${currentSessionId}/stop`, {
    method: "POST", credentials: "same-origin",
  });
}

// 事件绑定
$send.addEventListener("click", () => doSend($input.value.trim()));
$input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    doSend($input.value.trim());
  }
});
$newSend.addEventListener("click", () => doSend($newInput.value.trim(), $newAgentSelect.value));
$newInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    doSend($newInput.value.trim(), $newAgentSelect.value);
  }
});
$stop.addEventListener("click", doStop);
$newStop.addEventListener("click", doStop);
$newMsgBtn.addEventListener("click", () => { currentSessionId = null; showView("new"); });
$logout.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  location.href = "/login.html";
});

// 智能体管理
let editingAgentId = null;

function renderAgents() {
  $agentsList.innerHTML = "";
  for (const a of agents) {
    const card = el("div", "agent-card");
    const info = el("div", "info");
    info.appendChild(el("span", "name", a.name));
    const meta = [];
    if (a.system_prompt) meta.push("有系统提示词");
    if (a.skills) meta.push(`技能: ${a.skills}`);
    if (a.is_default) meta.push("默认");
    info.appendChild(el("span", "meta", meta.join(" / ") || "无额外配置"));
    card.appendChild(info);
    const actions = el("div", "actions");
    const editBtn = el("button", "", "编辑");
    editBtn.addEventListener("click", () => openAgentForm(a));
    actions.appendChild(editBtn);
    if (!a.is_default) {
      const delBtn = el("button", "danger", "删除");
      delBtn.addEventListener("click", async () => {
        if (!confirm(`删除智能体 "${a.name}"?`)) return;
        await fetch(`/api/agents/${a.id}`, { method: "DELETE", credentials: "same-origin" });
        await reloadAgents();
        renderAgents();
      });
      actions.appendChild(delBtn);
    }
    card.appendChild(actions);
    $agentsList.appendChild(card);
  }
}

function renderSkillCheckboxes(selectedSkills) {
  $afSkills.innerHTML = "";
  const sel = new Set((selectedSkills || "").split(",").map((s) => s.trim()).filter(Boolean));
  for (const s of skills) {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = s.name;
    cb.checked = sel.has(s.name);
    label.appendChild(cb);
    label.appendChild(document.createTextNode(s.name));
    $afSkills.appendChild(label);
  }
}

function openAgentForm(agent) {
  editingAgentId = agent ? agent.id : null;
  $agentFormTitle.textContent = agent ? "编辑智能体" : "新建智能体";
  $afName.value = agent ? agent.name : "";
  $afPrompt.value = agent ? (agent.system_prompt || "") : "";
  renderSkillCheckboxes(agent ? agent.skills : "");
  $agentFormPanel.style.display = "";
}

function closeAgentForm() {
  editingAgentId = null;
  $agentFormPanel.style.display = "none";
}

$addAgentBtn.addEventListener("click", () => openAgentForm(null));
$afCancel.addEventListener("click", closeAgentForm);
$afSave.addEventListener("click", async () => {
  const checked = Array.from($afSkills.querySelectorAll("input:checked")).map((cb) => cb.value);
  const payload = {
    name: $afName.value.trim(),
    system_prompt: $afPrompt.value.trim() || null,
    skills: checked.join(","),
  };
  if (!payload.name) { alert("请输入名称"); return; }
  if (editingAgentId) {
    await fetch(`/api/agents/${editingAgentId}`, {
      method: "PATCH", headers: { "content-type": "application/json" },
      body: JSON.stringify(payload), credentials: "same-origin",
    });
  } else {
    await fetch("/api/agents", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(payload), credentials: "same-origin",
    });
  }
  await reloadAgents();
  closeAgentForm();
  renderAgents();
});

$agentsBtn.addEventListener("click", () => showView("agents"));

bootstrap();
