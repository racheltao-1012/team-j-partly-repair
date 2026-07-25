const state = {
  vehicles: [],
  assessment: null,
  items: [],
  catalogueParts: [],
  selectedIndex: -1,
  currentDiagramId: null,
  diagramMeta: {},
  caseId: null,
  visionStatus: null,
  photoAssessment: null,
  previewUrls: [],
  supplierQuotes: {},
  supplierQuoteLoads: {},
  quoteSequence: 0,
};

const elements = {
  apiStatus: document.querySelector("#apiStatus"),
  vehicleSelect: document.querySelector("#vehicleSelect"),
  catalogueUpdatePanel: document.querySelector("#catalogueUpdatePanel"),
  existingCatalogueFile: document.querySelector("#existingCatalogueFile"),
  existingCatalogueFileName: document.querySelector("#existingCatalogueFileName"),
  importCatalogueButton: document.querySelector("#importCatalogueButton"),
  existingCatalogueMessage: document.querySelector("#existingCatalogueMessage"),
  vinInput: document.querySelector("#vinInput"),
  trimInput: document.querySelector("#trimInput"),
  analyseButton: document.querySelector("#analyseButton"),
  toggleAddVehicleButton: document.querySelector("#toggleAddVehicleButton"),
  closeAddVehicleButton: document.querySelector("#closeAddVehicleButton"),
  addVehicleForm: document.querySelector("#addVehicleForm"),
  newMake: document.querySelector("#newMake"),
  newModel: document.querySelector("#newModel"),
  newYear: document.querySelector("#newYear"),
  newTrim: document.querySelector("#newTrim"),
  newVin: document.querySelector("#newVin"),
  catalogueFile: document.querySelector("#catalogueFile"),
  catalogueFileName: document.querySelector("#catalogueFileName"),
  createVehicleButton: document.querySelector("#createVehicleButton"),
  addVehicleMessage: document.querySelector("#addVehicleMessage"),
  localPartOptions: document.querySelector("#localPartOptions"),
  setupError: document.querySelector("#setupError"),
  visionModeBadge: document.querySelector("#visionModeBadge"),
  photoFiles: document.querySelector("#photoFiles"),
  photoFileNames: document.querySelector("#photoFileNames"),
  impactHint: document.querySelector("#impactHint"),
  guidedControls: document.querySelector("#guidedControls"),
  guidedVisiblePart: document.querySelector("#guidedVisiblePart"),
  guidedDamageType: document.querySelector("#guidedDamageType"),
  guidedSeverity: document.querySelector("#guidedSeverity"),
  guidedSeverityValue: document.querySelector("#guidedSeverityValue"),
  photoPreviews: document.querySelector("#photoPreviews"),
  photoHelp: document.querySelector("#photoHelp"),
  workspace: document.querySelector("#workspace"),
  photoEvidenceCard: document.querySelector("#photoEvidenceCard"),
  photoRunBadge: document.querySelector("#photoRunBadge"),
  photoEvidenceMeta: document.querySelector("#photoEvidenceMeta"),
  photoEvidenceGallery: document.querySelector("#photoEvidenceGallery"),
  photoWarnings: document.querySelector("#photoWarnings"),
  vehicleTitle: document.querySelector("#vehicleTitle"),
  vehicleSubtitle: document.querySelector("#vehicleSubtitle"),
  candidateCount: document.querySelector("#candidateCount"),
  oemCount: document.querySelector("#oemCount"),
  impactCount: document.querySelector("#impactCount"),
  reviewProgress: document.querySelector("#reviewProgress"),
  reviewProgressText: document.querySelector("#reviewProgressText"),
  assessmentRows: document.querySelector("#assessmentRows"),
  reviewEmpty: document.querySelector("#reviewEmpty"),
  saveButton: document.querySelector("#saveButton"),
  exportButton: document.querySelector("#exportButton"),
  addPartButton: document.querySelector("#addPartButton"),
  saveMessage: document.querySelector("#saveMessage"),
  diagramTitle: document.querySelector("#diagramTitle"),
  diagramIdBadge: document.querySelector("#diagramIdBadge"),
  diagramEmpty: document.querySelector("#diagramEmpty"),
  diagramStage: document.querySelector("#diagramStage"),
  diagramImage: document.querySelector("#diagramImage"),
  hotspotOverlay: document.querySelector("#hotspotOverlay"),
  impactChecklist: document.querySelector("#impactChecklist"),
  supplierModeBadge: document.querySelector("#supplierModeBadge"),
  supplierEmpty: document.querySelector("#supplierEmpty"),
  supplierComparison: document.querySelector("#supplierComparison"),
  historyBadge: document.querySelector("#historyBadge"),
  historyContent: document.querySelector("#historyContent"),
  disclaimerText: document.querySelector("#disclaimerText"),
  toast: document.querySelector("#toast"),
};

const decisionOptions = [
  "Pending",
  "Confirm",
  "Reject",
  "Needs inspection",
  "Edit part",
];

const rejectionOptions = [
  "",
  "Part is not damaged",
  "Wrong catalogue part",
  "Wrong vehicle variant",
  "More photos required",
  "Repair instead of replace",
  "Other",
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
    ...options,
  });
  let payload;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }
  if (!response.ok) {
    const message = payload?.detail || payload || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

function setApiStatus(connected, label) {
  elements.apiStatus.className = `status-pill ${connected ? "connected" : "disconnected"}`;
  elements.apiStatus.innerHTML = `<span class="status-dot"></span>${escapeHtml(label)}`;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => {
    elements.toast.classList.add("hidden");
  }, 3500);
}

function updateFilePicker(input, output, plural = false) {
  const files = Array.from(input.files || []);
  if (!files.length) {
    output.textContent = plural ? "No files chosen" : "No file chosen";
    return;
  }
  if (files.length === 1) {
    output.textContent = files[0].name;
    return;
  }
  output.textContent = `${files.length} files selected`;
}

function vehicleDisplay(vehicle) {
  const identity = [
    vehicle.year,
    vehicle.make,
    vehicle.model,
    vehicle.trim,
  ].filter(Boolean).join(" ");
  return identity || vehicle.slug;
}

async function initialise() {
  try {
    state.visionStatus = await request("/api/v1/photo-assessments/status");
    renderVisionStatus();
    const health = await request("/api/health");
    const usingJsonFallback = health.vehicle_data_source === "json_fallback";
    const statusLabel = health.partly_api_connected
      ? `${health.vehicle_count} vehicles · Partly live`
      : usingJsonFallback
        ? `${health.vehicle_count} vehicles · JSON fallback`
        : `${health.vehicle_count} local vehicles · Partly offline`;
    setApiStatus(health.partly_api_connected, statusLabel);
    await refreshVehicles();
    if (!health.partly_api_connected) {
      elements.setupError.textContent = usingJsonFallback
        ? (
          "Partly API is offline. Vehicle identities were loaded from "
          + "data/vehicles.json. Live OEM parts and diagrams require Partly API."
        )
        : (
          "Partly API is offline, but local vehicles and imported catalogues still work."
        );
      elements.setupError.classList.remove("hidden");
    }
  } catch (error) {
    setApiStatus(false, "Unified API unavailable");
    elements.vehicleSelect.innerHTML = '<option value="">API unavailable</option>';
    elements.setupError.textContent = error.message;
    elements.setupError.classList.remove("hidden");
  }
}

function renderVisionStatus() {
  const configured = Boolean(state.visionStatus?.configured);
  elements.visionModeBadge.textContent = configured
    ? `Live vision · ${state.visionStatus.model}`
    : "Guided demo · no vision model";
  elements.visionModeBadge.classList.toggle("available", configured);
  elements.guidedControls.classList.toggle("hidden", configured);
  elements.photoHelp.textContent = configured
    ? (
      "Uploaded photos will be sent to the configured vision provider. "
      + "Visible results remain candidates until technician confirmation."
    )
    : (
      "No real image model is configured. The guided demo uses your entered "
      + "visible part as the propagation seed and labels it as manual."
    );
  updateAnalyseAvailability();
}

function updateAnalyseAvailability() {
  const hasVehicle = Boolean(selectedVehicle());
  const hasPhotos = Boolean((elements.photoFiles.files || []).length);
  const hasInputForMode = Boolean(
    state.visionStatus?.configured
    || elements.guidedVisiblePart.value.trim(),
  );
  elements.analyseButton.disabled = !(
    hasVehicle && hasPhotos && hasInputForMode
  );
}

function renderPhotoPreviews() {
  updateFilePicker(elements.photoFiles, elements.photoFileNames, true);
  state.previewUrls.forEach((url) => URL.revokeObjectURL(url));
  state.previewUrls = [];
  const files = Array.from(elements.photoFiles.files || []).slice(0, 4);
  if ((elements.photoFiles.files || []).length > 4) {
    showToast("Only the first 4 photos will be used");
  }
  elements.photoPreviews.innerHTML = files.map((file, index) => {
    const url = URL.createObjectURL(file);
    state.previewUrls.push(url);
    return `<figure>
      <img src="${escapeHtml(url)}" alt="Photo ${index + 1} preview">
      <figcaption>${index + 1}. ${escapeHtml(file.name)}</figcaption>
    </figure>`;
  }).join("");
  elements.analyseButton.querySelector("span").textContent = files.length
    ? `Analyse ${files.length} photo${files.length === 1 ? "" : "s"}`
    : "Upload photos to analyse";
  updateAnalyseAvailability();
}

elements.photoFiles.addEventListener("change", renderPhotoPreviews);
elements.guidedVisiblePart.addEventListener("input", updateAnalyseAvailability);
elements.guidedSeverity.addEventListener("input", () => {
  elements.guidedSeverityValue.textContent = (
    `${Math.round(Number(elements.guidedSeverity.value) * 100)}%`
  );
});

async function refreshVehicles(selectId = "") {
  state.vehicles = await request("/api/v1/vehicles");
  const optionMarkup = (vehicle) => (
    `<option value="${escapeHtml(vehicle.id)}">`
    + `${escapeHtml(vehicleDisplay(vehicle))}`
    + "</option>"
  );
  elements.vehicleSelect.innerHTML = [
    '<option value="">Select a vehicle…</option>',
    [...state.vehicles]
      .sort((left, right) => vehicleDisplay(left).localeCompare(vehicleDisplay(right)))
      .map(optionMarkup)
      .join(""),
  ].join("");
  elements.vehicleSelect.disabled = false;
  if (selectId && state.vehicles.some((vehicle) => vehicle.id === selectId)) {
    elements.vehicleSelect.value = selectId;
    elements.vehicleSelect.dispatchEvent(new Event("change"));
  }
}

function selectedVehicle() {
  return state.vehicles.find((item) => item.id === elements.vehicleSelect.value);
}

function renderCapabilities(vehicle) {
  if (!vehicle) {
    elements.catalogueUpdatePanel.classList.add("hidden");
    return;
  }
  elements.catalogueUpdatePanel.classList.toggle(
    "hidden",
    vehicle.source !== "local_catalogue",
  );
  elements.existingCatalogueMessage.textContent = "";
  elements.existingCatalogueFile.value = "";
  updateFilePicker(
    elements.existingCatalogueFile,
    elements.existingCatalogueFileName,
  );
  elements.importCatalogueButton.disabled = true;
}

elements.vehicleSelect.addEventListener("change", () => {
  const vehicle = selectedVehicle();
  updateAnalyseAvailability();
  renderCapabilities(vehicle);
  if (vehicle?.source === "local_catalogue") {
    elements.trimInput.value = vehicle.trim || "";
    elements.vinInput.value = vehicle.vin || "";
  }
  elements.setupError.classList.add("hidden");
});

elements.analyseButton.addEventListener("click", loadAssessment);

elements.toggleAddVehicleButton.addEventListener("click", () => {
  elements.addVehicleForm.classList.toggle("hidden");
});

elements.closeAddVehicleButton.addEventListener("click", () => {
  elements.addVehicleForm.classList.add("hidden");
});

elements.addVehicleForm.addEventListener("submit", createLocalVehicle);
elements.existingCatalogueFile.addEventListener("change", () => {
  updateFilePicker(
    elements.existingCatalogueFile,
    elements.existingCatalogueFileName,
  );
  elements.importCatalogueButton.disabled = !elements.existingCatalogueFile.files[0];
});
elements.catalogueFile.addEventListener("change", () => {
  updateFilePicker(elements.catalogueFile, elements.catalogueFileName);
});
elements.importCatalogueButton.addEventListener("click", importExistingCatalogue);

async function importExistingCatalogue() {
  const vehicle = selectedVehicle();
  const file = elements.existingCatalogueFile.files[0];
  if (!vehicle || vehicle.source !== "local_catalogue" || !file) return;
  elements.importCatalogueButton.disabled = true;
  elements.importCatalogueButton.textContent = "Importing…";
  elements.existingCatalogueMessage.textContent = "";
  try {
    const form = new FormData();
    form.append("file", file);
    const result = await request(
      `/api/v1/catalogues/import?vehicle_id=${encodeURIComponent(vehicle.id)}`,
      { method: "POST", body: form },
    );
    await refreshVehicles(vehicle.id);
    elements.existingCatalogueMessage.textContent = (
      `${result.created_count} added, ${result.updated_count} updated; `
      + `${result.total_part_count} parts now available.`
    );
    showToast(`${result.imported_count} catalogue rows imported`);
  } catch (error) {
    elements.existingCatalogueMessage.textContent = error.message;
  } finally {
    elements.importCatalogueButton.textContent = "Import CSV";
    elements.importCatalogueButton.disabled = !elements.existingCatalogueFile.files[0];
  }
}

async function createLocalVehicle(event) {
  event.preventDefault();
  elements.createVehicleButton.disabled = true;
  elements.createVehicleButton.textContent = "Adding vehicle…";
  elements.addVehicleMessage.textContent = "";
  try {
    const vehicle = await request("/api/v1/vehicles", {
      method: "POST",
      body: JSON.stringify({
        make: elements.newMake.value.trim(),
        model: elements.newModel.value.trim(),
        year: Number(elements.newYear.value),
        trim: elements.newTrim.value.trim(),
        vin: elements.newVin.value.trim(),
      }),
    });
    const file = elements.catalogueFile.files[0];
    let importMessage = "Vehicle saved without an OEM catalogue.";
    if (file) {
      elements.createVehicleButton.textContent = "Importing catalogue…";
      const form = new FormData();
      form.append("file", file);
      const result = await request(
        `/api/v1/catalogues/import?vehicle_id=${encodeURIComponent(vehicle.id)}`,
        { method: "POST", body: form },
      );
      importMessage = `${result.imported_count} OEM parts imported.`;
    }
    await refreshVehicles(vehicle.id);
    elements.addVehicleMessage.textContent = importMessage;
    elements.addVehicleForm.reset();
    updateFilePicker(elements.catalogueFile, elements.catalogueFileName);
    elements.newYear.value = "2022";
    elements.addVehicleForm.classList.add("hidden");
    showToast(`New vehicle added. ${importMessage}`);
  } catch (error) {
    elements.addVehicleMessage.textContent = error.message;
  } finally {
    elements.createVehicleButton.disabled = false;
    elements.createVehicleButton.textContent = "Add vehicle and import catalogue";
  }
}

async function loadAssessment() {
  const vehicleId = elements.vehicleSelect.value;
  if (!vehicleId) return;
  const photoFiles = Array.from(elements.photoFiles.files || []).slice(0, 4);
  if (!photoFiles.length) {
    elements.setupError.textContent = (
      "Upload at least one photo. Vehicle selection never generates a "
      + "fixed damage result."
    );
    elements.setupError.classList.remove("hidden");
    return;
  }
  if (
    !state.visionStatus?.configured
    && !elements.guidedVisiblePart.value.trim()
  ) {
    elements.setupError.textContent = (
      "Enter the technician-visible part for the clearly labelled guided "
      + "demo, or configure the vision model for real photo analysis."
    );
    elements.setupError.classList.remove("hidden");
    return;
  }
  elements.analyseButton.disabled = true;
  elements.analyseButton.querySelector("span").textContent = "Analysing photos…";
  elements.setupError.classList.add("hidden");
  state.caseId = null;
  elements.exportButton.disabled = true;

  try {
    const form = new FormData();
    form.append("vehicle_id", vehicleId);
    photoFiles.forEach((file) => form.append("files", file));
    form.append("impact_hint", elements.impactHint.value);
    const mode = state.visionStatus?.configured ? "vision" : "guided";
    form.append("mode", mode);
    form.append("guided_visible_part", elements.guidedVisiblePart.value.trim());
    form.append("guided_damage_type", elements.guidedDamageType.value);
    form.append("guided_severity", elements.guidedSeverity.value);
    const payload = await request("/api/v1/photo-assessments/analyse", {
      method: "POST",
      body: form,
    });
    state.assessment = payload;
    state.photoAssessment = payload.photo_assessment || null;
    state.items = payload.items.map((item) => ({ ...item }));
    state.catalogueParts = payload.catalogue_parts || [];
    state.supplierQuotes = {};
    state.supplierQuoteLoads = {};
    state.quoteSequence = 0;
    elements.localPartOptions.innerHTML = state.catalogueParts.map((part) => (
      `<option value="${escapeHtml(part.part_name)}">`
      + `${escapeHtml(part.oem_number)}`
      + `${part.category ? ` · ${escapeHtml(part.category)}` : ""}`
      + "</option>"
    )).join("");
    state.selectedIndex = -1;
    state.currentDiagramId = null;
    state.diagramMeta = {};
    renderAssessment();
    renderHistory();
    elements.workspace.classList.remove("hidden");
    elements.workspace.scrollIntoView({ behavior: "smooth", block: "start" });
    const firstDiagramIndex = state.items.findIndex((item) => item.diagram_id);
    if (firstDiagramIndex >= 0) selectRow(firstDiagramIndex);
  } catch (error) {
    elements.setupError.textContent = error.message;
    elements.setupError.classList.remove("hidden");
  } finally {
    elements.analyseButton.querySelector("span").textContent = (
      `Analyse ${photoFiles.length} photo${photoFiles.length === 1 ? "" : "s"}`
    );
    updateAnalyseAvailability();
  }
}

function renderAssessment() {
  const vehicle = state.assessment.vehicle || {};
  const summary = state.assessment.summary || {};
  const vehicleId = vehicle.id || elements.vehicleSelect.value;

  elements.vehicleTitle.textContent = vehicleDisplay(vehicle);
  elements.vehicleSubtitle.textContent = [
    vehicle.data_source === "json_fallback"
      ? "JSON vehicle snapshot"
      : vehicle.source === "partly"
        ? "Partly live data"
        : "Local catalogue data",
    vehicle.diagram_count != null ? `${vehicle.diagram_count} diagrams` : "",
    vehicle.part_count != null ? `${vehicle.part_count} catalogue parts` : "",
  ].filter(Boolean).join(" · ");
  elements.candidateCount.textContent = summary.ai_candidate_count ?? 0;
  elements.oemCount.textContent = summary.catalogue_matches ?? 0;
  elements.impactCount.textContent = (
    Number(summary.impact_check_count || 0)
    + Number(summary.historical_check_count || 0)
  );
  elements.disclaimerText.textContent = state.assessment.disclaimer;
  elements.reviewEmpty.textContent = (
    "No visible damage candidate was found in this photo run. Try clearer "
    + "angles or add a technician-observed part."
  );
  renderChecklist(state.assessment.impact_checklist || []);
  renderPhotoEvidence();
  renderTable();
  renderSupplierComparison();
  updateProgress();
}

function clamp01(value) {
  return Math.max(0, Math.min(1, Number(value) || 0));
}

function renderPhotoEvidence() {
  const photo = state.photoAssessment;
  elements.photoEvidenceCard.classList.toggle("hidden", !photo);
  if (!photo) return;

  elements.photoRunBadge.textContent = (
    photo.provider === "technician_guided_demo"
      ? "Guided demo · manual seed"
      : `${photo.provider} · ${photo.model}`
  );
  elements.photoEvidenceMeta.innerHTML = [
    ["Impact zone", photo.impact_zone || "unknown"],
    ["Direction", photo.impact_direction || "unknown"],
    ["Visual severity", `${Math.round((photo.impact_severity || 0) * 100)}%`],
    ["Usable photos", photo.photos_are_usable ? "Yes" : "Review required"],
  ].map(([label, value]) => (
    `<span><b>${escapeHtml(label)}</b>${escapeHtml(value)}</span>`
  )).join("");

  elements.photoEvidenceGallery.innerHTML = (photo.images || []).map((image, index) => {
    const evidenceItems = state.items.filter(
      (item) => item.evidence_image_id === image.image_id
    );
    const detections = evidenceItems.filter(
      (item) => item.evidence_image_id === image.image_id && item.evidence_box
    );
    const overlays = detections.map((item) => {
      const box = item.evidence_box;
      const x1 = clamp01(box.x1);
      const y1 = clamp01(box.y1);
      const x2 = clamp01(box.x2);
      const y2 = clamp01(box.y2);
      return `<div class="evidence-box" style="
        left:${Math.min(x1, x2) * 100}%;
        top:${Math.min(y1, y2) * 100}%;
        width:${Math.abs(x2 - x1) * 100}%;
        height:${Math.abs(y2 - y1) * 100}%;">
        <span>${escapeHtml(item.raw_part_name)} · ${escapeHtml(item.damage_type)}</span>
      </div>`;
    }).join("");
    return `<figure>
      <div class="evidence-image-stage">
        <img src="${escapeHtml(image.url)}" alt="Uploaded vehicle evidence ${index + 1}">
        ${overlays}
      </div>
      <figcaption>Photo ${index + 1} · ${
        photo.provider === "technician_guided_demo"
          ? `${evidenceItems.length} manual seed · no model box`
          : `${detections.length} visible candidate${detections.length === 1 ? "" : "s"}`
      }</figcaption>
    </figure>`;
  }).join("");

  const warnings = photo.quality_warnings || [];
  elements.photoWarnings.innerHTML = warnings.length
    ? warnings.map((warning) => `<p>${escapeHtml(warning)}</p>`).join("")
    : "<p>No image-quality warning was returned.</p>";
}

function renderChecklist(items) {
  if (!items.length) {
    elements.impactChecklist.innerHTML = (
      '<p class="muted">No rule-based impact path matched the returned damage names.</p>'
    );
    return;
  }
  elements.impactChecklist.innerHTML = items.map((item) => (
    `<div class="checklist-item">
      <b>${escapeHtml(item.damage_area)}</b>
      <span>Inspect: ${escapeHtml(item.inspect.join(", "))}</span>
      ${item.probability != null
        ? `<small>${Math.round(item.probability * 100)}% ${escapeHtml(item.probability_band)} · ${escapeHtml((item.path || []).join(" → "))}</small>`
        : ""}
    </div>`
  )).join("");
}

function confidenceMarkup(value, item = {}) {
  if (value == null) {
    const label = item.source === "manual" ? "Technician seed" : "No model score";
    return `<div class="confidence"><strong>—</strong><div class="cell-subtitle">${escapeHtml(label)}</div></div>`;
  }
  const percentage = Math.round(value * 100);
  const label = item.source === "impact_path"
    ? `${item.probability_band || "estimated"} inspection likelihood`
    : item.source === "historical_case"
      ? "Similar-case relevance"
      : "Visible-evidence confidence";
  return `<div class="confidence">
    <strong>${percentage}%</strong>
    <div class="confidence-bar"><i style="width:${percentage}%"></i></div>
    <div class="cell-subtitle">${escapeHtml(label)}</div>
  </div>`;
}

function optionMarkup(options, selected) {
  return options.map((option) => (
    `<option value="${escapeHtml(option)}" ${option === selected ? "selected" : ""}>`
    + `${escapeHtml(option || "Select reason…")}</option>`
  )).join("");
}

function sourceLabel(source) {
  return {
    ai_prediction: "AI candidate",
    visible_damage: "Visible damage",
    impact_path: "Impact check",
    historical_case: "Similar-case check",
    catalogue_candidate: "Catalogue candidate",
    manual: "Technician-added",
  }[source] || source;
}

function renderTable() {
  elements.reviewEmpty.classList.toggle("hidden", state.items.length > 0);
  elements.assessmentRows.innerHTML = state.items.map((item, index) => {
    const isManual = item.source === "manual";
    const rejectHidden = item.technician_decision === "Reject" ? "" : "hidden";
    const selected = index === state.selectedIndex ? "selected" : "";
    const partName = escapeHtml(item.predicted_part_name || "Unresolved part");
    const rawName = escapeHtml(item.raw_part_name || "Technician entry");
    const detail = [
      item.damage_type,
      item.severity != null ? `severity ${Math.round(item.severity * 100)}%` : "",
    ].filter(Boolean).join(" · ");
    const path = (item.propagation_path || []).join(" → ");
    return `<tr data-index="${index}" class="${selected}">
      <td>
        <span class="source-badge ${escapeHtml(item.source)}">${escapeHtml(sourceLabel(item.source))}</span>
        ${isManual
          ? `<input class="manual-name" data-field="raw_part_name" value="${rawName}" placeholder="Damage area">`
          : `<div class="cell-title">${rawName}</div>`}
        ${detail ? `<div class="damage-detail">${escapeHtml(detail)}</div>` : ""}
        <div class="cell-subtitle">${escapeHtml(item.ai_action || "")}</div>
        ${item.reason ? `<div class="reason-text">${escapeHtml(item.reason)}</div>` : ""}
      </td>
      <td>
        ${isManual
          ? `<input data-field="predicted_part_name" list="localPartOptions" value="${partName}" placeholder="Search or enter part name">`
          : `<div class="cell-title">${partName}</div>`}
        <div class="diagram-link">${item.diagram_id ? `Diagram ${escapeHtml(item.diagram_id)}` : "No diagram"}</div>
        ${path ? `<div class="path-text">${escapeHtml(path)}</div>` : ""}
      </td>
      <td class="oem-cell">
        ${isManual
          ? `<label class="manual-oem-field">
              <span>OEM</span>
              <input data-field="oem_number" value="${escapeHtml(item.oem_number || "")}" placeholder="Enter exact number">
            </label>`
          : `<div class="oem-number ${item.oem_number ? "" : "missing"}">
              <span>OEM</span>
              <strong>${escapeHtml(item.oem_number || "Not resolved")}</strong>
            </div>`}
      </td>
      <td>${confidenceMarkup(item.ai_confidence, item)}</td>
      <td>
        <select data-field="technician_decision">
          ${optionMarkup(decisionOptions, item.technician_decision)}
        </select>
        <select class="reject-reason ${rejectHidden}" data-field="rejection_reason">
          ${optionMarkup(rejectionOptions, item.rejection_reason)}
        </select>
      </td>
      <td>
        <div class="table-control">
          <input data-field="corrected_part_name" value="${escapeHtml(item.corrected_part_name || "")}" placeholder="Corrected part (if needed)">
          <textarea data-field="technician_note" placeholder="Technician note">${escapeHtml(item.technician_note || "")}</textarea>
        </div>
      </td>
    </tr>`;
  }).join("");

  elements.assessmentRows.querySelectorAll("tr").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (!event.target.matches("input, select, textarea, option")) {
        selectRow(Number(row.dataset.index));
      }
    });
    row.querySelectorAll("[data-field]").forEach((control) => {
      control.addEventListener("change", handleRowChange);
      if (control.matches("input, textarea")) {
        control.addEventListener("input", handleRowChange);
      }
    });
  });
}

function handleRowChange(event) {
  const row = event.target.closest("tr");
  const index = Number(row.dataset.index);
  const field = event.target.dataset.field;
  state.items[index][field] = event.target.value;

  if (field === "technician_decision") {
    const rejection = row.querySelector(".reject-reason");
    rejection.classList.toggle("hidden", event.target.value !== "Reject");
    if (event.target.value !== "Reject") {
      state.items[index].rejection_reason = "";
      rejection.value = "";
    }
    updateProgress();
  }
  if (
    field === "predicted_part_name"
    && event.type === "change"
    && state.items[index].source === "manual"
  ) {
    const match = state.catalogueParts.find(
      (part) => part.part_name.toLowerCase() === event.target.value.toLowerCase()
    );
    if (match) {
      Object.assign(state.items[index], {
        predicted_part_id: match.part_id,
        predicted_part_name: match.part_name,
        oem_number: match.oem_number,
        diagram_id: match.diagram_id,
        diagram_url: match.diagram_url,
        ai_action: "Technician-selected from imported catalogue",
      });
      state.selectedIndex = index;
      renderTable();
      selectRow(index);
    }
  }
  if (
    ["technician_decision", "oem_number", "predicted_part_name", "corrected_part_name"]
      .includes(field)
  ) {
    renderSupplierComparison();
  }
  state.caseId = null;
  elements.exportButton.disabled = true;
}

function updateProgress() {
  const reviewable = state.items.filter((item) => item.source !== "impact_path");
  const reviewed = reviewable.filter(
    (item) => item.technician_decision && item.technician_decision !== "Pending"
  ).length;
  const percentage = reviewable.length ? Math.round((reviewed / reviewable.length) * 100) : 0;
  elements.reviewProgress.textContent = `${percentage}%`;
  elements.reviewProgressText.textContent = `${reviewed} of ${reviewable.length} rows reviewed`;
}

elements.addPartButton.addEventListener("click", () => {
  state.items.push({
    source: "manual",
    raw_part_name: "",
    predicted_part_id: null,
    predicted_part_name: "",
    oem_number: null,
    diagram_id: null,
    diagram_url: null,
    ai_confidence: null,
    ai_action: "Technician-added missing part",
    technician_decision: "Confirm",
    rejection_reason: "",
    corrected_part_id: "",
    corrected_part_name: "",
    technician_note: "",
    hotspot: null,
  });
  renderTable();
  renderSupplierComparison();
  updateProgress();
  const rows = elements.assessmentRows.querySelectorAll("tr");
  rows[rows.length - 1]?.scrollIntoView({ behavior: "smooth", block: "center" });
});

async function selectRow(index) {
  state.selectedIndex = index;
  renderTable();
  const item = state.items[index];
  elements.diagramTitle.textContent = item.predicted_part_name || item.raw_part_name;
  if (!item.diagram_id && !item.diagram_url) {
    state.currentDiagramId = null;
    elements.diagramIdBadge.textContent = "No diagram";
    elements.diagramEmpty.classList.remove("hidden");
    elements.diagramStage.classList.add("hidden");
    return;
  }

  state.currentDiagramId = String(item.diagram_id || item.predicted_part_id);
  elements.diagramIdBadge.textContent = item.diagram_url
    ? "Imported diagram"
    : `Diagram ${item.diagram_id}`;
  elements.diagramEmpty.classList.add("hidden");
  elements.diagramStage.classList.remove("hidden");
  const vehicle = selectedVehicle();
  if (item.diagram_url) {
    elements.diagramImage.src = item.diagram_url;
    state.diagramMeta[state.currentDiagramId] = {};
    if (elements.diagramImage.complete) renderOverlays();
    return;
  }
  const providerKey = encodeURIComponent(vehicle?.provider_key || "");
  const diagram = encodeURIComponent(item.diagram_id);
  elements.diagramImage.src = `/api/partly/vehicles/${providerKey}/diagrams/${diagram}/image`;
  try {
    state.diagramMeta[state.currentDiagramId] = await request(
      `/api/partly/vehicles/${providerKey}/diagrams/${diagram}/meta`
    );
  } catch (_error) {
    state.diagramMeta[state.currentDiagramId] = {};
  }
  if (elements.diagramImage.complete) renderOverlays();
}

elements.diagramImage.addEventListener("load", renderOverlays);
window.addEventListener("resize", renderOverlays);

function procurementParts() {
  const parts = new Map();
  state.items.forEach((item) => {
    const oemNumber = String(item.oem_number || "").trim();
    if (item.technician_decision !== "Confirm" || !oemNumber) return;
    const key = oemNumber.toUpperCase();
    if (parts.has(key)) return;
    parts.set(key, {
      key,
      oem_number: oemNumber,
      part_name: (
        item.corrected_part_name
        || item.predicted_part_name
        || item.raw_part_name
        || "Confirmed part"
      ),
    });
  });
  return [...parts.values()];
}

function blankSupplierQuote(partKey) {
  state.quoteSequence += 1;
  return {
    id: `draft-${state.quoteSequence}`,
    quote_id: null,
    part_key: partKey,
    supplier: "",
    stock_status: "unknown",
    stock_quantity: "",
    unit_price: "",
    currency: "NZD",
    estimated_arrival: "",
    notes: "",
    is_preferred: false,
    is_draft: true,
    dirty: true,
    saving: false,
    error: "",
  };
}

function quoteFromApi(quote, partKey) {
  return {
    ...quote,
    id: quote.quote_id,
    part_key: partKey,
    stock_quantity: quote.stock_quantity ?? "",
    estimated_arrival: quote.estimated_arrival || "",
    is_preferred: Boolean(quote.is_preferred),
    is_draft: false,
    dirty: false,
    saving: false,
    error: "",
  };
}

function currentVehicleId() {
  return state.assessment?.vehicle?.id || elements.vehicleSelect.value;
}

async function loadSupplierQuotes(part, force = false) {
  if (!force && state.supplierQuoteLoads[part.key] === "loaded") return;
  state.supplierQuoteLoads[part.key] = "loading";
  renderSupplierComparison();
  try {
    const params = new URLSearchParams({
      vehicle_id: currentVehicleId(),
      oem_number: part.oem_number,
    });
    const quotes = await request(`/api/v1/supplier-quotes?${params}`);
    state.supplierQuotes[part.key] = quotes.map(
      (quote) => quoteFromApi(quote, part.key)
    );
    state.supplierQuoteLoads[part.key] = "loaded";
  } catch (error) {
    state.supplierQuoteLoads[part.key] = "error";
    state.supplierQuotes[part.key] = [];
    state.supplierQuoteLoads[`${part.key}:error`] = error.message;
  }
  renderSupplierComparison();
}

function dateDisplayFromIso(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : "";
}

function formatDateEntry(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
}

function isoDateFromDisplay(value) {
  const match = String(value || "").match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return "";
  const [, day, month, year] = match;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  if (
    date.getUTCFullYear() !== Number(year)
    || date.getUTCMonth() !== Number(month) - 1
    || date.getUTCDate() !== Number(day)
  ) return "";
  return `${year}-${month}-${day}`;
}

function supplierQuoteBadges(quote, lowestPrice, earliestArrival) {
  const badges = [];
  const price = Number(quote.unit_price);
  if (price > 0 && price === lowestPrice) badges.push("Lowest price");
  if (
    quote.estimated_arrival
    && quote.estimated_arrival === earliestArrival
  ) badges.push("Earliest arrival");
  if (quote.stock_status === "in_stock") badges.push("In stock");
  if (quote.stock_status === "out_of_stock") badges.push("Out of stock");
  if (quote.stock_status === "backorder") badges.push("Backorder");
  if (quote.stock_status === "unknown") badges.push("Availability unknown");
  if (quote.is_draft) badges.push("Unsaved");
  if (quote.dirty && !quote.is_draft) badges.push("Changes not saved");
  return badges.map((badge) => `<span>${escapeHtml(badge)}</span>`).join("");
}

function stockSummary(quote) {
  if (quote.stock_status === "in_stock") {
    return `${escapeHtml(quote.stock_quantity)} in stock`;
  }
  if (quote.stock_status === "out_of_stock") return "Out of stock";
  if (quote.stock_status === "backorder") return "Backorder";
  return "Availability unknown";
}

function availabilityOptions(selected) {
  return [
    ["unknown", "Unknown"],
    ["in_stock", "In stock"],
    ["out_of_stock", "Out of stock"],
    ["backorder", "Backorder"],
  ].map(([value, label]) => (
    `<option value="${value}" ${selected === value ? "selected" : ""}>`
    + `${label}</option>`
  )).join("");
}

function renderSupplierComparison() {
  const parts = procurementParts();
  elements.supplierEmpty.classList.toggle("hidden", parts.length > 0);
  elements.supplierComparison.classList.toggle("hidden", parts.length === 0);
  if (!parts.length) {
    elements.supplierComparison.innerHTML = "";
    return;
  }

  parts.forEach((part) => {
    if (!state.supplierQuoteLoads[part.key]) {
      state.supplierQuoteLoads[part.key] = "loading";
      loadSupplierQuotes(part);
    }
  });

  elements.supplierComparison.innerHTML = parts.map((part) => {
    const quotes = state.supplierQuotes[part.key] || [];
    const loadState = state.supplierQuoteLoads[part.key];
    const prices = quotes
      .map((quote) => Number(quote.unit_price))
      .filter((price) => price > 0);
    const arrivals = quotes
      .map((quote) => quote.estimated_arrival)
      .filter(Boolean)
      .sort();
    const lowestPrice = prices.length ? Math.min(...prices) : null;
    const earliestArrival = arrivals[0] || "";
    const selectedQuote = quotes.find((quote) => quote.is_preferred);
    let quoteRows = quotes.map((quote) => `
      <tr data-part-key="${escapeHtml(part.key)}" data-quote-id="${escapeHtml(quote.id)}">
        <td>
          <input
            data-quote-field="supplier"
            value="${escapeHtml(quote.supplier)}"
            placeholder="Supplier name"
            aria-label="Supplier name"
          >
        </td>
        <td>
          <select
            data-quote-field="stock_status"
            aria-label="Availability"
          >${availabilityOptions(quote.stock_status)}</select>
        </td>
        <td>
          <input
            data-quote-field="stock_quantity"
            type="number"
            min="1"
            step="1"
            value="${escapeHtml(quote.stock_quantity)}"
            placeholder="Qty"
            aria-label="Stock quantity"
            ${quote.stock_status === "in_stock" ? "" : "disabled"}
          >
        </td>
        <td>
          <div class="price-input">
            <span>NZ$</span>
            <input
              data-quote-field="unit_price"
              type="number"
              min="0"
              step="0.01"
              value="${escapeHtml(quote.unit_price)}"
              placeholder="0.00"
              aria-label="Unit price in New Zealand dollars"
            >
          </div>
        </td>
        <td>
          <div class="date-input">
            <input
              data-quote-date-display
              type="text"
              value="${escapeHtml(dateDisplayFromIso(quote.estimated_arrival))}"
              placeholder="DD/MM/YYYY"
              inputmode="numeric"
              maxlength="10"
              autocomplete="off"
              aria-label="Estimated arrival date, day month year"
            >
            <button
              class="date-picker-button"
              data-quote-action="open-date"
              type="button"
              aria-label="Open date picker"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M7 2v3M17 2v3M3.5 9h17M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2Z"/>
              </svg>
            </button>
            <input
              class="native-date-picker"
              data-quote-field="estimated_arrival"
              type="date"
              lang="en-NZ"
              value="${escapeHtml(quote.estimated_arrival)}"
              tabindex="-1"
              aria-hidden="true"
            >
          </div>
        </td>
        <td>
          <div class="quote-badges">
            ${supplierQuoteBadges(quote, lowestPrice, earliestArrival)}
          </div>
        </td>
        <td class="quote-actions">
          <button
            class="quote-save"
            data-quote-action="save"
            type="button"
            ${quote.saving ? "disabled" : ""}
          >${quote.saving ? "Saving…" : quote.is_draft ? "Save quote" : "Update"}</button>
          <button
            class="quote-select ${quote.is_preferred ? "selected" : ""}"
            data-quote-action="select"
            type="button"
            ${quote.saving ? "disabled" : ""}
          >${quote.is_preferred ? "Preferred" : "Make preferred"}</button>
          <button
            class="quote-remove"
            data-quote-action="remove"
            type="button"
            ${quote.saving ? "disabled" : ""}
            aria-label="Remove supplier quote"
          >×</button>
          ${quote.error
            ? `<span class="quote-error">${escapeHtml(quote.error)}</span>`
            : ""}
        </td>
      </tr>
    `).join("");
    if (!quoteRows) {
      if (loadState === "loading") {
        quoteRows = '<tr><td class="quote-empty-row" colspan="7">Loading saved quotes…</td></tr>';
      } else if (loadState === "error") {
        quoteRows = `
          <tr>
            <td class="quote-empty-row" colspan="7">
              Could not load saved quotes.
              <button data-quote-action="retry" data-part-key="${escapeHtml(part.key)}" type="button">Retry</button>
            </td>
          </tr>
        `;
      } else {
        quoteRows = '<tr><td class="quote-empty-row" colspan="7">No saved quotes yet. Availability remains unknown until a quote is added.</td></tr>';
      }
    }
    return `
      <article class="supplier-part" data-part-key="${escapeHtml(part.key)}">
        <div class="supplier-part-heading">
          <div>
            <span class="supplier-part-name">${escapeHtml(part.part_name)}</span>
            <span class="oem-number procurement-oem">
              <span>OEM</span>
              <strong>${escapeHtml(part.oem_number)}</strong>
            </span>
          </div>
          <button
            class="secondary-button small"
            data-quote-action="add"
            data-part-key="${escapeHtml(part.key)}"
            type="button"
            ${loadState === "loaded" ? "" : "disabled"}
          >+ Add supplier quote</button>
        </div>
        <div class="supplier-table-wrap">
          <table class="supplier-table">
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Availability</th>
                <th>Quantity</th>
                <th>Unit price</th>
                <th>Estimated arrival</th>
                <th>Comparison</th>
                <th>Preferred</th>
              </tr>
            </thead>
            <tbody>${quoteRows}</tbody>
          </table>
        </div>
        <div class="quote-selection-summary ${selectedQuote ? "ready" : ""}">
          ${selectedQuote
            ? `<strong>Preferred quote:</strong>
              <span>${escapeHtml(selectedQuote.supplier || "Unnamed supplier")}</span>
              <span>${stockSummary(selectedQuote)}</span>
              <span>${Number(selectedQuote.unit_price) > 0 ? `NZ$${Number(selectedQuote.unit_price).toFixed(2)}` : "Price not entered"}</span>
              <span>${selectedQuote.estimated_arrival ? `Arrives ${escapeHtml(dateDisplayFromIso(selectedQuote.estimated_arrival))}` : "Arrival not entered"}</span>`
            : "Saved quotes will return after refresh. Add a quote, then choose a preferred supplier if needed."}
        </div>
      </article>
    `;
  }).join("");
}

function supplierQuoteFromControl(control) {
  const row = control.closest("tr[data-quote-id]");
  if (!row) return null;
  const quotes = state.supplierQuotes[row.dataset.partKey] || [];
  return quotes.find((quote) => quote.id === row.dataset.quoteId) || null;
}

function quotePayload(part, quote, preferred = quote.is_preferred) {
  return {
    vehicle_id: currentVehicleId(),
    oem_number: part.oem_number,
    part_name: part.part_name,
    supplier: quote.supplier.trim(),
    unit_price: Number(quote.unit_price),
    currency: quote.currency || "NZD",
    stock_status: quote.stock_status || "unknown",
    stock_quantity: (
      quote.stock_status === "in_stock"
        ? Number(quote.stock_quantity)
        : null
    ),
    estimated_arrival: quote.estimated_arrival || null,
    notes: quote.notes || "",
    is_preferred: Boolean(preferred),
  };
}

async function persistSupplierQuote(partKey, quote, preferred = quote.is_preferred) {
  const part = procurementParts().find((candidate) => candidate.key === partKey);
  if (!part) throw new Error("The confirmed part is no longer available");
  if (!(Number(quote.unit_price) > 0)) {
    throw new Error("Enter a unit price greater than zero");
  }
  if (
    quote.stock_status === "in_stock"
    && !(Number(quote.stock_quantity) >= 1)
  ) {
    throw new Error("Enter a stock quantity of at least 1");
  }

  quote.saving = true;
  quote.error = "";
  renderSupplierComparison();
  try {
    const payload = quotePayload(part, quote, preferred);
    let saved;
    if (quote.is_draft) {
      saved = await request("/api/v1/supplier-quotes", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    } else {
      const {
        vehicle_id: _vehicleId,
        oem_number: _oemNumber,
        ...changes
      } = payload;
      saved = await request(
        `/api/v1/supplier-quotes/${encodeURIComponent(quote.quote_id)}`,
        {
          method: "PATCH",
          body: JSON.stringify(changes),
        }
      );
    }
    const quotes = state.supplierQuotes[partKey] || [];
    if (saved.is_preferred) {
      quotes.forEach((candidate) => {
        candidate.is_preferred = false;
      });
    }
    const index = quotes.findIndex((candidate) => candidate.id === quote.id);
    const normalised = quoteFromApi(saved, partKey);
    if (index >= 0) quotes.splice(index, 1, normalised);
    else quotes.push(normalised);
    state.supplierQuoteLoads[partKey] = "loaded";
    renderSupplierComparison();
    return normalised;
  } catch (error) {
    quote.saving = false;
    quote.error = error.message;
    renderSupplierComparison();
    throw error;
  }
}

elements.supplierComparison.addEventListener("input", (event) => {
  if (event.target.matches("[data-quote-date-display]")) {
    event.target.value = formatDateEntry(event.target.value);
    event.target.setCustomValidity("");
    return;
  }
  const field = event.target.dataset.quoteField;
  if (!field) return;
  const quote = supplierQuoteFromControl(event.target);
  if (quote) {
    quote[field] = event.target.value;
    quote.dirty = true;
    quote.error = "";
  }
});

elements.supplierComparison.addEventListener("change", (event) => {
  if (event.target.matches("[data-quote-date-display]")) {
    const quote = supplierQuoteFromControl(event.target);
    if (!quote) return;
    const displayValue = event.target.value.trim();
    const arrival = isoDateFromDisplay(displayValue);
    if (displayValue && !arrival) {
      event.target.setCustomValidity("Enter a valid date in DD/MM/YYYY format.");
      event.target.reportValidity();
      return;
    }
    event.target.setCustomValidity("");
    quote.estimated_arrival = arrival;
    quote.dirty = true;
    renderSupplierComparison();
    return;
  }
  const field = event.target.dataset.quoteField;
  if (!field) return;
  const quote = supplierQuoteFromControl(event.target);
  if (quote) {
    quote[field] = event.target.value;
    quote.dirty = true;
    quote.error = "";
    if (field === "stock_status") {
      if (quote.stock_status === "out_of_stock") quote.stock_quantity = 0;
      if (
        quote.stock_status === "unknown"
        || quote.stock_status === "backorder"
      ) quote.stock_quantity = "";
      if (quote.stock_status === "in_stock" && Number(quote.stock_quantity) < 1) {
        quote.stock_quantity = "";
      }
    }
  }
  renderSupplierComparison();
});

elements.supplierComparison.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-quote-action]");
  if (!button) return;
  const action = button.dataset.quoteAction;
  if (action === "open-date") {
    const picker = button.closest(".date-input")?.querySelector(".native-date-picker");
    if (!picker) return;
    if (typeof picker.showPicker === "function") picker.showPicker();
    else picker.click();
    return;
  }
  if (action === "retry") {
    const retryKey = button.dataset.partKey;
    const part = procurementParts().find((candidate) => candidate.key === retryKey);
    if (part) await loadSupplierQuotes(part, true);
    return;
  }
  const partKey = (
    button.dataset.partKey
    || button.closest("[data-part-key]")?.dataset.partKey
  );
  if (!partKey) return;
  const quotes = state.supplierQuotes[partKey] || [];
  if (action === "add") {
    quotes.push(blankSupplierQuote(partKey));
  } else {
    const row = button.closest("tr[data-quote-id]");
    const quoteId = row?.dataset.quoteId;
    if (!quoteId) return;
    const quote = quotes.find((candidate) => candidate.id === quoteId);
    if (!quote) return;
    if (action === "save") {
      try {
        await persistSupplierQuote(partKey, quote);
        showToast("Supplier quote saved");
      } catch (error) {
        showToast(error.message);
      }
      return;
    }
    if (action === "select") {
      try {
        await persistSupplierQuote(partKey, quote, true);
        showToast("Preferred quote saved");
      } catch (error) {
        showToast(error.message);
      }
      return;
    }
    if (action === "remove") {
      try {
        if (!quote.is_draft) {
          quote.saving = true;
          renderSupplierComparison();
          await request(
            `/api/v1/supplier-quotes/${encodeURIComponent(quote.quote_id)}`,
            { method: "DELETE" }
          );
        }
        const index = quotes.findIndex((candidate) => candidate.id === quoteId);
        if (index >= 0) quotes.splice(index, 1);
        showToast(quote.is_draft ? "Unsaved quote removed" : "Supplier quote deleted");
      } catch (error) {
        quote.saving = false;
        quote.error = error.message;
        showToast(error.message);
      }
    }
  }
  renderSupplierComparison();
});

async function persistSupplierQuoteChanges() {
  const parts = procurementParts();
  for (const part of parts) {
    const quotes = [...(state.supplierQuotes[part.key] || [])];
    for (const quote of quotes) {
      if (!quote.is_draft && !quote.dirty) continue;
      const hasEnteredData = (
        quote.supplier.trim()
        || Number(quote.unit_price) > 0
        || quote.stock_status !== "unknown"
        || quote.estimated_arrival
      );
      if (!hasEnteredData) continue;
      await persistSupplierQuote(part.key, quote);
    }
  }
  return parts
    .flatMap((part) => state.supplierQuotes[part.key] || [])
    .filter((quote) => !quote.is_draft && quote.quote_id)
    .map((quote) => quote.quote_id);
}

function imageBounds() {
  const stageRect = elements.diagramStage.getBoundingClientRect();
  const imageRect = elements.diagramImage.getBoundingClientRect();
  return {
    left: imageRect.left - stageRect.left,
    top: imageRect.top - stageRect.top,
    width: imageRect.width,
    height: imageRect.height,
  };
}

function hotspotToNormalised(hotspot, diagramId) {
  if (!hotspot) return null;
  const x1 = Number(hotspot.x1);
  const y1 = Number(hotspot.y1);
  const x2 = Number(hotspot.x2);
  const y2 = Number(hotspot.y2);
  if (![x1, y1, x2, y2].every(Number.isFinite)) return null;
  if ([x1, y1, x2, y2].every((value) => value >= 0 && value <= 1)) {
    return { x1, y1, x2, y2 };
  }
  const meta = state.diagramMeta[diagramId] || {};
  const scaleX = Number(meta.scale_x) || 1;
  const scaleY = Number(meta.scale_y) || 1;
  const naturalWidth = elements.diagramImage.naturalWidth || 1;
  const naturalHeight = elements.diagramImage.naturalHeight || 1;
  return {
    x1: (x1 * scaleX) / naturalWidth,
    y1: (y1 * scaleY) / naturalHeight,
    x2: (x2 * scaleX) / naturalWidth,
    y2: (y2 * scaleY) / naturalHeight,
  };
}

function placeOverlay(element, region) {
  const bounds = imageBounds();
  const left = bounds.left + Math.min(region.x1, region.x2) * bounds.width;
  const top = bounds.top + Math.min(region.y1, region.y2) * bounds.height;
  const width = Math.abs(region.x2 - region.x1) * bounds.width;
  const height = Math.abs(region.y2 - region.y1) * bounds.height;
  Object.assign(element.style, {
    left: `${left}px`,
    top: `${top}px`,
    width: `${Math.max(width, 4)}px`,
    height: `${Math.max(height, 4)}px`,
  });
}

function renderOverlays() {
  if (!state.currentDiagramId || !elements.diagramImage.complete) return;
  const item = state.items[state.selectedIndex];
  const hotspot = hotspotToNormalised(item?.hotspot, state.currentDiagramId);
  elements.hotspotOverlay.classList.toggle("hidden", !hotspot);
  if (hotspot) placeOverlay(elements.hotspotOverlay, hotspot);
}

elements.saveButton.addEventListener("click", saveCase);

async function saveCase() {
  if (!state.assessment) return;
  elements.saveButton.disabled = true;
  elements.saveButton.textContent = "Saving…";
  elements.saveMessage.classList.add("hidden");
  const vehicle = state.assessment.vehicle || {};

  try {
    const quoteIds = await persistSupplierQuoteChanges();
    const payload = {
      vehicle_slug: vehicle.id || elements.vehicleSelect.value,
      vehicle_make: vehicle.make || "",
      vehicle_model: vehicle.model || "",
      vehicle_year: String(vehicle.year || ""),
      vehicle_trim: elements.trimInput.value.trim(),
      vin: elements.vinInput.value.trim(),
      status: "Reviewed",
      photo_run_id: state.photoAssessment?.run_id || null,
      items: state.items,
      quote_ids: quoteIds,
    };
    const result = await request("/api/cases", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.caseId = result.case_id;
    elements.exportButton.disabled = false;
    elements.saveMessage.textContent = `Review saved. Case ID: ${result.case_id}`;
    elements.saveMessage.className = "save-message success";
    showToast("Technician review saved");
    await renderHistory();
  } catch (error) {
    elements.saveMessage.textContent = error.message;
    elements.saveMessage.className = "save-message error";
  } finally {
    elements.saveButton.disabled = false;
    elements.saveButton.textContent = "Save technician review";
  }
}

elements.exportButton.addEventListener("click", () => {
  if (state.caseId) {
    window.location.href = `/api/cases/${encodeURIComponent(state.caseId)}/export.csv`;
  }
});

function renderHistory() {
  const history = state.assessment?.similar_cases;
  if (!history) return;
  elements.historyBadge.textContent = (
    `${history.match_count} similar case${history.match_count === 1 ? "" : "s"}`
  );
  if (!history.match_count) {
    elements.historyContent.className = "history-empty";
    elements.historyContent.textContent = (
      "No saved case passed the similarity threshold for this photo pattern. "
      + "No historical part suggestion was added."
    );
    return;
  }
  const matches = (history.matches || []).map((match) => (
    `<div class="similar-case-row">
      <strong>${Math.round(match.similarity * 100)}% match</strong>
      <span>${escapeHtml((match.signals || []).join(" · "))}</span>
    </div>`
  )).join("");
  const recommendationCount = (history.recommendations || []).length;
  elements.historyContent.className = "history-stats";
  elements.historyContent.innerHTML = `
    <div class="history-number">
      <div><strong>${history.match_count}</strong><span>cases above ${Math.round(history.threshold * 100)}%</span></div>
      <div><strong>${recommendationCount}</strong><span>confirmed parts referenced</span></div>
    </div>
    <div class="similar-case-list">${matches}</div>
    <p class="muted">These cases can suggest inspection targets only. They do not replace this photo analysis.</p>
  `;
}

initialise();
