let conversationId = null;
let apiKey = localStorage.getItem("agent_api_key") || "";

async function fetchJson(url, options = {}) {
  options.headers = options.headers || {};
  if (apiKey) {
    options.headers["X-API-Key"] = apiKey;
  }
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function renderCards(cards) {
  const wrap = el("div", "cards");
  cards.forEach((card) => {
    const node = el("div", "card");
    node.appendChild(el("strong", "", card.title || card.type));
    if (card.content) {
      const pre = el("pre");
      pre.textContent = card.content;
      node.appendChild(pre);
    }
    if (card.items) {
      const list = el("ul");
      card.items.forEach((item) => {
        const li = el("li", "", item);
        list.appendChild(li);
      });
      node.appendChild(list);
    }
    wrap.appendChild(node);
  });
  return wrap;
}

function addMessage(role, text, cards = []) {
  const container = document.querySelector("#messages");
  const msg = el("article", `message ${role}`);
  msg.appendChild(el("div", "", text));
  if (cards.length) {
    msg.appendChild(renderCards(cards));
  }
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
}

async function refreshDashboard() {
  const data = await fetchJson("/api/dashboard");
  const dash = document.querySelector("#dashboard");
  const runsPanel = document.querySelector("#runsPanel");
  const conversationsPanel = document.querySelector("#conversationsPanel");
  const templatesPanel = document.querySelector("#templatesPanel");
  const settingsPanel = document.querySelector("#settingsPanel");
  const jobsPanel = document.querySelector("#jobsPanel");
  dash.innerHTML = "";
  runsPanel.innerHTML = "";
  conversationsPanel.innerHTML = "";
  templatesPanel.innerHTML = "";
  settingsPanel.innerHTML = "";
  jobsPanel.innerHTML = "";

  const docs = el("div", "metric");
  docs.innerHTML = `<strong>الملفات المفهرسة</strong><div class="muted">${data.documents.length}</div>`;
  dash.appendChild(docs);

  const mem = el("div", "metric");
  mem.innerHTML = `<strong>الذكريات المحفوظة</strong><div class="muted">${data.memories.length}</div>`;
  dash.appendChild(mem);

  const tel = el("div", "metric");
  tel.innerHTML = `<strong>آخر تشغيلات</strong><div class="muted">${data.telemetry.length}</div>`;
  dash.appendChild(tel);

  const models = el("div", "metric");
  models.innerHTML = `<strong>النماذج</strong><div class="muted">${data.settings.default_chat_model}<br>${data.settings.code_model}<br>${data.settings.vision_model}</div>`;
  dash.appendChild(models);

  const internet = el("div", "metric");
  internet.innerHTML = `<strong>الإنترنت</strong><div class="muted">enabled: ${data.settings.internet_enabled}<br>downloads: ${data.settings.downloads_dir}<br>max: ${data.settings.max_download_size_mb} MB<br>provider: ${data.settings.search_provider}</div>`;
  dash.appendChild(internet);

  data.documents.slice(0, 8).forEach((doc) => {
    const item = el("div", "metric");
    item.innerHTML = `<div>${doc.path}</div><div class="muted">${doc.size_bytes} bytes</div>`;
    dash.appendChild(item);
  });

  data.runs.slice(0, 3).forEach((run) => {
    const box = el("div", "run");
    box.innerHTML = `
      <div class="run-title">${run.title}</div>
      <div class="muted">${run.mode} · ${run.status}</div>
      <div class="run-progress"><span style="width:${Math.round(run.progress * 100)}%"></span></div>
      <div class="muted">${run.summary || ""}</div>
    `;
    const list = el("ul");
    run.steps.forEach((step) => {
      const li = el("li", "", `${step.title} - ${step.status}${step.artifact_path ? ` - ${step.artifact_path}` : ""}`);
      list.appendChild(li);
    });
    box.appendChild(list);
    runsPanel.appendChild(box);
  });

  data.conversations.slice(0, 8).forEach((conversation) => {
    const box = el("div", "conversation");
    box.innerHTML = `<div><strong>${conversation.title}</strong></div><div class="muted">${conversation.last_message || ""}</div>`;
    const exportButton = el("button", "small-button", "تصدير");
    exportButton.addEventListener("click", async () => {
      try {
        const result = await fetchJson("/api/conversations/export", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ conversation_id: conversation.id }),
        });
        await navigator.clipboard.writeText(JSON.stringify(result, null, 2));
        addMessage("assistant", "تم نسخ المحادثة إلى الحافظة بصيغة JSON.");
      } catch (error) {
        addMessage("assistant", `تعذر تصدير المحادثة: ${error.message}`);
      }
    });
    box.appendChild(exportButton);
    conversationsPanel.appendChild(box);
  });

  data.templates.forEach((template) => {
    const box = el("div", "template");
    box.innerHTML = `<div><strong>${template.name}</strong></div><div class="muted">${template.description}</div>`;
    const button = el("button", "", "إنشاء");
    button.addEventListener("click", async () => {
      const targetDir = window.prompt("اكتب اسم المجلد الهدف داخل مساحة العمل", `generated/${template.id}`);
      if (!targetDir) return;
      try {
        const result = await fetchJson("/api/templates/apply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ template_id: template.id, target_dir: targetDir }),
        });
        addMessage("assistant", `تم إنشاء القالب ${template.name}`, [
          { type: "artifacts", title: "الملفات الناتجة", items: result.written || [] },
        ]);
        refreshDashboard();
      } catch (error) {
        addMessage("assistant", `تعذر إنشاء القالب: ${error.message}`);
      }
    });
    box.appendChild(button);
    templatesPanel.appendChild(box);
  });

  const settingsBox = el("div", "settings-box");
  settingsBox.innerHTML = `<div class="muted">default mode: ${data.saved_settings.default_mode || data.settings.default_mode}</div><div class="muted">permission: ${data.saved_settings.permission_level || 'none'}</div><div class="muted">internet enabled: ${String(data.settings.internet_enabled)}</div><div class="muted">api key enabled: ${String(data.settings.api_key_enabled)}</div>`;
  const apiKeyInput = document.createElement("input");
  apiKeyInput.className = "project-input";
  apiKeyInput.placeholder = "API Key (optional)";
  apiKeyInput.value = apiKey;
  const saveButton = el("button", "small-button", "حفظ الإعدادات الحالية");
  saveButton.addEventListener("click", async () => {
    try {
      const preferences = {
        default_mode: document.querySelector("#modeSelect").value,
        permission_level: document.querySelector("#permissionSelect").value,
        api_key: apiKeyInput.value.trim(),
      };
      apiKey = apiKeyInput.value.trim();
      localStorage.setItem("agent_api_key", apiKey);
      await fetchJson("/api/settings/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences }),
      });
      addMessage("assistant", "تم حفظ الإعدادات المحلية.");
      refreshDashboard();
    } catch (error) {
      addMessage("assistant", `تعذر حفظ الإعدادات: ${error.message}`);
    }
  });
  const importButton = el("button", "small-button", "استيراد محادثة");
  importButton.addEventListener("click", async () => {
    const raw = window.prompt("ألصق JSON الخاص بالمحادثة هنا");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      const result = await fetchJson("/api/conversations/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      addMessage("assistant", `تم استيراد المحادثة. عدد الرسائل: ${result.imported_messages}`);
      refreshDashboard();
    } catch (error) {
      addMessage("assistant", `تعذر استيراد المحادثة: ${error.message}`);
    }
  });
  settingsBox.appendChild(apiKeyInput);
  settingsBox.appendChild(saveButton);
  settingsBox.appendChild(importButton);
  settingsPanel.appendChild(settingsBox);

  data.jobs.slice(0, 8).forEach((job) => {
    const box = el("div", "run");
    box.innerHTML = `<div class="run-title">${job.kind}</div><div class="muted">${job.status}</div><div class="muted">${job.id}</div>`;
    jobsPanel.appendChild(box);
  });
}

async function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result);
      resolve(result.split(",")[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

document.querySelector("#chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#messageInput");
  const imageInput = document.querySelector("#imageInput");
  const mode = document.querySelector("#modeSelect").value;
  const permissionLevel = document.querySelector("#permissionSelect").value;
  const message = input.value.trim();
  if (!message) return;

  addMessage("user", message);
  input.value = "";

  const images = [];
  for (const file of imageInput.files) {
    images.push({ name: file.name, data_base64: await fileToBase64(file) });
  }
  imageInput.value = "";

  try {
    const result = await fetchJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, message, images, permission_level: permissionLevel, mode }),
    });
    conversationId = result.conversation_id;
    addMessage("assistant", result.answer, result.cards || []);
    refreshDashboard();
  } catch (error) {
    addMessage("assistant", `حدث خطأ أثناء الإرسال: ${error.message}`);
  }
});

document.querySelector("#reindexBtn").addEventListener("click", async () => {
  try {
    await fetchJson("/api/reindex", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    addMessage("assistant", "تمت إعادة فهرسة المعرفة المحلية بنجاح.");
    refreshDashboard();
  } catch (error) {
    addMessage("assistant", `تعذر إعادة الفهرسة: ${error.message}`);
  }
});

window.addEventListener("load", async () => {
  addMessage("assistant", "الوكيل جاهز. يمكنك سؤاله بالعربية، رفع صورة، أو تفعيل الأدوات المحلية عند الحاجة.");
  try {
    await fetchJson("/api/health");
    refreshDashboard();
  } catch (error) {
    addMessage("assistant", "تعذر الوصول إلى Ollama محلياً. شغّل التطبيق ثم أعد المحاولة.");
  }
});

document.querySelector("#buildProjectBtn").addEventListener("click", async () => {
  const description = document.querySelector("#messageInput").value.trim();
  const projectName = document.querySelector("#projectNameInput").value.trim();
  const targetDir = document.querySelector("#targetDirInput").value.trim() || `generated/${projectName || "new-project"}`;
  const allowExternal = document.querySelector("#allowExternalToggle").checked;
  const runAsync = document.querySelector("#runAsyncToggle").checked;
  if (!description) {
    addMessage("assistant", "اكتب وصف المشروع أولاً في صندوق الرسالة ثم اضغط بناء المشروع.");
    return;
  }
  addMessage("user", `Build full project: ${description}`);
  try {
    const result = await fetchJson("/api/projects/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description,
        project_name: projectName,
        target_dir: targetDir,
        allow_external: allowExternal,
        async: runAsync,
      }),
    });
    if (result.job_id) {
      addMessage("assistant", `تم وضع مهمة البناء في الخلفية. job: ${result.job_id}`);
    } else {
      conversationId = result.conversation_id;
      addMessage("assistant", `تم إنشاء المشروع ${result.project_name} داخل ${result.target_dir}`, result.cards || []);
    }
    refreshDashboard();
  } catch (error) {
    addMessage("assistant", `تعذر بناء المشروع: ${error.message}`);
  }
});

document.querySelector("#executeProjectBtn").addEventListener("click", async () => {
  const targetDir = document.querySelector("#targetDirInput").value.trim() || "generated/new-project";
  const allowExternal = document.querySelector("#allowExternalToggle").checked;
  const runAsync = document.querySelector("#runAsyncToggle").checked;
  addMessage("user", `Execute project pipeline: ${targetDir}`);
  try {
    const result = await fetchJson("/api/projects/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_dir: targetDir,
        allow_external: allowExternal,
        actions: ["install", "run", "smoke"],
        async: runAsync,
      }),
    });
    if (result.job_id) {
      addMessage("assistant", `تم وضع مهمة التنفيذ في الخلفية. job: ${result.job_id}`);
    } else {
      conversationId = result.conversation_id;
      addMessage("assistant", `نتيجة التنفيذ: ${result.status}`, result.cards || []);
    }
    refreshDashboard();
  } catch (error) {
    addMessage("assistant", `تعذر تنفيذ المشروع: ${error.message}`);
  }
});
