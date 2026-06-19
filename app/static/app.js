let loadedRooms = [];
let loadedDevicesList = [];

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  const responseText = await response.text();
  let payload = {};
  if (responseText) {
    try {
      payload = JSON.parse(responseText);
    } catch {
      payload = { error: responseText };
    }
  }
  if (!response.ok) {
    const error = new Error(payload.error || `Request failed (${response.status})`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function showPairingOverlay(message = "Łączenie z urządzeniem. To może chwilę potrwać.") {
  const overlay = document.querySelector("#pairing-overlay");
  const stage = document.querySelector("#pairing-loader-stage");
  const detail = document.querySelector("#pairing-loader-detail");
  if (overlay) {
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
  }
  if (stage) {
    stage.textContent = message;
  }
  if (detail) {
    detail.textContent = message;
  }
  document.body.classList.add("is-pairing");
}

function updatePairingOverlay(message) {
  const stage = document.querySelector("#pairing-loader-stage");
  const detail = document.querySelector("#pairing-loader-detail");
  if (stage) {
    stage.textContent = message;
  }
  if (detail) {
    detail.textContent = message;
  }
}

function resetPairingLog() {
  const log = document.querySelector("#pairing-loader-log");
  if (log) {
    log.innerHTML = "";
  }
}

function appendPairingLog(message) {
  const log = document.querySelector("#pairing-loader-log");
  if (!log) {
    return;
  }
  const item = document.createElement("li");
  item.textContent = message;
  log.appendChild(item);
}

function renderPairingLog(messages) {
  const log = document.querySelector("#pairing-loader-log");
  if (!log) {
    return;
  }
  log.innerHTML = "";
  messages.forEach((message) => appendPairingLog(message));
}

const delay = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

async function pollPairingJob(jobId) {
  let lastLogLength = 0;

  while (true) {
    const status = await requestJson(`/api/matter/pair/${jobId}`);
    updatePairingOverlay(status.message || "Parowanie w toku.");

    if (Array.isArray(status.log) && status.log.length !== lastLogLength) {
      renderPairingLog(status.log);
      lastLogLength = status.log.length;
    }

    if (status.status === "completed") {
      return status.result;
    }

    if (status.status === "failed") {
      throw new Error(status.error || status.message || "Parowanie nie powiodło się.");
    }

    await delay(1000);
  }
}

function hidePairingOverlay() {
  const overlay = document.querySelector("#pairing-overlay");
  if (overlay) {
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
  }
  document.body.classList.remove("is-pairing");
}

function formToObject(form) {
  const values = Object.fromEntries(new FormData(form).entries());
  if (typeof values.payload === "string" && values.payload.trim()) {
    try {
      values.payload = JSON.parse(values.payload);
    } catch {
      throw new Error("Payload musi być poprawnym JSON-em.");
    }
  }
  return values;
}

function getActivePairingPayload(form) {
  const values = Object.fromEntries(new FormData(form).entries());
  const qrCode = String(values.qr_code || "").trim();
  const pairingCode = String(values.pairing_code || "").trim();
  const method = qrCode ? "qr" : pairingCode ? "pairing_code" : values.pairing_method || "qr";

  if (qrCode.startsWith("matter://")) {
    const candidate = qrCode.slice("matter://".length).trim();
    if (candidate && /^\d+$/.test(candidate)) {
      return {
        name: values.name,
        vendor: values.vendor,
        endpoint: values.endpoint || "1",
        pairing_code: candidate,
      };
    }
    return {
      name: values.name,
      vendor: values.vendor,
      endpoint: values.endpoint || "1",
      qr_code: candidate,
    };
  }

  if (method === "qr") {
    return {
      name: values.name,
      vendor: values.vendor,
      endpoint: values.endpoint || "1",
      qr_code: values.qr_code || "",
    };
  }

  return {
    name: values.name,
    vendor: values.vendor,
    endpoint: values.endpoint || "1",
    pairing_code: values.pairing_code || "",
  };
}

function deviceCard(device) {
  const element = document.createElement("article");
  element.className = "device-card";
  const actions = Array.isArray(device.actions) ? device.actions : [];
  
  const room = loadedRooms.find(r => r.id === device.room_id);
  const roomNameBadge = room ? `<span class="badge" style="background: rgba(56, 189, 248, 0.12); color: var(--accent); border-color: rgba(56, 189, 248, 0.28); margin-left: 8px;">Pokój: ${room.name}</span>` : "";

  element.innerHTML = `
    <header>
      <div>
        <strong>${device.name}</strong> ${roomNameBadge}
        <div class="meta">${device.vendor} · ${device.device_type} · endpoint ${device.endpoint}</div>
      </div>
      <span class="badge">${device.status}</span>
    </header>
    <div class="meta">
      <span>ID: ${device.id}</span>
      <span>Node: ${device.node_id}</span>
      <span>Clusters: ${(device.clusters || []).join(", ")}</span>
    </div>
    <div class="meta">Stan: ${JSON.stringify(device.attributes || {})}</div>
    
    <div class="meta" style="display: flex; align-items: center; gap: 8px; margin-top: 6px;">
      <span>Pokój:</span>
      <select class="room-selector" style="border-radius: 8px; border: 1px solid var(--border); padding: 4px 8px; background: rgba(15, 23, 42, 0.75); color: var(--text); font-size: 0.85rem;">
        <option value="">-- Bez pokoju --</option>
        ${loadedRooms.map(r => `<option value="${r.id}" ${r.id === device.room_id ? 'selected' : ''}>${r.name}</option>`).join('')}
      </select>
    </div>

    <div class="device-actions" data-device-actions></div>
    <div class="actions" style="margin-top: 10px;">
      <button data-action="connect">Połącz</button>
      <button data-action="disconnect">Rozłącz</button>
      <button data-action="delete">Usuń</button>
    </div>
  `;

  element.querySelector(".room-selector").addEventListener("change", async (e) => {
    const selectedRoomId = e.target.value;
    try {
      await requestJson(`/api/devices/${device.id}/room`, {
        method: "POST",
        body: JSON.stringify({ room_id: selectedRoomId })
      });
      await loadDevices();
    } catch (error) {
      alert("Nie udało się przypisać pokoju: " + error.message);
    }
  });

  const deviceActionsContainer = element.querySelector("[data-device-actions]");
  if (actions.length > 0) {
    const title = document.createElement("div");
    title.className = "meta device-actions-title";
    title.textContent = "Dostępne akcje";
    deviceActionsContainer.appendChild(title);

    actions.forEach((action) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = action;
      button.addEventListener("click", async () => {
        try {
          const payload = buildActionPayload(action);
          if (payload === null) {
            return;
          }
          await sendCommand(device.id, action, payload);
        } catch (error) {
          alert(error.message);
        }
      });
      deviceActionsContainer.appendChild(button);
    });
  } else {
    deviceActionsContainer.textContent = "Brak zdefiniowanych akcji dla tego urządzenia.";
  }

  element.querySelector('[data-action="connect"]').addEventListener("click", () => updateStatus(device.id, "connect"));
  element.querySelector('[data-action="disconnect"]').addEventListener("click", () => updateStatus(device.id, "disconnect"));
  element.querySelector('[data-action="delete"]').addEventListener("click", () => removeDevice(device.id));
  return element;
}

function buildActionPayload(action) {
  if (action === "set_level") {
    const brightness = window.prompt("Podaj jasność 0-100", "50");
    if (brightness === null) {
      return null;
    }
    return { brightness: Number(brightness) };
  }

  if (action === "set_temperature") {
    const temperature = window.prompt("Podaj temperaturę", "21");
    if (temperature === null) {
      return null;
    }
    return { target_temperature: Number(temperature) };
  }

  return {};
}

function profileCard(profile) {
  const element = document.createElement("article");
  element.className = "device-card";
  element.innerHTML = `
    <header>
      <div>
        <strong>${profile.label}</strong>
        <div class="meta">${profile.device_type}</div>
      </div>
      <span class="badge">Matter</span>
    </header>
    <div class="meta">Clusters: ${(profile.clusters || []).join(", ")}</div>
  `;
  return element;
}

async function loadDevices() {
  const container = document.querySelector("#devices");
  container.innerHTML = "<p>Ładowanie...</p>";
  const data = await requestJson("/api/devices");
  loadedDevicesList = data.devices || [];

  // Optimize: if backend already returned actions, use them directly
  const needsActions = loadedDevicesList.some(device => !device.actions);
  let devicesWithActions;
  if (!needsActions) {
    devicesWithActions = loadedDevicesList;
  } else {
    devicesWithActions = await Promise.all(
      loadedDevicesList.map(async (device) => {
        try {
          const response = await requestJson(`/api/devices/${device.id}/actions`);
          return { ...device, actions: response.actions };
        } catch {
          return { ...device, actions: [] };
        }
      })
    );
  }

  container.innerHTML = "";

  if (devicesWithActions.length === 0) {
    container.innerHTML = "<p>Brak urządzeń. Dodaj pierwsze lub użyj parowania Matter.</p>";
    updateAutomationDevicesDropdowns();
    return;
  }

  devicesWithActions.forEach((device) => container.appendChild(deviceCard(device)));
  updateAutomationDevicesDropdowns();
}

async function updateStatus(deviceId, action) {
  await requestJson(`/api/devices/${deviceId}/${action}`, { method: "POST" });
  await loadDevices();
}

async function sendCommand(deviceId, action, payload) {
  await requestJson(`/api/devices/${deviceId}/command`, {
    method: "POST",
    body: JSON.stringify({ action, payload }),
  });
  await loadDevices();
}

async function removeDevice(deviceId) {
  await requestJson(`/api/devices/${deviceId}/delete`, { method: "POST" });
  await loadDevices();
}

async function setupForms() {
  const pairingForm = document.querySelector("#pair-device-form");
  const qrInput = document.querySelector("#qr-code-input");
  const pairingCodeInput = document.querySelector("#pairing-code-input");
  const pairingResolution = document.querySelector("#pairing-resolution");

  const refreshPairingMode = async () => {
    const payload = getActivePairingPayload(pairingForm);
    const selected = payload.qr_code ? "qr" : payload.pairing_code ? "pairing_code" : pairingForm.querySelector('input[name="pairing_method"]:checked')?.value || "qr";
    qrInput.disabled = selected !== "qr";
    pairingCodeInput.disabled = selected !== "pairing_code";

    if (payload.qr_code || payload.pairing_code) {
      pairingResolution.textContent = "Typ urządzenia zostanie ustalony przez realny kontroler podczas parowania.";
      return;
    }

    pairingResolution.textContent = "Wklej kod QR albo pairing code. Typ ustali kontroler Matter po stronie backendu.";
  };

  pairingForm.querySelectorAll('input[name="pairing_method"]').forEach((input) => {
    input.addEventListener("change", refreshPairingMode);
  });
  qrInput.addEventListener("input", refreshPairingMode);
  pairingCodeInput.addEventListener("input", refreshPairingMode);

  document.querySelector("#pair-device-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = getActivePairingPayload(form);
    const submitButton = form.querySelector('button[type="submit"]');

    try {
      submitButton.disabled = true;
      resetPairingLog();
      showPairingOverlay("Inicjalizacja parowania.");
      appendPairingLog("Zebrano dane parowania z formularza.");
      appendPairingLog(`Wybrany tryb: ${payload.qr_code ? "QR" : "pairing code"}.`);

      const start = await requestJson("/api/matter/pair", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      appendPairingLog(`Backend przyjął zadanie ${start.job_id}.`);
      appendPairingLog(start.message || "Oczekiwanie na kolejne etapy parowania.");

      const result = await pollPairingJob(start.job_id);
      const device = result?.device;

      if (!device) {
        appendPairingLog(`Backend zakończył job, ale nie zwrócił urządzenia: ${JSON.stringify(result || {})}`);
        throw new Error("Backend zakończył parowanie bez danych urządzenia.");
      }

      appendPairingLog(`Dodano urządzenie: ${device.device_type}.`);
      if (device.metadata) {
        const metadata = device.metadata;
        appendPairingLog(`Kontroler: ${metadata.controller || "unknown"}.`);
        appendPairingLog(`Metoda: ${metadata.pairing_method || "unknown"}, resolved_from: ${metadata.resolved_from || "unknown"}.`);
      }

      pairingResolution.textContent = `Dodano urządzenie: ${device.device_type}`;

      form.reset();
      qrInput.disabled = false;
      pairingCodeInput.disabled = true;
      await loadDevices();
    } catch (error) {
      appendPairingLog(`Błąd: ${error.message}`);
      if (error.payload && error.payload.resolved) {
        appendPairingLog(`Resolved: ${JSON.stringify(error.payload.resolved)}`);
      }
      if (error.message && error.message.toLowerCase().includes("timed out")) {
        appendPairingLog("Komisjonowanie przekroczyło limit czasu. Sprawdź, czy urządzenie jest w tej samej sieci i czy faktycznie potwierdza parowanie.");
      }
      pairingResolution.textContent = error.payload?.error || error.message;
      alert(error.message);
    } finally {
      hidePairingOverlay();
      submitButton.disabled = false;
    }
  });

  document.querySelector("#refresh-devices").addEventListener("click", loadDevices);
  document.querySelector("#refresh-profiles").addEventListener("click", loadProfiles);

  await refreshPairingMode();
}

async function loadProfiles() {
  const container = document.querySelector("#profiles");
  container.innerHTML = "<p>Ładowanie profili...</p>";
  const data = await requestJson("/api/matter/discover");
  container.innerHTML = "";

  data.profiles.forEach((profile) => container.appendChild(profileCard(profile)));
}

async function setupHealth() {
  try {
    const payload = await requestJson("/api/health");
    document.querySelector("#health-status").textContent = payload.status === "ok" ? "Online" : "Nieznany";
    document.querySelector("#health-detail").textContent = "API działa poprawnie.";
  } catch (error) {
    document.querySelector("#health-status").textContent = "Offline";
    document.querySelector("#health-detail").textContent = error.message;
  }
}

async function loadRooms() {
  try {
    const data = await requestJson("/api/rooms");
    loadedRooms = data.rooms || [];
    renderRooms();
  } catch (err) {
    console.error("Błąd ładowania pokojów", err);
  }
}

function renderRooms() {
  const container = document.querySelector("#rooms-list");
  if (!container) return;
  container.innerHTML = "";
  if (loadedRooms.length === 0) {
    container.innerHTML = "<p class='status-inline'>Brak pokojów. Dodaj nowy pokój powyżej.</p>";
    return;
  }
  loadedRooms.forEach(room => {
    const div = document.createElement("div");
    div.style.display = "flex";
    div.style.justifyContent = "space-between";
    div.style.alignItems = "center";
    div.style.padding = "10px 14px";
    div.style.background = "rgba(15, 23, 42, 0.5)";
    div.style.border = "1px solid var(--border)";
    div.style.borderRadius = "10px";
    div.innerHTML = `
      <span><strong>${room.name}</strong></span>
      <button type="button" class="btn-delete-room" style="padding: 6px 12px; font-size: 0.8rem; background: #ef4444; border: none; border-radius: 8px;">Usuń</button>
    `;
    div.querySelector(".btn-delete-room").addEventListener("click", async () => {
      if (confirm(`Czy na pewno chcesz usunąć pokój "${room.name}"?`)) {
        try {
          await requestJson(`/api/rooms/${room.id}/delete`, { method: "POST" });
          await loadRooms();
          await loadDevices();
        } catch (err) {
          alert("Nie udało się usunąć pokoju: " + err.message);
        }
      }
    });
    container.appendChild(div);
  });
}

function updateAutomationDevicesDropdowns() {
  const triggerSelect = document.querySelector("#automation-trigger-device");
  const actionSelect = document.querySelector("#automation-action-device");
  if (!triggerSelect || !actionSelect) return;

  const prevTriggerVal = triggerSelect.value;
  const prevActionVal = actionSelect.value;

  triggerSelect.innerHTML = "<option value=''>-- Wybierz urządzenie --</option>";
  actionSelect.innerHTML = "<option value=''>-- Wybierz urządzenie --</option>";

  loadedDevicesList.forEach(device => {
    const room = loadedRooms.find(r => r.id === device.room_id);
    const suffix = room ? ` (${room.name})` : "";
    
    const optTrigger = document.createElement("option");
    optTrigger.value = device.id;
    optTrigger.textContent = `${device.name}${suffix} [${device.device_type}]`;
    triggerSelect.appendChild(optTrigger);

    const optAction = document.createElement("option");
    optAction.value = device.id;
    optAction.textContent = `${device.name}${suffix} [${device.device_type}]`;
    actionSelect.appendChild(optAction);
  });

  if (prevTriggerVal) triggerSelect.value = prevTriggerVal;
  if (prevActionVal) {
    actionSelect.value = prevActionVal;
  } else {
    updateAutomationActionCommands();
  }
}

async function updateAutomationActionCommands() {
  const actionSelect = document.querySelector("#automation-action-device");
  const commandSelect = document.querySelector("#automation-action-command");
  if (!actionSelect || !commandSelect) return;

  const deviceId = actionSelect.value;
  commandSelect.innerHTML = "<option value=''>-- Najpierw wybierz urządzenie --</option>";

  if (!deviceId) return;

  try {
    const response = await requestJson(`/api/devices/${deviceId}/actions`);
    commandSelect.innerHTML = "";
    if (response.actions && response.actions.length > 0) {
      response.actions.forEach(action => {
        const opt = document.createElement("option");
        opt.value = action;
        opt.textContent = action;
        commandSelect.appendChild(opt);
      });
    } else {
      commandSelect.innerHTML = "<option value=''>Brak dostępnych akcji</option>";
    }
  } catch (err) {
    console.error("Błąd ładowania akcji urządzenia", err);
  }
}

async function loadAutomations() {
  const container = document.querySelector("#automations-list");
  if (!container) return;
  container.innerHTML = "<p>Ładowanie automatyzacji...</p>";
  try {
    const data = await requestJson("/api/automations");
    const automations = data.automations || [];
    container.innerHTML = "";
    if (automations.length === 0) {
      container.innerHTML = "<p class='status-inline'>Brak zdefiniowanych automatyzacji.</p>";
      return;
    }
    automations.forEach(aut => {
      const trDevice = loadedDevicesList.find(d => d.id === aut.trigger_device_id);
      const acDevice = loadedDevicesList.find(d => d.id === aut.action_device_id);

      const trName = trDevice ? trDevice.name : `Urządzenie [${aut.trigger_device_id.slice(0, 8)}]`;
      const acName = acDevice ? acDevice.name : `Urządzenie [${aut.action_device_id.slice(0, 8)}]`;

      const card = document.createElement("article");
      card.className = "device-card";
      card.innerHTML = `
        <header>
          <div>
            <strong>${aut.name}</strong>
            <div class="meta" style="margin-top: 4px;">
              Utworzono: ${new Date(aut.created_at).toLocaleString()}
            </div>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <span class="badge" style="background: ${aut.enabled ? 'rgba(52, 211, 153, 0.12)' : 'rgba(239, 68, 68, 0.12)'}; color: ${aut.enabled ? 'var(--good)' : '#ef4444'}; border-color: ${aut.enabled ? 'rgba(52, 211, 153, 0.28)' : 'rgba(239, 68, 68, 0.28)'};">
              ${aut.enabled ? 'Aktywna' : 'Wyłączona'}
            </span>
          </div>
        </header>
        <div class="meta" style="line-height: 1.5; margin-top: 6px;">
          <strong>Wyzwalacz:</strong> Jeśli <span style="color: var(--accent);">${trName}</span> zmieni atrybut <code>${aut.trigger_attribute}</code> na <code>${aut.trigger_value}</code>
        </div>
        <div class="meta" style="line-height: 1.5;">
          <strong>Akcja:</strong> Wyślij komendę <code>${aut.action_command}</code> z parametrami <code>${JSON.stringify(aut.action_payload)}</code> do <span style="color: var(--accent);">${acName}</span>
        </div>
        <div class="actions" style="margin-top: 10px;">
          <button class="btn-toggle-auto">${aut.enabled ? 'Wyłącz' : 'Włącz'}</button>
          <button class="btn-delete-auto" style="background: #ef4444;">Usuń</button>
        </div>
      `;

      card.querySelector(".btn-toggle-auto").addEventListener("click", async () => {
        try {
          await requestJson(`/api/automations/${aut.id}/toggle`, {
            method: "POST",
            body: JSON.stringify({ enabled: !aut.enabled })
          });
          await loadAutomations();
        } catch (err) {
          alert("Błąd przełączania stanu automatyzacji: " + err.message);
        }
      });

      card.querySelector(".btn-delete-auto").addEventListener("click", async () => {
        if (confirm(`Czy na pewno chcesz usunąć automatyzację "${aut.name}"?`)) {
          try {
            await requestJson(`/api/automations/${aut.id}/delete`, { method: "POST" });
            await loadAutomations();
          } catch (err) {
            alert("Błąd usuwania automatyzacji: " + err.message);
          }
        }
      });

      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = `<p class='status-inline' style='color: #ef4444;'>Błąd ładowania automatyzacji: ${err.message}</p>`;
  }
}

function smartParseValue(val) {
  const trimmed = String(val).trim();
  if (trimmed.toLowerCase() === "true") return true;
  if (trimmed.toLowerCase() === "false") return false;
  if (trimmed !== "" && !isNaN(trimmed)) return Number(trimmed);
  return trimmed;
}

function setupRoomAndAutomationEvents() {
  const createRoomForm = document.querySelector("#create-room-form");
  if (createRoomForm) {
    createRoomForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const nameInput = createRoomForm.querySelector('input[name="name"]');
      const name = nameInput.value.trim();
      if (!name) return;
      try {
        await requestJson("/api/rooms", {
          method: "POST",
          body: JSON.stringify({ name })
        });
        nameInput.value = "";
        await loadRooms();
        await loadDevices();
      } catch (err) {
        alert("Błąd podczas tworzenia pokoju: " + err.message);
      }
    });
  }

  const createAutomationForm = document.querySelector("#create-automation-form");
  if (createAutomationForm) {
    const actionDeviceSelect = document.querySelector("#automation-action-device");
    if (actionDeviceSelect) {
      actionDeviceSelect.addEventListener("change", updateAutomationActionCommands);
    }

    createAutomationForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = new FormData(createAutomationForm);
      const name = formData.get("name").trim();
      const trigger_device_id = formData.get("trigger_device_id");
      const trigger_attribute = formData.get("trigger_attribute").trim();
      const trigger_value_raw = formData.get("trigger_value").trim();
      const action_device_id = formData.get("action_device_id");
      const action_command = formData.get("action_command");
      const action_payload_raw = formData.get("action_payload").trim();

      if (!name || !trigger_device_id || !trigger_attribute || !trigger_value_raw || !action_device_id || !action_command) {
        alert("Proszę wypełnić wszystkie wymagane pola automatyzacji.");
        return;
      }

      let action_payload = {};
      if (action_payload_raw) {
        try {
          action_payload = JSON.parse(action_payload_raw);
        } catch (err) {
          alert("Payload akcji musi być poprawnym obiektem JSON (lub pozostaw pusty).");
          return;
        }
      }

      const trigger_value = smartParseValue(trigger_value_raw);

      try {
        await requestJson("/api/automations", {
          method: "POST",
          body: JSON.stringify({
            name,
            trigger_device_id,
            trigger_attribute,
            trigger_value,
            action_device_id,
            action_command,
            action_payload
          })
        });
        createAutomationForm.reset();
        if (actionDeviceSelect) {
          actionDeviceSelect.value = "";
          updateAutomationActionCommands();
        }
        await loadAutomations();
      } catch (err) {
        alert("Błąd podczas dodawania automatyzacji: " + err.message);
      }
    });
  }

  const refreshAutomationsBtn = document.querySelector("#refresh-automations");
  if (refreshAutomationsBtn) {
    refreshAutomationsBtn.addEventListener("click", loadAutomations);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  hidePairingOverlay();
  await setupHealth();
  await setupForms();
  await loadProfiles();
  
  setupRoomAndAutomationEvents();
  
  await loadRooms();
  await loadDevices();
  await loadAutomations();
});